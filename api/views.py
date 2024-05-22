from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from core.models import Spotify_Token, YouTubeCredentials
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from random import randint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from google_auth_oauthlib.flow import Flow
# Create your views here.

# @api_view(['POST'])
# def login(request):
#     return Response({})


# @api_view(['POST'])
# def signup(request):
#     return Response({})


# @api_view(['GET'])
# def test_token(request):
#     return Response({})

def get_authorization_url():
    client_id = settings.SPOTIFY_CLIENT_ID  # Replace with your Client ID
    redirect_uri = settings.SPOTIFY_REDIRECT_URI  # Replace with your redirect URI
    scope = "playlist-read-private"  # adjust scope as needed
    state = randint(1, 100)  # Function to generate random string
    url = f"https://accounts.spotify.com/authorize?" \
        f"client_id={client_id}" \
        f"&response_type=code" \
        f"&redirect_uri={redirect_uri}" \
        f"&scope={scope}" \
        f"&state={state}"
    print(client_id)
    print(redirect_uri)
    return url


@login_required
def redirect_to_spotify(request):
    link = get_authorization_url()
    return redirect(link)


def exchange_code_for_tokens(authorization_code, redirect_uri, client_id, client_secret):
    """
    Exchanges the authorization code for access and refresh tokens.

    Args:
        authorization_code: The authorization code received from Spotify.
        redirect_uri: The redirect URI registered in your Spotify app settings.
        client_id: Your Spotify app's Client ID.
        client_secret: Your Spotify app's Client Secret (keep confidential).

    Returns:
        A dictionary containing the access token and refresh token, or None on error.
    """

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
    authorization_code = request.GET.get("code")
    state = request.GET.get("state")  # Optional for security
    print(authorization_code)
    token_response = exchange_code_for_tokens(
        authorization_code=authorization_code, redirect_uri=settings.SPOTIFY_REDIRECT_URI, client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET)

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
    print(token_response)
    return token_response


@login_required
def get_playlists(request):
    sp_oauth = SpotifyOAuth(client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET,
                            redirect_uri=settings.SPOTIFY_REDIRECT_URI, scope='playlist-read-private')

    # Get access token and refresh token
    try:
        access_token = Spotify_Token.objects.get(
            user=request.user).access_token
        sp = spotipy.Spotify(auth=access_token)

        # Get user's playlists
        playlists = sp.current_user_playlists()
    except:
        # Handle case where access token is not available
        refresh_token = Spotify_Token.objects.get(
            user=request.user).refresh_token
        token_response = exchange_refresh_token_for_tokens(
            request, refresh_token, settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET)
        access_token = token_response['access_token']
        Spotify_Token.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': access_token,
            }
        )
        sp = spotipy.Spotify(auth=access_token)

        # Get user's playlists
        playlists = sp.current_user_playlists()

    # Print user's playlists
    return render(request, "C:/Users/nick/Documents/GitHub/MusicTranferProject/core/templates/playlists.html", {"playlists": playlists['items']})


def get_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=['https://www.googleapis.com/auth/youtube.readonly']
    )


def authorize_youtube(request):
    print(settings.GOOGLE_REDIRECT_URI)
    flow = get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    request.session['state'] = state
    return redirect(authorization_url)

def youtube_callback(request):
    flow=get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    flow.fetch_token(authorization_response = request.build_absolute_uri())
    credentials = flow.credentials
    user = request.user
    YouTubeCredentials.objects.update_or_create(
        user=user,
        defaults={
            'access_token': credentials.token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
    )
    return redirect('home')

def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
            }