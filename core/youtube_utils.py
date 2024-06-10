# core/youtube_utils.py

import requests
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from core.models import YouTubeCredentials


def refresh_youtube_access_token(client_id, client_secret, refresh_token):
    url = 'https://oauth2.googleapis.com/token'
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        return response.json()['access_token']
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def get_youtube_service(credentials, user):
    try:
        creds = Credentials(
            token=credentials.access_token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            scopes=credentials.scopes
        )

        if creds.expired and creds.refresh_token:
            logging.info("Refreshing YouTube credentials")
            access_token = refresh_youtube_access_token(credentials.client_id, credentials.client_secret,
                                                        credentials.refresh_token)
            credentials.access_token = access_token
            credentials.save()

        service = build('youtube', 'v3', credentials=creds)
        return service
    except Exception as e:
        logging.error(f"Error getting YouTube service: {e}")
        raise e
