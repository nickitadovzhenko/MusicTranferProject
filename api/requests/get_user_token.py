import requests

def exchange_code_for_tokens(authorization_code, redirect_uri, client_id, client_secret):
    """
    Exchanges the authorization code for access and refresh tokens.

    Args:
        authorization_code: The authorization code received from Spotify.
        redirect_uri: The redirect URI registered in your Spotify app settings.
        client_id: Your Spotify app's Client ID.
        client_secret: Your Spotify app's Client Secret (keep confidential).

    Returns:
        A dictionary containing the access token and refresh token, or None on error.
    """

    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error exchanging code: {response.status_code}")
        return None





