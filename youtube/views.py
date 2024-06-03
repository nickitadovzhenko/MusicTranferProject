from django.shortcuts import render
from django.conf import settings
from oauthlib.oauth2 import OAuth2Error

from core.models import YouTubeCredentials
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from random import randint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from google_auth_oauthlib.flow import Flow
from django.http import JsonResponse, HttpResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import googleapiclient

from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

import logging  # For logging errors


# Create your views here.

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
        scopes=['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/youtube.force-ssl']
    )


@login_required
def authorize_youtube(request):
    flow = get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    request.session['state'] = state
    return redirect(authorization_url)


@login_required
def youtube_callback(request):
    flow = get_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    try:
        flow.fetch_token(authorization_response=request.build_absolute_uri())
    except OAuth2Error as e:  # Catch OAuth2 errors
        logging.error(f"OAuth2 error: {e}")
        return render(request, 'error_page.html', {'error_message': f"OAuth2 Error: {e}"})
    credentials = flow.credentials
    user = request.user

    try:
        YouTubeCredentials.objects.update_or_create(
            user=user,
            defaults={
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
        )
    except Exception as e:
        logging.error(f"Error saving YouTube credentials: {e}")
        return render(request, 'error_page.html', {'error_message': f"Error saving YouTube credentials: {e}"})
    return redirect('home')


def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
            }


def disconnect_youtube(request):
    YouTubeCredentials.objects.filter(user=request.user).delete()
    return redirect('dashboard')


def get_youtube_service(credentials):
    # Load credentials
    creds = Credentials(
        token=credentials.access_token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        scopes=credentials.scopes
    )

    # Build the YouTube service
    service = build('youtube', 'v3', credentials=creds)
    return service


@login_required
def get_youtube_playlists(request):
    # Get YouTube credentials for the current user
    youtube_credentials = YouTubeCredentials.objects.filter(user=request.user).first()
    if not youtube_credentials:
        # Handle case where credentials are not available
        return HttpResponse("YouTube credentials not found", status=400)

    def get_number_of_tracks(playlist_id, youtube_service):
        try:
            # Call the playlistItems.list method to retrieve items in the playlist
            playlist_items_response = youtube_service.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=50  # Max number of items per request
            ).execute()

            # Count the number of items (tracks) in the playlist
            total_items = playlist_items_response.get('pageInfo', {}).get('totalResults', 0)
            return total_items

        except Exception as e:
            # Handle exceptions
            print(f"Failed to retrieve number of tracks for playlist {playlist_id}. Error: {str(e)}")
            return 0

    # Get the YouTube API service
    youtube_service = get_youtube_service(youtube_credentials)

    try:
        # Call the playlists.list method to retrieve playlists
        playlists_response = youtube_service.playlists().list(
            part='snippet',
            mine=True
        ).execute()

        # Extract playlist information from the response
        playlists = playlists_response.get('items', [])
        playlist_info = [{'id': playlist['id'], 'title': playlist['snippet']['title']} for playlist in playlists]

        playlists_data = []
        for playlist in playlists:
            playlist_id = playlist['id']
            playlist_title = playlist['snippet']['title']
            playlist_image = playlist['snippet']['thumbnails']['default']['url']
            num_tracks = get_number_of_tracks(playlist_id,
                                              youtube_service)  # Assume you have a function to get the number of tracks
            playlists_data.append({'title': playlist_title, 'image_url': playlist_image, 'num_tracks': num_tracks})

        # Render the template with playlist information
        return render(request, 'youtube_playlists.html', {'playlists': playlists_data})

    except Exception as e:
        # Handle exceptions
        return HttpResponse(f"Failed to retrieve playlists. Error: {str(e)}", status=500)
