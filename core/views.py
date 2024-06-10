import logging

from django.shortcuts import render, redirect
from googleapiclient.errors import HttpError

from .forms import CreateUserForm, LoginForm
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.decorators import login_required
from .token import user_tokenizer_generate
from django.contrib.auth.models import User
from django.conf import settings
from youtube.views import get_youtube_service
from random import randint
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.models import auth
from django.contrib.auth import authenticate
from django.contrib import messages
from .models import Spotify_Token, YouTubeCredentials
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from api.requests.get_user_token import exchange_code_for_tokens
from spotify.views import get_authorization


# Create your views here.


def home(request):
    return render(request, 'index.html')


def login(request):
    return render(request, 'login.html')


def signup(request):
    form = CreateUserForm()

    if request.method == 'POST':
        form = CreateUserForm(request.POST)

        if form.is_valid():
            user = form.save()

            user.is_active = False

            user.save()

            # Email verification setup

            current_site = get_current_site(request)

            subject = 'Account verification email'

            message = render_to_string('registration/email-verification.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': user_tokenizer_generate.make_token(user),
            })

            user.email_user(subject=subject, message=message)

            return redirect('email-verification-sent')

    context = {'form': form}

    return render(request, 'registration/signup.html', context)


def email_verification(request, uidb64, token):
    unique_id = force_str(urlsafe_base64_decode(uidb64))
    user = User.objects.get(pk=unique_id)

    # Success
    if user and user_tokenizer_generate.check_token(user, token):

        user.is_active = True

        user.save()

        return redirect('email-verification-success')

    # Failed

    else:
        return redirect('email-verification-failed')


def email_verification_sent(request):
    return render(request, 'registration/email-verification-sent.html')


def email_verification_success(request):
    return render(request, 'registration/email-verification-success.html')


def email_verification_failed(request):
    return render(request, 'registration/email-verification-failed.html')


def my_login(request):
    form = LoginForm()

    if request.method == 'POST':

        form = LoginForm(request, data=request.POST)

        if form.is_valid():

            username = request.POST.get('username')
            password = request.POST.get('password')

            user = authenticate(request, username=username, password=password)

            if user is not None:
                auth.login(request, user)

                return redirect('home')

    context = {'form': form}

    return render(request, 'my-login.html', context)


def user_logout(request):
    try:
        for key in list(request.session.keys()):
            if key == 'session_key':

                continue
            else:
                del request.session[key]

    except KeyError:
        pass

    messages.success(request, "Logout success")
    return redirect("home")


def dashboard(request):
    if Spotify_Token.objects.filter(user=request.user):
        spoti_status = 'connected'
    else:
        spoti_status = 'no_connection'
    if YouTubeCredentials.objects.filter(user=request.user):
        youtube_status = 'connected'
    else:
        youtube_status = 'no_connection'
    return render(request, 'dashboard.html', {"spoti_status": spoti_status, "youtube_status": youtube_status})


