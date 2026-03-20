import logging
from celery import shared_task
from django.contrib.auth.models import User
import spotipy
from googleapiclient.errors import HttpError
from youtube.services import get_youtube_service_from_credentials
from spotify.services import get_valid_access_token
from core.models import TransferJob

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def transfer_spotify_to_youtube_task(self, user_id, playlist_ids):
    user = User.objects.get(pk=user_id)
    job = TransferJob.objects.filter(task_id=self.request.id).first()
    if not job:
        job = TransferJob.objects.create(user=user, task_id=self.request.id, playlist_count=len(playlist_ids))
    
    try:
        job.status = 'running'
        job.save()

        access_token = get_valid_access_token(user)
        sp = spotipy.Spotify(auth=access_token)
        youtube_service = get_youtube_service_from_credentials(user)

        for spotify_playlist_id in playlist_ids:
            if spotify_playlist_id == 'liked_songs':
                results = sp.current_user_saved_tracks()
                playlist_name = "Spotify Liked Songs"
            else:
                source_playlist = sp.playlist(spotify_playlist_id)
                playlist_name = source_playlist['name']
                results = sp.playlist_tracks(spotify_playlist_id)

            request_body = {
                'snippet': {
                    'title': f"Transferred: {playlist_name}",
                    'description': "Playlist transferred from Spotify using Streamify.",
                    'tags': ['Spotify', 'Streamify', 'Transfer']
                },
                'status': {'privacyStatus': 'public'}
            }
            response = youtube_service.playlists().insert(part="snippet,status", body=request_body).execute()
            youtube_playlist_id = response['id']

            # Update progress
            job.processed_count += 1
            job.save()

            tracks = results['items']
            while results['next']:
                results = sp.next(results)
                tracks.extend(results['items'])

            for track in tracks:
                track_obj = track.get('track')
                if not track_obj: continue
                track_name = track_obj['name']
                artist_name = track_obj['artists'][0]['name']
                query = f"{track_name} {artist_name}"

                search_response = youtube_service.search().list(
                    q=query, part="id", maxResults=1, type="video"
                ).execute()

                if search_response['items']:
                    video_id = search_response['items'][0]['id']['videoId']
                    playlist_item_snippet = {
                        'playlistId': youtube_playlist_id,
                        'resourceId': {
                            'kind': 'youtube#video',
                            'videoId': video_id
                        }
                    }
                    youtube_service.playlistItems().insert(
                        part="snippet", body={"snippet": playlist_item_snippet}
                    ).execute()
        
        job.status = 'done'
        job.save()
    except Exception as e:
        job.status = 'error'
        job.error_msg = str(e)
        job.save()
        logger.error(f"Error in transfer_spotify_to_youtube_task: {e}")

@shared_task(bind=True)
def transfer_youtube_to_spotify_task(self, user_id, playlist_ids):
    user = User.objects.get(pk=user_id)
    job = TransferJob.objects.filter(task_id=self.request.id).first()
    if not job:
        job = TransferJob.objects.create(user=user, task_id=self.request.id, playlist_count=len(playlist_ids))
    
    try:
        job.status = 'running'
        job.save()

        access_token = get_valid_access_token(user)
        sp = spotipy.Spotify(auth=access_token)
        youtube_service = get_youtube_service_from_credentials(user)
        spotify_user_id = sp.me()['id']

        for youtube_playlist_id in playlist_ids:
            playlist_response = youtube_service.playlists().list(
                part="snippet", id=youtube_playlist_id
            ).execute()
            
            if not playlist_response['items']: continue
            playlist_title = playlist_response['items'][0]['snippet']['title']

            new_playlist = sp.user_playlist_create(
                user=spotify_user_id,
                name=f"Transferred: {playlist_title}",
                public=True,
                description="Playlist transferred from YouTube using Streamify."
            )
            spotify_playlist_id = new_playlist['id']

            playlist_items_request = youtube_service.playlistItems().list(
                part="snippet", playlistId=youtube_playlist_id, maxResults=50
            )
            
            track_uris = []
            while playlist_items_request:
                playlist_items_response = playlist_items_request.execute()
                for item in playlist_items_response['items']:
                    video_title = item['snippet']['title']
                    search_results = sp.search(q=video_title, type='track', limit=1)
                    if search_results['tracks']['items']:
                        track_uris.append(search_results['tracks']['items'][0]['uri'])
                playlist_items_request = youtube_service.playlistItems().list_next(playlist_items_request, playlist_items_response)

            if track_uris:
                for i in range(0, len(track_uris), 100):
                    sp.playlist_add_items(playlist_id=spotify_playlist_id, items=track_uris[i:i+100])

            # Update progress
            job.processed_count += 1
            job.save()

        job.status = 'done'
        job.save()
    except Exception as e:
        job.status = 'error'
        job.error_msg = str(e)
        job.save()
        logger.error(f"Error in transfer_youtube_to_spotify_task: {e}")

@shared_task(bind=True)
def transfer_spotify_to_spotify_task(self, user_id, playlist_ids, dest_access_token):
    user = User.objects.get(pk=user_id)
    job = TransferJob.objects.filter(task_id=self.request.id).first()
    if not job:
        job = TransferJob.objects.create(user=user, task_id=self.request.id, playlist_count=len(playlist_ids))
    
    try:
        job.status = 'running'
        job.save()

        source_access_token = get_valid_access_token(user)
        sp_source = spotipy.Spotify(auth=source_access_token)
        sp_dest = spotipy.Spotify(auth=dest_access_token)
        dest_user = sp_dest.me()['id']

        for spotify_playlist_id in playlist_ids:
            is_liked_songs = (spotify_playlist_id == 'liked_songs')

            if is_liked_songs:
                results = sp_source.current_user_saved_tracks()
            else:
                source_playlist = sp_source.playlist(spotify_playlist_id)
                source_playlist_name = source_playlist['name']
                results = sp_source.playlist_tracks(spotify_playlist_id)
                
                new_playlist = sp_dest.user_playlist_create(
                    user=dest_user,
                    name=source_playlist_name,
                    public=True,
                    description=f"Transferred from another Spotify account: {source_playlist_name}"
                )

            tracks = results['items']
            while results.get('next'):
                results = sp_source.next(results)
                tracks.extend(results['items'])
            
            track_uris = []
            for track in tracks:
                track_obj = track.get('track')
                if track_obj and track_obj.get('uri') and not track_obj.get('is_local', False):
                    track_uris.append(track_obj['uri'])
            
            if is_liked_songs:
                for i in range(0, len(track_uris), 50):
                    sp_dest.current_user_saved_tracks_add(tracks=track_uris[i:i+50])
            else:
                for i in range(0, len(track_uris), 100):
                    sp_dest.playlist_add_items(playlist_id=new_playlist['id'], items=track_uris[i:i+100])

            # Update progress
            job.processed_count += 1
            job.save()

        job.status = 'done'
        job.save()
    except Exception as e:
        job.status = 'error'
        job.error_msg = str(e)
        job.save()
        logger.error(f"Error in transfer_spotify_to_spotify_task: {e}")
