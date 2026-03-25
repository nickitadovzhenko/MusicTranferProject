import logging

from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
import spotipy

from core.models import SpotifyToken, YouTubeCredentials
from spotify.services import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_valid_access_token,
)
from youtube.services import get_flow

logger = logging.getLogger(__name__)

@login_required
def redirect_to_spotify(request):
    return redirect(get_authorization_url())

@login_required
def handle_authorization_code(request):
    authorization_code = request.GET.get("code")
    token_response = exchange_code_for_tokens(
        authorization_code=authorization_code,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
    )
    if not token_response:
        return render(request, 'error_page.html', {'error_message': 'Failed to retrieve access token from Spotify.'})
    SpotifyToken.objects.update_or_create(
        user=request.user,
        defaults={
            'access_token': token_response['access_token'],
            'refresh_token': token_response['refresh_token'],
        },
    )
    return redirect('dashboard')

@login_required
def get_playlists(request):
    access_token = get_valid_access_token(request.user)
    sp = spotipy.Spotify(auth=access_token)
    playlists = sp.current_user_playlists()
    return render(request, "playlists.html", {"playlists": playlists['items']})

def authorize_youtube(request):
    flow = get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    request.session['state'] = state
    return redirect(authorization_url)

def youtube_callback(request):
    flow = get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    credentials = flow.credentials
    YouTubeCredentials.objects.update_or_create(
        user=request.user,
        defaults={
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'scopes': credentials.scopes,
        },
    )
    return redirect('home')