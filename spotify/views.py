from django.shortcuts import render
from django.conf import settings
from core.models import Spotify_Token
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from random import randint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests


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
    except Spotify_Token.DoesNotExist:
        return render(request, 'error_page.html', {'error_message':"You need to connect your Spotify account first."})
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

@login_required
def disconnect_spotify(request):
    Spotify_Token.objects.filter(user=request.user).delete()
    return redirect('dashboard')