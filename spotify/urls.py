from django.urls import path
from . import views

urlpatterns = [
    path('redirect_spotify', views.redirect_to_spotify, name='spotify_redirect'),
    path('disconnect', views.disconnect_spotify, name='disconnect_spotify'),
    path('spotify_callback', views.handle_authorization_code, name='spotify_callback'),
    path('get_playlists_spotify', views.get_playlists, name='get_playlists'),
]