@login_required
@csrf_exempt
def store_selected_tracks(request):
    if request.method == 'POST':
        selected_playlists = request.POST.getlist('playlists')  # Extract selected playlists
        all_tracks = []

        # Get access token for Spotify API
        access_token = get_authorization(request)

        sp = spotipy.Spotify(auth=access_token)

        for playlist_id in selected_playlists:
            results = sp.playlist_items(playlist_id, fields="items.track.name,items.track.artists.name,total",
                                        additional_types=["track"])
            tracks = results['items']

            while results.get('next'):
                results = sp.next(results)
                tracks.extend(results['items'])

            formatted_tracks = [
                {
                    'name': track['track']['name'],
                    'artists': ', '.join([artist['name'] for artist in track['track']['artists']]),
                    'playlist_id': playlist_id
                }
                for track in tracks if track['track'] is not None
            ]

            all_tracks.extend(formatted_tracks)

        # Store tracks in the session or database as needed
        print(all_tracks)

        return JsonResponse({'status': 'success', 'message': 'Tracks stored successfully.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@login_required
def transfer_and_create_youtube_playlist(request):
    if request.method == 'POST':
        selected_playlist_ids = request.POST.getlist('playlists')
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists selected'})

        try:
            spotify_token = Spotify_Token.objects.get(user=request.user)
            youtube_credentials = YouTubeCredentials.objects.get(user=request.user)
        except (Spotify_Token.DoesNotExist, YouTubeCredentials.DoesNotExist) as e:
            return render(request, 'error_page.html', {'error_message': str(e)})

        sp = spotipy.Spotify(auth=spotify_token.access_token)
        youtube_service = get_youtube_service(youtube_credentials)

        for spotify_playlist_id in selected_playlist_ids:
            spotify_playlist = sp.playlist(spotify_playlist_id)

            # Create YouTube playlist (add error handling)
            try:
                playlist_snippet = {
                    'title': spotify_playlist['name'],
                    'description': f"Transferred from Spotify playlist: {spotify_playlist['external_urls']['spotify']}",
                }
                playlist_status = {'privacyStatus': 'public'}
                request_body = {"snippet": playlist_snippet, "status": playlist_status}
                response = youtube_service.playlists().insert(part="snippet,status", body=request_body).execute()
                youtube_playlist_id = response['id']
            except HttpError as e:
                logging.error(f"An error occurred creating a playlist: {e}")
                return render(request, 'error_page.html', {'error_message': 'Error creating playlist'})

            # Fetch Spotify playlist tracks and add to YouTube (with error handling)
            try:
                results = sp.playlist_tracks(spotify_playlist_id)
                tracks = results['items']

                while results['next']:
                    results = sp.next(results)
                    tracks.extend(results['items'])

                for track in tracks:
                    track_name = track['track']['name']
                    artist_name = track['track']['artists'][0]['name']

                    # Search YouTube for the track
                    search_response = youtube_service.search().list(
                        q=f"{track_name} {artist_name}",
                        part="id",
                        type="video",
                        maxResults=1
                    ).execute()

                    if search_response['items']:
                        video_id = search_response['items'][0]['id']['videoId']

                        # Add video to the YouTube playlist
                        playlist_item_snippet = {
                            'playlistId': youtube_playlist_id,
                            'resourceId': {
                                'kind': 'youtube#video',
                                'videoId': video_id
                            }
                        }
                        request = youtube_service.playlistItems().insert(
                            part="snippet", body={"snippet": playlist_item_snippet}
                        )
                        response = request.execute()
            except Exception as e:  # Catch more general exceptions during track transfer
                logging.error(f"An error occurred transferring tracks: {e}")
                return render(request, 'error_page.html', {'error_message': 'Error transferring tracks'})

        return redirect('get_playlists_youtube')

    return render(request, 'error_page.html', {'error_message': 'Invalid request method'})


@login_required
def transfer_and_create_spotify_playlist(request):
    if request.method == 'POST':
        selected_playlist_ids = request.POST.getlist('playlists')
        print(selected_playlist_ids)
        # Check if any playlists were selected
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists selected'})

        # Get Spotify and YouTube credentials
        try:
            spotify_token = Spotify_Token.objects.get(user=request.user)
            youtube_credentials = YouTubeCredentials.objects.get(user=request.user)
        except (Spotify_Token.DoesNotExist, YouTubeCredentials.DoesNotExist) as e:
            return render(request, 'error_page.html', {'error_message': str(e)})

        sp = spotipy.Spotify(auth=spotify_token.access_token)
        youtube_service = get_youtube_service(youtube_credentials)

        for youtube_playlist_id in selected_playlist_ids:
            # Get YouTube playlist details (add error handling)
            try:
                request = youtube_service.playlists().list(
                    part="snippet",
                    id=youtube_playlist_id
                )
                response = request.execute()

                if not response['items']:
                    logging.warning(f"YouTube playlist not found: {youtube_playlist_id}")
                    continue  # Skip to the next playlist if not found

                youtube_playlist = response['items'][0]
            except HttpError as e:
                logging.error(f"An error occurred fetching playlist details: {e}")
                return render(request, 'error_page.html', {'error_message': 'Error fetching YouTube playlist details'})

            # Create Spotify playlist with the same name (add error handling)
            try:
                spotify_playlist = sp.user_playlist_create(
                    user=sp.me()['id'],
                    name=youtube_playlist['snippet']['title'],
                    public=True,  # You can set this to False for a private playlist
                    description=f"Transferred from YouTube playlist: {youtube_playlist['snippet']['title']}"
                )
                spotify_playlist_id = spotify_playlist['id']
            except Exception as e:
                logging.error(f"An error occurred creating Spotify playlist: {e}")
                return render(request, 'error_page.html', {'error_message': 'Error creating Spotify playlist'})

            # Fetch YouTube playlist tracks and add to Spotify (with error handling)
            try:
                request = youtube_service.playlistItems().list(
                    part="snippet",
                    playlistId=youtube_playlist_id,
                    maxResults=50  # Adjust as needed
                )
                response = request.execute()
                youtube_playlist_items = response['items']

                while response.get('nextPageToken'):
                    request = youtube_service.playlistItems().list(
                        part="snippet",
                        playlistId=youtube_playlist_id,
                        maxResults=50,
                        pageToken=response['nextPageToken']
                    )
                    response = request.execute()
                    youtube_playlist_items.extend(response['items'])

                track_uris = []
                for item in youtube_playlist_items:
                    video_id = item['snippet']['resourceId']['videoId']
                    video_title = item['snippet']['title']

                    # Search Spotify for the track
                    search_results = sp.search(q=video_title, type='track', limit=1)
                    if search_results['tracks']['items']:
                        track_uris.append(search_results['tracks']['items'][0]['uri'])

                if track_uris:
                    sp.playlist_add_items(playlist_id=spotify_playlist_id, items=track_uris)

            except Exception as e:
                logging.error(f"An error occurred transferring tracks: {e}")
                return render(request, 'error_page.html', {'error_message': 'Error transferring tracks'})

        return redirect('get_playlists')

    return render(request, 'error_page.html', {'error_message': 'Invalid request method'})