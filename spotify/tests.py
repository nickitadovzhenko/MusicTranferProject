from unittest.mock import patch

import spotipy.exceptions
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import SpotifyToken


class GetAuthorizationUrlTest(TestCase):
    def test_contains_required_oauth_params(self):
        from spotify.services import get_authorization_url
        url = get_authorization_url(state='mystate')
        self.assertIn('response_type=code', url)
        self.assertIn('state=mystate', url)
        self.assertIn('scope=', url)

    def test_show_dialog_appends_param(self):
        from spotify.services import get_authorization_url
        url = get_authorization_url(show_dialog=True)
        self.assertIn('show_dialog=true', url)

    def test_show_dialog_false_by_default(self):
        from spotify.services import get_authorization_url
        url = get_authorization_url()
        self.assertNotIn('show_dialog', url)

    def test_auto_generates_state_when_none_given(self):
        from spotify.services import get_authorization_url
        url = get_authorization_url()
        self.assertIn('state=', url)


class ExchangeCodeForTokensTest(TestCase):
    @patch('spotify.services.requests.post')
    def test_returns_token_json_on_200(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'access_token': 'access123',
            'refresh_token': 'refresh456',
        }
        from spotify.services import exchange_code_for_tokens
        result = exchange_code_for_tokens('code', 'http://redirect', 'cid', 'csecret')
        self.assertEqual(result['access_token'], 'access123')
        self.assertEqual(result['refresh_token'], 'refresh456')

    @patch('spotify.services.requests.post')
    def test_returns_none_on_non_200(self, mock_post):
        mock_post.return_value.status_code = 400
        from spotify.services import exchange_code_for_tokens
        result = exchange_code_for_tokens('bad_code', 'http://redirect', 'cid', 'csecret')
        self.assertIsNone(result)


class ExchangeRefreshTokenTest(TestCase):
    @patch('spotify.services.requests.post')
    def test_returns_new_token_data(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'access_token': 'fresh_token'}
        from spotify.services import exchange_refresh_token_for_tokens
        result = exchange_refresh_token_for_tokens('refresh', 'cid', 'csecret')
        self.assertEqual(result['access_token'], 'fresh_token')

    @patch('spotify.services.requests.post')
    def test_raises_on_non_200_response(self, mock_post):
        mock_post.return_value.status_code = 401
        from spotify.services import exchange_refresh_token_for_tokens
        with self.assertRaises(Exception) as ctx:
            exchange_refresh_token_for_tokens('bad_refresh', 'cid', 'csecret')
        self.assertIn('Failed to refresh Spotify token', str(ctx.exception))
        self.assertIn('401', str(ctx.exception))


class IsTokenValidTest(TestCase):
    @patch('spotify.services.spotipy.Spotify')
    def test_returns_true_for_valid_token(self, MockSpotify):
        MockSpotify.return_value.current_user.return_value = {'id': 'user1'}
        from spotify.services import is_token_valid
        self.assertTrue(is_token_valid('valid_token'))

    @patch('spotify.services.spotipy.Spotify')
    def test_returns_false_for_401(self, MockSpotify):
        MockSpotify.return_value.current_user.side_effect = (
            spotipy.exceptions.SpotifyException(http_status=401, code=-1, msg='Unauthorized')
        )
        from spotify.services import is_token_valid
        self.assertFalse(is_token_valid('expired_token'))

    @patch('spotify.services.spotipy.Spotify')
    def test_propagates_non_401_spotify_exception(self, MockSpotify):
        MockSpotify.return_value.current_user.side_effect = (
            spotipy.exceptions.SpotifyException(http_status=500, code=-1, msg='Server Error')
        )
        from spotify.services import is_token_valid
        with self.assertRaises(spotipy.exceptions.SpotifyException):
            is_token_valid('some_token')


class GetValidAccessTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='spotifyuser', password='pass123')

    @patch('spotify.services.is_token_valid', return_value=True)
    def test_returns_existing_token_when_still_valid(self, _mock):
        SpotifyToken.objects.create(
            user=self.user, access_token='valid_access', refresh_token='some_refresh'
        )
        from spotify.services import get_valid_access_token
        token = get_valid_access_token(self.user)
        self.assertEqual(token, 'valid_access')

    @patch('spotify.services.exchange_refresh_token_for_tokens')
    @patch('spotify.services.is_token_valid', return_value=False)
    def test_refreshes_and_saves_new_token_when_expired(self, _mock_valid, mock_refresh):
        mock_refresh.return_value = {'access_token': 'refreshed_access'}
        SpotifyToken.objects.create(
            user=self.user, access_token='old_access', refresh_token='my_refresh'
        )
        from spotify.services import get_valid_access_token
        token = get_valid_access_token(self.user)
        self.assertEqual(token, 'refreshed_access')
        # Verify the new token was persisted to the DB
        db_token = SpotifyToken.objects.get(user=self.user)
        self.assertEqual(db_token.access_token, 'refreshed_access')

    def test_raises_when_no_spotify_account_linked(self):
        from spotify.services import get_valid_access_token
        with self.assertRaises(Exception) as ctx:
            get_valid_access_token(self.user)
        self.assertIn('connect your Spotify account', str(ctx.exception))
