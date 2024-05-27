import requests

playlist_id = '2xl7GsFIJbTgHsY8DBGPSZ'
track_uri = 'spotify:track:4iV5W9uYEdYUVa79Axb7Rh'
access_token = 'BQDy2eQJC_khNXFFw3dgHZkvhT5jxdEnJbxQWXyQkpPvB3sIQ9DPNT7s-5IwbYBom3B2Sb1eqiGQqVHHw6cU4KjWgPHAC8R9JUP1g6LTzJB0XSftED6ejmIX0Sm4tbKYlgl9DCfNHFdYskqCH92mIZ2jk9fCPwozHX1mzi-1XFiLzDlYXyKat_TNmdtxU-tpBGA_u7lpEgC3cgKko5s'

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

data = {"uris": [track_uri]}

response = requests.post(
    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
    headers=headers,
    json=data,
)

if response.status_code == 201:
    print("Track added to playlist successfully!")
else:
    print(f"Error adding track: {response.status_code} - {response.text}")