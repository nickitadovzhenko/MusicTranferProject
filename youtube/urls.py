from django.urls import path
from . import views

urlpatterns = [
    path('authorize_youtube', views.authorize_youtube, name='authorize_youtube'),
    path('youtube_callback', views.youtube_callback, name='youtube_callback'),
    path('disconnect', views.disconnect_youtube, name='disconnect_youtube'),
    path('get_playlists_youtube', views.get_youtube_playlists, name='get_playlists_youtube')
]