from django.shortcuts import render
from django.conf import settings
from core.models import Spotify_Token, YouTubeCredentials
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from random import randint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from spotify.services import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_valid_access_token
)


@login_required
def redirect_to_spotify(request):
    link = get_authorization_url()
    return redirect(link)


@login_required
def handle_authorization_code(request):
    error = request.GET.get("error")
    if error:
        return render(request, 'error_page.html', {'error_message': f'Spotify authorization failed: {error}'})

    authorization_code = request.GET.get("code")
    state = request.GET.get("state")
    token_response = exchange_code_for_tokens(
        authorization_code=authorization_code, 
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        client_id=settings.SPOTIFY_CLIENT_ID, 
        client_secret=settings.SPOTIFY_CLIENT_SECRET
    )

    if not token_response:
        return render(request, 'error_page.html', {'error_message': 'Failed to retrieve access token from Spotify.'})

    if state == "s2s":
        selected_playlist_ids = request.session.get('s2s_playlists', [])
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists found in session for transfer'})
        
        from core.tasks import transfer_spotify_to_spotify_task
        from core.models import TransferJob
        
        # Trigger Celery task
        result = transfer_spotify_to_spotify_task.delay(
            request.user.id, 
            selected_playlist_ids, 
            token_response['access_token']
        )
        
        # Create TransferJob
        TransferJob.objects.create(
            user=request.user,
            task_id=result.id,
            playlist_count=len(selected_playlist_ids)
        )
        
        if 's2s_playlists' in request.session:
            del request.session['s2s_playlists']
            
        return redirect('transfer_progress', task_id=result.id)

    user = request.user
    Spotify_Token.objects.update_or_create(
        user=user,
        defaults={
            'access_token': token_response['access_token'],
            'refresh_token': token_response['refresh_token']
        }
    )
    return redirect('dashboard')


@login_required
def get_playlists(request):
    try:
        access_token = get_valid_access_token(request.user)
        sp = spotipy.Spotify(auth=access_token)
        playlists = sp.current_user_playlists()
        
        saved_tracks_info = sp.current_user_saved_tracks(limit=1)
        liked_songs = {
            'id': 'liked_songs',
            'name': 'Liked Songs',
            'images': [{'url': 'https://misc.scdn.co/liked-songs/liked-songs-300.png'}],
            'tracks': {'total': saved_tracks_info['total']}
        }
        all_playlists = [liked_songs] + playlists['items']
        
        return render(request, "playlists.html", {"playlists": all_playlists})
    except Exception as e:
        return render(request, 'error_page.html', {'error_message': str(e)})


@login_required
def disconnect_spotify(request):
    Spotify_Token.objects.filter(user=request.user).delete()
    return redirect('dashboard')


@login_required
def list_tracks(request, playlist_id):
    try:
        access_token = get_valid_access_token(request.user)
        sp = spotipy.Spotify(auth=access_token)
        
        if playlist_id == 'liked_songs':
            results = sp.current_user_saved_tracks()
        else:
            results = sp.playlist_items(
                playlist_id, fields="items.track.name,items.track.artists.name,total", additional_types=["track"]
            )
            
        tracks = results['items']
        
        # Handle pagination only if 'next' key exists
        while results.get('next'):  # Check if 'next' key is present
            results = sp.next(results)
            tracks.extend(results['items'])

        # Transform the data for easier display in the template
        formatted_tracks = [
            {
                'name': track['track']['name'],
                'artists': ', '.join([artist['name'] for artist in track['track']['artists']]),
            }
            for track in tracks if track['track'] is not None  # Handle potential null tracks
        ]
        return render(request, 'playlist_tracks.html', {'playlist_id': playlist_id, 'tracks': formatted_tracks})
    except Exception as e:
        return render(request, 'error_page.html', {'error_message': 'Error fetching playlist tracks: ' + str(e)})
