import requests


def get_user_code(client_id, redirect_uri):

    authorize_url = 'https://accounts.spotify.com/authorize'
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'playlist-read-private',
        'state': 'RANDOM_VALUE'
    }
    response = requests.get(authorize_url, params=params)

    return response