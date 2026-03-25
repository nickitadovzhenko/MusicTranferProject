import secrets
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from django.conf import settings
from core.models import SpotifyToken, YouTubeCredentials

def get_authorization_url(state=None, show_dialog=False):
    client_id = settings.SPOTIFY_CLIENT_ID
    redirect_uri = settings.SPOTIFY_REDIRECT_URI
    scope = "playlist-read-private playlist-modify-public playlist-modify-private user-library-read user-library-modify"
    if state is None:
        state = secrets.token_urlsafe(16)
    url = f"https://accounts.spotify.com/authorize?" \
          f"client_id={client_id}" \
          f"&response_type=code" \
          f"&redirect_uri={redirect_uri}" \
          f"&scope={scope}" \
          f"&state={state}"
    if show_dialog:
        url += "&show_dialog=true"
    return url

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
    return None

def exchange_refresh_token_for_tokens(refresh_token, client_id, client_secret):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    response = requests.post(url, data=data, auth=(client_id, client_secret))
    if response.status_code != 200:
        raise Exception(f"Failed to refresh Spotify token: {response.status_code}")
    return response.json()

def is_token_valid(access_token):
    sp = spotipy.Spotify(auth=access_token)
    try:
        sp.current_user()
        return True
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return False
        raise e

def get_valid_access_token(user):
    try:
        spotify_token = SpotifyToken.objects.get(user=user)
        access_token = spotify_token.access_token
        if is_token_valid(access_token):
            return access_token
        else:
            refresh_token = spotify_token.refresh_token
            token_response = exchange_refresh_token_for_tokens(
                refresh_token, settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET
            )
            new_access_token = token_response['access_token']
            spotify_token.access_token = new_access_token
            spotify_token.save()
            return new_access_token
    except SpotifyToken.DoesNotExist:
        raise Exception("You need to connect your Spotify account first.")

def get_spotify_client(user):
    access_token = get_valid_access_token(user)
    return spotipy.Spotify(auth=access_token)
