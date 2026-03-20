import requests
from django.conf import settings
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def get_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=[
            'https://www.googleapis.com/auth/youtube', 
            'https://www.googleapis.com/auth/youtube.readonly',
            'https://www.googleapis.com/auth/youtube.force-ssl'
        ]
    )

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def refresh_access_token(refresh_token, client_id, client_secret, youtube_credentials):
    url = 'https://oauth2.googleapis.com/token'
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    response = requests.post(url, data=data)
    if response.status_code == 200:
        new_access_token = response.json()['access_token']
        youtube_credentials.access_token = new_access_token
        youtube_credentials.save()
        return new_access_token
    else:
        raise Exception(f"Error refreshing YouTube token: {response.status_code}, {response.text}")

def get_youtube_service_from_credentials(youtube_credentials):
    # Depending on how outdated the token is, we might want to refresh it proactively,
    # but googleapiclient usually handles it if token_uri and client_secrets are present. 
    creds = Credentials(
        token=youtube_credentials.access_token,
        refresh_token=youtube_credentials.refresh_token,
        token_uri=youtube_credentials.token_uri,
        client_id=youtube_credentials.client_id,
        client_secret=youtube_credentials.client_secret,
        scopes=youtube_credentials.scopes
    )
    return build('youtube', 'v3', credentials=creds)
