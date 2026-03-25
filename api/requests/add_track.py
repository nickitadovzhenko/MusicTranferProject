"""
Dev/test script — not used by the application at runtime.
Replace ACCESS_TOKEN with a valid token before running.
"""
import logging
import requests

logger = logging.getLogger(__name__)

PLAYLIST_ID = '2xl7GsFIJbTgHsY8DBGPSZ'
TRACK_URI = 'spotify:track:4iV5W9uYEdYUVa79Axb7Rh'
ACCESS_TOKEN = 'REPLACE_WITH_VALID_TOKEN'

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

data = {"uris": [TRACK_URI]}

response = requests.post(
    f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}/tracks",
    headers=headers,
    json=data,
)

if response.status_code == 201:
    logger.info("Track added to playlist successfully!")
else:
    logger.error("Error adding track: %s - %s", response.status_code, response.text)