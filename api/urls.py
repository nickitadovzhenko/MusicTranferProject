from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    # path('login', views.login),
    # path('signup', views.signup),
    # path('test_token', views.test_token),
    path('redirect', views.redirect_to_spotify, name='spotify_redirect'),

    path('spotify_callback', views.handle_authorization_code, name='spotify_callback'),
    path('get_playlists_spotify', views.get_playlists, name='get_playlists'),

    path('authorize_youtube', views.authorize_youtube, name='authorize_youtube'),
    path('youtube_callback', views.youtube_callback, name='youtube_callback'),
]
