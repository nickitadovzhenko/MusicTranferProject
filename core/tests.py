from unittest.mock import patch, MagicMock, call
from django.db import connection
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from core.models import SpotifyToken, YouTubeCredentials, TransferJob
from core.tasks import (
    transfer_spotify_to_youtube_task,
    transfer_youtube_to_spotify_task,
    transfer_spotify_to_spotify_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username='testuser', password='pass123'):
    return User.objects.create_user(username=username, password=password)


def make_yt_credentials(user):
    return YouTubeCredentials.objects.create(
        user=user,
        access_token='yt_access',
        refresh_token='yt_refresh',
        token_uri='https://oauth2.googleapis.com/token',
        scopes='https://www.googleapis.com/auth/youtube',
    )


def spotify_track(name='Song', artist='Artist', uri='spotify:track:abc', is_local=False):
    """Return a dict shaped like a Spotify track item."""
    return {
        'track': {
            'name': name,
            'artists': [{'name': artist}],
            'uri': uri,
            'is_local': is_local,
        }
    }


def spotify_page(items, has_next=False):
    """Return a dict shaped like a Spotify paged response."""
    return {'items': items, 'next': 'http://next-page' if has_next else None}


# ---------------------------------------------------------------------------
# Task: transfer_spotify_to_youtube_task
# ---------------------------------------------------------------------------

class TransferSpotifyToYoutubeTaskTest(TestCase):
    def setUp(self):
        self.user = make_user('s2y_user')
        make_yt_credentials(self.user)

    def _run(self, playlist_ids):
        return transfer_spotify_to_youtube_task.apply(args=[self.user.id, playlist_ids])

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_happy_path_sets_status_done(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.playlist.return_value = {'name': 'My Playlist'}
        mock_sp.playlist_tracks.return_value = spotify_page([spotify_track()])

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.insert.return_value.execute.return_value = {'id': 'yt_pl_1'}
        mock_yt.search.return_value.list.return_value.execute.return_value = {
            'items': [{'id': {'videoId': 'vid_abc'}}]
        }

        self._run(['playlist_id_1'])

        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'done')
        self.assertEqual(job.processed_count, 1)

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_liked_songs_uses_saved_tracks_endpoint(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.current_user_saved_tracks.return_value = spotify_page([spotify_track()])

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.insert.return_value.execute.return_value = {'id': 'yt_liked'}
        mock_yt.search.return_value.list.return_value.execute.return_value = {'items': []}

        self._run(['liked_songs'])

        mock_sp.current_user_saved_tracks.assert_called_once()
        mock_sp.playlist.assert_not_called()

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_skips_adding_item_when_youtube_search_has_no_results(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.playlist.return_value = {'name': 'My Playlist'}
        mock_sp.playlist_tracks.return_value = spotify_page([spotify_track()])

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.insert.return_value.execute.return_value = {'id': 'yt_pl'}
        mock_yt.search.return_value.list.return_value.execute.return_value = {'items': []}

        self._run(['playlist_id_1'])

        mock_yt.playlistItems.return_value.insert.assert_not_called()

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_handles_null_track_in_playlist(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.playlist.return_value = {'name': 'My Playlist'}
        # One valid track, one null track
        mock_sp.playlist_tracks.return_value = spotify_page([{'track': None}, spotify_track()])

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.insert.return_value.execute.return_value = {'id': 'yt_pl'}
        mock_yt.search.return_value.list.return_value.execute.return_value = {
            'items': [{'id': {'videoId': 'vid_xyz'}}]
        }

        # Should not raise
        self._run(['playlist_id_1'])
        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'done')

    @patch('core.tasks.get_valid_access_token', side_effect=Exception('Spotify auth failed'))
    def test_exception_sets_job_to_error_and_stores_message(self, _tok):
        self._run(['playlist_id_1'])
        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'error')
        self.assertIn('Spotify auth failed', job.error_msg)


# ---------------------------------------------------------------------------
# Task: transfer_youtube_to_spotify_task
# ---------------------------------------------------------------------------

class TransferYoutubeToSpotifyTaskTest(TestCase):
    def setUp(self):
        self.user = make_user('y2s_user')
        make_yt_credentials(self.user)

    def _run(self, playlist_ids):
        return transfer_youtube_to_spotify_task.apply(args=[self.user.id, playlist_ids])

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_happy_path_creates_spotify_playlist_and_adds_tracks(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.me.return_value = {'id': 'spotify_user_id'}
        mock_sp.user_playlist_create.return_value = {'id': 'new_sp_pl'}
        mock_sp.search.return_value = {'tracks': {'items': [{'uri': 'spotify:track:xyz'}]}}

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 'My YT Playlist'}}]
        }
        mock_yt.playlistItems.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 'Some Song'}}],
        }
        mock_yt.playlistItems.return_value.list_next.return_value = None

        self._run(['yt_playlist_id'])

        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'done')
        mock_sp.playlist_add_items.assert_called_once()

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_skips_playlist_when_youtube_returns_no_items(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.me.return_value = {'id': 'spotify_user_id'}

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.list.return_value.execute.return_value = {'items': []}

        self._run(['empty_yt_playlist'])

        mock_sp.user_playlist_create.assert_not_called()

    @patch('core.tasks.get_youtube_service_from_credentials')
    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='sp_token')
    def test_does_not_add_tracks_when_no_spotify_matches_found(self, _tok, MockSpotify, mock_yt_svc):
        mock_sp = MockSpotify.return_value
        mock_sp.me.return_value = {'id': 'spotify_user_id'}
        mock_sp.user_playlist_create.return_value = {'id': 'new_sp_pl'}
        mock_sp.search.return_value = {'tracks': {'items': []}}  # No match

        mock_yt = mock_yt_svc.return_value
        mock_yt.playlists.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 'My YT Playlist'}}]
        }
        mock_yt.playlistItems.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 'Obscure Song'}}],
        }
        mock_yt.playlistItems.return_value.list_next.return_value = None

        self._run(['yt_playlist_id'])

        mock_sp.playlist_add_items.assert_not_called()

    @patch('core.tasks.get_valid_access_token', side_effect=Exception('Token failure'))
    def test_exception_sets_job_to_error(self, _tok):
        self._run(['yt_pl'])
        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'error')
        self.assertIn('Token failure', job.error_msg)


