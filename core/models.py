from django.db import models
from django.contrib.auth.models import User
from django_cryptography.fields import encrypt


# Create your models here.

class Spotify_Token(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = encrypt(models.CharField(max_length=500))
    refresh_token = encrypt(models.CharField(max_length=500))




class YouTubeCredentials(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    refresh_token = encrypt(models.CharField(max_length=255))
    access_token = encrypt(models.CharField(max_length=255))
    token_uri = models.URLField()
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()

    def __str__(self):
        return f"YouTube credentials for {self.user.username}"
