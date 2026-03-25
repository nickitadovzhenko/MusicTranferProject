import base64
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

from django.contrib.auth.models import User


# Create your models here.


class EncryptedCharField(models.CharField):
    def _get_fernet(self):
        key = base64.urlsafe_b64encode(settings.SECRET_KEY.encode()[:32])
        return Fernet(key)

    def get_prep_value(self, value):
        if value is None:
            return value
        return self._get_fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value

        return self._get_fernet().decrypt(value.encode()).decode()






class SpotifyToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = EncryptedCharField(max_length=500)
    refresh_token = EncryptedCharField(max_length=500)

    class Meta:
        db_table = 'core_spotify_token'


# Backward-compat alias — remove once all references are updated to SpotifyToken
Spotify_Token = SpotifyToken


class YouTubeCredentials(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    refresh_token = EncryptedCharField(max_length=255)
    access_token = EncryptedCharField(max_length=255)
    token_uri = models.URLField()
    scopes = models.TextField()

    def __str__(self):
        return f"YouTube credentials for {self.user.username}"


class TransferJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default='pending')
    error_msg = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    playlist_count = models.IntegerField(default=0)
    processed_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Job {self.task_id} - {self.status}"


