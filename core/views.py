from django.shortcuts import render, redirect, get_object_or_404
from googleapiclient.errors import HttpError

from .forms import CreateUserForm, LoginForm
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.decorators import login_required
from .token import user_tokenizer_generate
from django.contrib.auth.models import User
from django.conf import settings
from youtube.services import get_youtube_service_from_credentials
from random import randint
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.models import auth
from django.contrib.auth import authenticate
from django.contrib import messages
from .models import Spotify_Token, YouTubeCredentials, TransferJob
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotify.services import get_valid_access_token
from .tasks import transfer_spotify_to_youtube_task, transfer_youtube_to_spotify_task, transfer_spotify_to_spotify_task


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


@login_required
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
        access_token = get_valid_access_token(request.user)

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

        # Trigger Celery task
        result = transfer_spotify_to_youtube_task.delay(request.user.id, selected_playlist_ids)
        
        # Create TransferJob
        TransferJob.objects.create(
            user=request.user,
            task_id=result.id,
            playlist_count=len(selected_playlist_ids)
        )
        
        return redirect('transfer_progress', task_id=result.id)

    return render(request, 'error_page.html', {'error_message': 'Invalid request method'})

@login_required
def get_playlists_s2s(request):
    try:
        access_token = get_valid_access_token(request.user)
        sp = spotipy.Spotify(auth=access_token)
        playlists = sp.current_user_playlists()
        
        # Inject Liked Songs
        saved_tracks_info = sp.current_user_saved_tracks(limit=1)
        liked_songs = {
            'id': 'liked_songs',
            'name': 'Liked Songs',
            'images': [{'url': 'https://misc.scdn.co/liked-songs/liked-songs-300.png'}],
            'tracks': {'total': saved_tracks_info['total']}
        }
        all_playlists = [liked_songs] + playlists['items']
        
        return render(request, "transfer_s2s.html", {"playlists": all_playlists})
    except Exception as e:
        return render(request, 'error_page.html', {'error_message': str(e)})

@login_required
def transfer_spotify_to_spotify_init(request):
    if request.method == 'POST':
        selected_playlist_ids = request.POST.getlist('playlists')
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists selected'})
        
        request.session['s2s_playlists'] = selected_playlist_ids
        
        from spotify.services import get_authorization_url
        link = get_authorization_url(state="s2s", show_dialog=True)
        return redirect(link)
    return render(request, 'error_page.html', {'error_message': 'Invalid request method'})

@login_required
def transfer_and_create_spotify_playlist(request):
    if request.method == 'POST':
        selected_playlist_ids = request.POST.getlist('playlists')
        if not selected_playlist_ids:
            return render(request, 'error_page.html', {'error_message': 'No playlists selected'})

        # Trigger Celery task
        result = transfer_youtube_to_spotify_task.delay(request.user.id, selected_playlist_ids)
        
        # Create TransferJob
        TransferJob.objects.create(
            user=request.user,
            task_id=result.id,
            playlist_count=len(selected_playlist_ids)
        )
        
        return redirect('transfer_progress', task_id=result.id)

    return render(request, 'error_page.html', {'error_message': 'Invalid request method'})


@login_required
def transfer_progress(request, task_id):
    job = get_object_or_404(TransferJob, task_id=task_id, user=request.user)
    return render(request, 'transfer_progress.html', {'job': job})


@login_required
def transfer_status(request, task_id):
    job = get_object_or_404(TransferJob, task_id=task_id, user=request.user)
    return JsonResponse({
        'status': job.get_status_display(),
        'error': job.error_msg,
        'state': job.status,
        'processed': job.processed_count,
        'total': job.playlist_count
    })