# ---------------------------------------------------------------------------
# Task: transfer_spotify_to_spotify_task
# ---------------------------------------------------------------------------

class TransferSpotifyToSpotifyTaskTest(TestCase):
    def setUp(self):
        self.user = make_user('s2s_user')

    def _run(self, playlist_ids):
        return transfer_spotify_to_spotify_task.apply(
            args=[self.user.id, playlist_ids, 'dest_access_token']
        )

    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='src_token')
    def test_playlist_transfer_happy_path(self, _tok, MockSpotify):
        mock_sp_src = MagicMock()
        mock_sp_dest = MagicMock()
        MockSpotify.side_effect = [mock_sp_src, mock_sp_dest]

        mock_sp_dest.me.return_value = {'id': 'dest_user'}
        mock_sp_src.playlist.return_value = {'name': 'Source Playlist'}
        mock_sp_src.playlist_tracks.return_value = spotify_page([
            spotify_track(uri='spotify:track:aaa'),
            spotify_track(uri='spotify:track:bbb'),
        ])
        mock_sp_dest.user_playlist_create.return_value = {'id': 'dest_pl_id'}

        self._run(['source_playlist_id'])

        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'done')
        mock_sp_dest.playlist_add_items.assert_called_once_with(
            playlist_id='dest_pl_id',
            items=['spotify:track:aaa', 'spotify:track:bbb'],
        )

    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='src_token')
    def test_liked_songs_transferred_with_saved_tracks_add(self, _tok, MockSpotify):
        mock_sp_src = MagicMock()
        mock_sp_dest = MagicMock()
        MockSpotify.side_effect = [mock_sp_src, mock_sp_dest]

        mock_sp_dest.me.return_value = {'id': 'dest_user'}
        mock_sp_src.current_user_saved_tracks.return_value = spotify_page([
            spotify_track(uri='spotify:track:liked1'),
        ])

        self._run(['liked_songs'])

        mock_sp_dest.current_user_saved_tracks_add.assert_called_once_with(
            tracks=['spotify:track:liked1']
        )
        mock_sp_dest.playlist_add_items.assert_not_called()

    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='src_token')
    def test_local_tracks_are_excluded(self, _tok, MockSpotify):
        mock_sp_src = MagicMock()
        mock_sp_dest = MagicMock()
        MockSpotify.side_effect = [mock_sp_src, mock_sp_dest]

        mock_sp_dest.me.return_value = {'id': 'dest_user'}
        mock_sp_src.playlist.return_value = {'name': 'My Playlist'}
        mock_sp_src.playlist_tracks.return_value = spotify_page([
            spotify_track(uri='spotify:local:x', is_local=True),
        ])
        mock_sp_dest.user_playlist_create.return_value = {'id': 'dest_pl'}

        self._run(['source_pl'])

        mock_sp_dest.playlist_add_items.assert_not_called()

    @patch('core.tasks.spotipy.Spotify')
    @patch('core.tasks.get_valid_access_token', return_value='src_token')
    def test_large_playlist_batched_in_100s(self, _tok, MockSpotify):
        mock_sp_src = MagicMock()
        mock_sp_dest = MagicMock()
        MockSpotify.side_effect = [mock_sp_src, mock_sp_dest]

        mock_sp_dest.me.return_value = {'id': 'dest_user'}
        mock_sp_src.playlist.return_value = {'name': 'Big Playlist'}
        tracks = [spotify_track(uri=f'spotify:track:{i}') for i in range(150)]
        mock_sp_src.playlist_tracks.return_value = spotify_page(tracks)
        mock_sp_dest.user_playlist_create.return_value = {'id': 'dest_pl'}

        self._run(['big_playlist'])

        self.assertEqual(mock_sp_dest.playlist_add_items.call_count, 2)  # 100 + 50

    @patch('core.tasks.get_valid_access_token', side_effect=Exception('Auth error'))
    def test_exception_sets_job_to_error(self, _tok):
        self._run(['some_pl'])
        job = TransferJob.objects.get(user=self.user)
        self.assertEqual(job.status, 'error')
        self.assertIn('Auth error', job.error_msg)


