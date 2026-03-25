import logging

from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from oauthlib.oauth2 import OAuth2Error

from core.models import YouTubeCredentials
from youtube.services import (
    get_flow,
    refresh_access_token,
    get_youtube_service_from_credentials,
)

logger = logging.getLogger(__name__)

# Create your views here.

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
        logger.error(f"OAuth2 error: {e}")
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
                'scopes': credentials.scopes
            }
        )
    except Exception as e:
        logger.error(f"Error saving YouTube credentials: {e}")
        return render(request, 'error_page.html', {'error_message': f"Error saving YouTube credentials: {e}"})
    return redirect('home')



def disconnect_youtube(request):
    YouTubeCredentials.objects.filter(user=request.user).delete()
    return redirect('dashboard')



@login_required
def get_youtube_playlists(request):
    youtube_credentials = YouTubeCredentials.objects.filter(user=request.user).first()
    if not youtube_credentials:
        return HttpResponse("YouTube credentials not found", status=400)

    def get_number_of_tracks(playlist_id, youtube_service):
        try:
            playlist_items_response = youtube_service.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=50
            ).execute()

            total_items = playlist_items_response.get('pageInfo', {}).get('totalResults', 0)
            return total_items
        except Exception as e:
            logger.error(f"Failed to retrieve number of tracks for playlist {playlist_id}. Error: {str(e)}")
            return 0

    try:
        # Refresh access token using refresh token from the database
        access_token = refresh_access_token(youtube_credentials.refresh_token, settings.GOOGLE_CLIENT_ID,
                                            settings.GOOGLE_CLIENT_SECRET, youtube_credentials)

        # Build YouTube service with the refreshed access token
        youtube_service = get_youtube_service_from_credentials(youtube_credentials)

        # Call YouTube API to retrieve playlists
        playlists_response = youtube_service.playlists().list(
            part='snippet',
            mine=True
        ).execute()

        playlists = playlists_response.get('items', [])
        playlist_info = [{'id': playlist['id'], 'title': playlist['snippet']['title']} for playlist in playlists]

        playlists_data = []
        for playlist in playlists:
            playlist_id = playlist['id']
            playlist_title = playlist['snippet']['title']
            playlist_image = playlist['snippet']['thumbnails']['default']['url']
            num_tracks = get_number_of_tracks(playlist_id, youtube_service)
            playlists_data.append({
                'title': playlist_title,
                'image_url': playlist_image,
                'num_tracks': num_tracks,
                'playlist_id': playlist_id
            })

        return render(request, 'youtube_playlists.html', {'playlists': playlists_data})
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        return HttpResponse(f"An unexpected error occurred. Error: {str(e)}", status=500)



