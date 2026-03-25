from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.models import YouTubeCredentials


def make_yt_credentials(user):
    return YouTubeCredentials.objects.create(
        user=user,
        access_token='old_access_token',
        refresh_token='refresh_token',
        token_uri='https://oauth2.googleapis.com/token',
        scopes='https://www.googleapis.com/auth/youtube',
    )


class RefreshAccessTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ytuser', password='pass123')
        self.yt_creds = make_yt_credentials(self.user)

    @patch('youtube.services.requests.post')
    def test_returns_new_token_and_saves_to_db(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'access_token': 'new_yt_token'}
        from youtube.services import refresh_access_token
        result = refresh_access_token('refresh_token', 'cid', 'csecret', self.yt_creds)
        self.assertEqual(result, 'new_yt_token')
        self.yt_creds.refresh_from_db()
        self.assertEqual(self.yt_creds.access_token, 'new_yt_token')

    @patch('youtube.services.requests.post')
    def test_raises_on_non_200_response(self, mock_post):
        mock_post.return_value.status_code = 401
        mock_post.return_value.text = 'Unauthorized'
        from youtube.services import refresh_access_token
        with self.assertRaises(Exception) as ctx:
            refresh_access_token('bad_refresh', 'cid', 'csecret', self.yt_creds)
        self.assertIn('Error refreshing YouTube token', str(ctx.exception))
        self.assertIn('401', str(ctx.exception))

    @patch('youtube.services.requests.post')
    def test_posts_correct_grant_type(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'access_token': 'tok'}
        from youtube.services import refresh_access_token
        refresh_access_token('ref', 'cid', 'csecret', self.yt_creds)
        call_data = mock_post.call_args[1]['data']
        self.assertEqual(call_data['grant_type'], 'refresh_token')
        self.assertEqual(call_data['client_id'], 'cid')
        self.assertEqual(call_data['refresh_token'], 'ref')


@override_settings(GOOGLE_CLIENT_ID='test_cid', GOOGLE_CLIENT_SECRET='test_csecret')
class GetYoutubeServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ytuser2', password='pass123')
        self.yt_creds = make_yt_credentials(self.user)

    @patch('youtube.services.build')
    def test_calls_build_with_youtube_v3(self, mock_build):
        mock_build.return_value = MagicMock()
        from youtube.services import get_youtube_service_from_credentials
        get_youtube_service_from_credentials(self.yt_creds)
        mock_build.assert_called_once()
        args = mock_build.call_args[0]
        self.assertEqual(args[0], 'youtube')
        self.assertEqual(args[1], 'v3')

    @patch('youtube.services.build')
    def test_returns_built_service(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        from youtube.services import get_youtube_service_from_credentials
        result = get_youtube_service_from_credentials(self.yt_creds)
        self.assertIs(result, mock_service)
