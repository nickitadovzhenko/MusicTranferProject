# Streamify

A web application that transfers playlists and liked songs between music streaming platforms — built with Django, Celery, and OAuth2.

> **Live demo:** _coming soon_

---

## What it does

Streamify lets users migrate their music libraries across streaming services without any manual work:

- **Spotify → YouTube** — transfers playlists and liked songs, searches YouTube for each track
- **YouTube → Spotify** — transfers YouTube playlists, searches Spotify for each video title
- **Spotify → Spotify** — copies playlists or liked songs across two different Spotify accounts

Transfers run as **background jobs** so the UI never blocks. Users can monitor real-time progress while the transfer runs.

---

## Architecture

```
Browser
   │
   ▼
Django (views + REST API)
   │
   ├── OAuth2 ──► Spotify API (Spotipy)
   │                  └── playlist data, track search, liked songs
   │
   ├── OAuth2 ──► YouTube Data API v3
   │                  └── playlist data, video search
   │
   └── Celery task queue
          │
          ▼
        Redis (broker)
          │
          ▼
      Celery worker
          └── runs transfers asynchronously, writes progress to DB
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Backend | Python 3.14, Django 5.2 LTS | Rapid development, long-term support until 2028 |
| Task queue | Celery 5 + Redis | Playlist transfers take minutes — offloaded to background workers to avoid blocking the user |
| Database | MySQL (production), SQLite (tests) | Relational structure fits users ↔ tokens ↔ jobs |
| Spotify integration | Spotipy | Thin wrapper around Spotify Web API with built-in OAuth helpers |
| YouTube integration | Google API Python Client | Official Google library for YouTube Data API v3 |
| Token encryption | Custom Fernet field (`cryptography` library) | OAuth tokens are encrypted at rest using AES-128 symmetric encryption derived from `SECRET_KEY` |
| Auth | Django built-in + email verification | Secure user management without external auth services |
| API | Django REST Framework | Clean REST endpoints for transfer status and job monitoring |

---

## Key Design Decisions

**Why Celery for background jobs?**
Playlist transfers involve dozens to hundreds of API calls (one per track). Running this synchronously in a web request would time out and give users no feedback. Celery offloads each transfer to a worker process, and the job progress is written to the database so the frontend can poll it.

**Why encrypt OAuth tokens at rest?**
Users connect their Spotify and YouTube accounts — those OAuth tokens grant write access to their music libraries. Storing them in plaintext is a serious security risk. Each token is encrypted with Fernet (AES-128-CBC + HMAC) using a key derived from Django's `SECRET_KEY` before being written to the database.

**Why Django 5.2 LTS?**
LTS releases receive security patches for three years. Choosing an LTS version for a production-facing app means not scrambling to upgrade every six months.

---

## Hosted Demo

A fully hosted version with Docker and CI/CD is coming soon. The live URL will be added here once deployed.

---

## Running Tests

The test suite uses SQLite in-memory and runs Celery tasks synchronously — no Redis or external APIs needed.

```bash
python manage.py test --settings=playlistTransfer.test_settings
```

**46 tests** covering:
- All three transfer tasks (Spotify→YouTube, YouTube→Spotify, Spotify→Spotify)
- Token validation and refresh logic
- OAuth service layer (Spotify and YouTube)
- Transfer views and dashboard

External APIs (Spotify, YouTube) are fully mocked — tests run offline and cover both happy paths and failure scenarios.

---

## Project Structure

```
core/          # User auth, transfer job model, Celery tasks, main views
spotify/       # Spotify OAuth flow and service layer
youtube/       # YouTube OAuth flow and service layer
api/           # Django REST Framework endpoints
playlistTransfer/  # Django project config, Celery config, settings
```

---

## Roadmap

- [ ] Docker + docker-compose (one-command local setup)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Swagger API docs
- [ ] Apple Music integration
- [ ] Export playlists to CSV/JSON