# ---------------------------------------------------------------------------
# View: dashboard
# ---------------------------------------------------------------------------

class DashboardViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user('dash_user')

    def test_unauthenticated_user_is_redirected(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_no_connections_shows_both_disconnected(self):
        self.client.login(username='dash_user', password='pass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['spoti_status'], 'no_connection')
        self.assertEqual(response.context['youtube_status'], 'no_connection')

    def test_spotify_connected_shows_correct_status(self):
        self.client.login(username='dash_user', password='pass123')
        SpotifyToken.objects.create(user=self.user, access_token='tok', refresh_token='ref')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['spoti_status'], 'connected')
        self.assertEqual(response.context['youtube_status'], 'no_connection')

    def test_both_connected_shows_both_statuses(self):
        self.client.login(username='dash_user', password='pass123')
        SpotifyToken.objects.create(user=self.user, access_token='tok', refresh_token='ref')
        make_yt_credentials(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['spoti_status'], 'connected')
        self.assertEqual(response.context['youtube_status'], 'connected')


# ---------------------------------------------------------------------------
# View: transfer_status
# ---------------------------------------------------------------------------

class TransferStatusViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user('status_user')
        self.client.login(username='status_user', password='pass123')
        self.job = TransferJob.objects.create(
            user=self.user,
            task_id='test-task-abc',
            status='running',
            playlist_count=5,
            processed_count=2,
        )

    def test_returns_correct_json_fields(self):
        response = self.client.get(reverse('transfer_status', args=['test-task-abc']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['state'], 'running')
        self.assertEqual(data['processed'], 2)
        self.assertEqual(data['total'], 5)

    def test_error_message_included_in_response(self):
        self.job.status = 'error'
        self.job.error_msg = 'Something went wrong'
        self.job.save()
        response = self.client.get(reverse('transfer_status', args=['test-task-abc']))
        data = response.json()
        self.assertEqual(data['error'], 'Something went wrong')

    def test_returns_404_for_another_users_job(self):
        other = make_user('other_user')
        TransferJob.objects.create(user=other, task_id='other-task-xyz', status='done')
        response = self.client.get(reverse('transfer_status', args=['other-task-xyz']))
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# View: transfer (Spotify → YouTube)
# ---------------------------------------------------------------------------

class TransferToYoutubeViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user('xfer_user')
        self.client.login(username='xfer_user', password='pass123')

    def test_get_request_shows_error_page(self):
        response = self.client.get(reverse('transfer'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid request method')

    def test_post_with_no_playlists_shows_error_page(self):
        response = self.client.post(reverse('transfer'), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No playlists selected')

    @patch('core.views.transfer_spotify_to_youtube_task.delay')
    def test_valid_post_creates_job_and_redirects(self, mock_delay):
        mock_result = MagicMock()
        mock_result.id = 'new-task-id-123'
        mock_delay.return_value = mock_result

        response = self.client.post(reverse('transfer'), {'playlists': ['pl1', 'pl2']})

        self.assertEqual(response.status_code, 302)
        mock_delay.assert_called_once_with(self.user.id, ['pl1', 'pl2'])
        self.assertTrue(TransferJob.objects.filter(task_id='new-task-id-123').exists())


# ---------------------------------------------------------------------------
# View: transfer_to_spotify (YouTube → Spotify)
# ---------------------------------------------------------------------------

class TransferToSpotifyViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user('xfer2_user')
        self.client.login(username='xfer2_user', password='pass123')

    def test_get_request_shows_error_page(self):
        response = self.client.get(reverse('transfer_to_spotify'))
        self.assertContains(response, 'Invalid request method')

    def test_post_with_no_playlists_shows_error_page(self):
        response = self.client.post(reverse('transfer_to_spotify'), {})
        self.assertContains(response, 'No playlists selected')

    @patch('core.views.transfer_youtube_to_spotify_task.delay')
    def test_valid_post_creates_job_and_redirects(self, mock_delay):
        mock_result = MagicMock()
        mock_result.id = 'yt-task-id-456'
        mock_delay.return_value = mock_result

        response = self.client.post(reverse('transfer_to_spotify'), {'playlists': ['ytpl1']})

        self.assertEqual(response.status_code, 302)
        mock_delay.assert_called_once_with(self.user.id, ['ytpl1'])
        self.assertTrue(TransferJob.objects.filter(task_id='yt-task-id-456').exists())


class EncryptedCharFieldTest(TestCase):
    def setUp(self):
        self.user = make_user('enc_user')
    
    def test_token_is_decrypted_correctly_on_read(self):
        SpotifyToken.objects.create(
            user = self.user,
            access_token = 'my_plain_token',
            refresh_token = 'my_plain_refresh',
        )
        token = SpotifyToken.objects.get(user=self.user)
        self.assertEqual(token.access_token, 'my_plain_token')
        self.assertEqual(token.refresh_token, 'my_plain_refresh')
    
    def test_token_is_encrypted_in_database(self):
        SpotifyToken.objects.create(
            user=self.user,
            access_token='my_plain_token',
            refresh_token='my_plain_refresh',
        )
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT access_token FROM core_spotify_token WHERE user_id = %s',
                [self.user.id]
            )
            raw_value = cursor.fetchone()[0]

        self.assertNotEqual(raw_value, 'my_plain_token')
        self.assertTrue(raw_value.startswith('gAAAA'))