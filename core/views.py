from django.shortcuts import render, redirect
from .forms import CreateUserForm, LoginForm
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.decorators import login_required
from .token import user_tokenizer_generate
from django.contrib.auth.models import User
from django.conf import settings

from random import randint
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.auth.models import auth
from django.contrib.auth import authenticate
from django.contrib import messages
from .models import Spotify_Token, YouTubeCredentials

from api.requests.get_user_token import exchange_code_for_tokens



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
    if Spotify_Token.objects.filter(user = request.user):
        spoti_status = 'connected'
    else:
        spoti_status = 'no_connection'
    if YouTubeCredentials.objects.filter(user = request.user):
        youtube_status = 'connected'
    else:
        youtube_status = 'no_connection'
    return render(request, 'dashboard.html', {"spoti_status":spoti_status,  "youtube_status":youtube_status})



