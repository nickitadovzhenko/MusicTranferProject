from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup' , views.signup, name='signup'),
    path('email-verification/<str:uidb64>/<str:token>',
         views.email_verification, name='email-verification'),

    path('email-verification-sent', views.email_verification_sent,
         name='email-verification-sent'),

    path('email-verification-success', views.email_verification_success,
         name='email-verification-success'),

    path('email-verification-failed', views.email_verification_failed,
         name='email-verification-failed'),

    # LogIn/LogOut urls

    path('my-login', views.my_login, name='my-login'),

    path('user-logout', views.user_logout, name='user-logout'),

    path('dashboard', views.dashboard, name='dashboard'),

    path('store_selected_tracks/', views.store_selected_tracks, name='store_selected_tracks'),

    path('transfer', views.transfer_and_create_youtube_playlist, name='transfer'),

    path('transfer_to_spotify', views.transfer_and_create_spotify_playlist, name = 'transfer_to_spotify')
]
