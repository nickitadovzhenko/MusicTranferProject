from django.shortcuts import render
from django.conf import settings
from core.models import Spotify_Token, YouTubeCredentials
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from random import randint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests


def get_authorization_url(state=None, show_dialog=False):
    client_id = settings.SPOTIFY_CLIENT_ID  # Replace with your Client ID
    redirect_uri = settings.SPOTIFY_REDIRECT_URI  # Replace with your redirect URI
    scope = "playlist-read-private playlist-modify-public playlist-modify-private user-library-read user-library-modify"  # Replace with your scope
    if state is None:
        state = str(randint(1, 100))  # Function to generate random string
    url = f"https://accounts.spotify.com/authorize?" \
          f"client_id={client_id}" \
          f"&response_type=code" \
          f"&redirect_uri={redirect_uri}" \
          f"&scope={scope}" \
          f"&state={state}"
    if show_dialog:
        url += "&show_dialog=true"
    return url


@login_required
def redirect_to_spotify(request):
    link = get_authorization_url()
    return redirect(link)


def exchange_code_for_tokens(authorization_code, redirect_uri, client_id, client_secret):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error exchanging code: {response.status_code}")
        return None


@login_required
def handle_authorization_code(request):
    error = request.GET.get("error")
    if error:
        return render(request, 'error_page.html', {'error_message': f'Spotify authorization failed: {error}'})

    authorization_code = request.GET.get("code")
    state = request.GET.get("state")  # Optional for security
    token_response = exchange_code_for_tokens(
        authorization_code=authorization_code, redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET)

    if not token_response:
        return render(request, 'error_page.html', {'error_message': 'Failed to retrieve access token from Spotify.'})

    if state == "s2s":
        selected_playlist_ids = request.session.get('s2s_playlists', [])
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists found in session for transfer'})
        
        try:
            source_access_token = get_authorization(request)
            sp_source = spotipy.Spotify(auth=source_access_token)
            
            dest_access_token = token_response['access_token']
            sp_dest = spotipy.Spotify(auth=dest_access_token)
            dest_user = sp_dest.me()['id']
            
            for spotify_playlist_id in selected_playlist_ids:
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
                while results['next']:
                    results = sp_source.next(results)
                    tracks.extend(results['items'])
                
                track_uris = []
                for track in tracks:
                    track_obj = track.get('track')
                    if track_obj and track_obj.get('uri'):
                        # Spotify API rejects local tracks with 'Unsupported URI'
                        if not track_obj.get('is_local', False):
                            track_uris.append(track_obj['uri'])
                
                if is_liked_songs:
                    # Add to saved tracks in chunks of 50
                    for i in range(0, len(track_uris), 50):
                        sp_dest.current_user_saved_tracks_add(tracks=track_uris[i:i+50])
                else:
                    for i in range(0, len(track_uris), 100):
                        sp_dest.playlist_add_items(playlist_id=new_playlist['id'], items=track_uris[i:i+100])
                    
            if 's2s_playlists' in request.session:
                del request.session['s2s_playlists']
            return render(request, "success.html")
            
        except Exception as e:
            import logging
            logging.error(f"S2S Transfer Error: {e}")
            return render(request, 'error_page.html', {'error_message': f"S2S Transfer Error: {e}"})

    user = request.user
    Spotify_Token.objects.update_or_create(
        user=user,
        defaults={
            'access_token': token_response['access_token'],
            'refresh_token': token_response['refresh_token']
        }
    )
    return render(request, "success.html")


def exchange_refresh_token_for_tokens(request, refresh_token, client_id, client_secret):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    response = requests.post(url, data=data, auth=(client_id, client_secret))
    token_response = response.json()
    return token_response


@login_required
def get_playlists(request):
    try:
        access_token = get_authorization(request)
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
        access_token = get_authorization(request)
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


def is_token_valid(access_token):
    sp = spotipy.Spotify(auth=access_token)
    try:
        sp.current_user()  # This endpoint requires authentication and will fail if the token is invalid
        return True
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return False
        else:
            raise e  # Raise other exceptions that are not related to invalid token


def get_authorization(request):
    try:
        spotify_token = Spotify_Token.objects.get(user=request.user)
        access_token = spotify_token.access_token
        
        if is_token_valid(access_token):
            return access_token
        else:
            refresh_token = spotify_token.refresh_token
            token_response = exchange_refresh_token_for_tokens(request, refresh_token, settings.SPOTIFY_CLIENT_ID,
                                                               settings.SPOTIFY_CLIENT_SECRET)
            access_token = token_response['access_token']
            spotify_token.access_token = access_token
            spotify_token.save()
            return access_token
    except Spotify_Token.DoesNotExist:
        raise Exception("You need to connect your Spotify account first.")
