# Yandex Music -> Spotify Transfer

Small local tool for transferring liked Yandex Music tracks to a Spotify playlist.

Current version focuses on liked tracks. The architecture is intentionally small and reviewable, with a report-first workflow before importing a large library.

## What It Does

1. Reads liked tracks from Yandex Music using the unofficial `yandex-music` Python library.
2. Searches each track in Spotify using the official Spotify Web API through `spotipy`.
3. Scores candidates by title, artist, and duration.
4. Writes a JSON report with `matched`, `review`, and `not_found` items.
5. In non-dry-run mode, creates or reuses a private Spotify playlist and adds matched tracks.

## Why Not Just Use Existing Tools?

[`MarshalX/yandex2spotify`](https://github.com/MarshalX/yandex2spotify) is a useful reference and can do an end-to-end transfer. This project keeps the first version narrower because music matching is easy to get wrong:

- remasters and re-releases;
- clean vs explicit versions;
- covers;
- tracks unavailable in a Spotify market;
- Cyrillic/Latin spelling differences.

This script prefers dry-run reports and conservative matching before writing to Spotify.

## Credentials And API Tokens

Do not put tokens in the repo. Use environment variables:

```bash
export YANDEX_MUSIC_TOKEN='...'
export SPOTIFY_CLIENT_ID='...'
export SPOTIFY_CLIENT_SECRET='...'
```

Create a local `.env` file if that is easier, but keep it untracked:

```bash
cp .env.example .env
nano .env
set -a
. ./.env
set +a
```

### Spotify Credentials

Spotify uses the official Spotify Web API. For a personal transfer script, use
Authorization Code Flow because the script needs permission to create or edit
playlists in your own Spotify account.

1. Open the Spotify Developer Dashboard:

   <https://developer.spotify.com/dashboard>

2. Sign in with the Spotify account that should receive the imported music.

3. Create a new app.

   Suggested values:

   - App name: `Yandex Music Spotify Transfer`
   - App description: `Personal music library transfer tool`
   - Website: can be left empty if Spotify allows it, or use a personal/project URL.
   - Redirect URI: `http://127.0.0.1:8888/callback`

4. Open the app settings and copy:

   - `Client ID` -> `SPOTIFY_CLIENT_ID`
   - `Client secret` -> `SPOTIFY_CLIENT_SECRET`

5. Make sure the redirect URI in the Spotify dashboard exactly matches the
   redirect URI used by the script:

   ```text
   http://127.0.0.1:8888/callback
   ```

   Even a missing slash, different port, `localhost` instead of `127.0.0.1`, or
   `https` instead of `http` can break OAuth.

6. Export the credentials:

   ```bash
   export SPOTIFY_CLIENT_ID='your_client_id'
   export SPOTIFY_CLIENT_SECRET='your_client_secret'
   ```

The script requests these Spotify scopes:

```text
playlist-modify-private playlist-modify-public
```

They are enough for creating/updating playlists. Future modules may need more
scopes, for example `user-library-modify` for saving liked tracks directly to
Spotify library.

On the first non-dry-run execution, Spotipy prints an authorization URL. Open it,
approve access, and paste the final redirected URL back into the terminal when
prompted. Spotipy then caches the Spotify access/refresh token under:

```text
.cache/spotify-token.json
```

Do not commit that cache file.

### Yandex Music Token

Yandex Music does not provide a stable public developer app flow for this use
case. This tool uses the unofficial `yandex-music` Python library, so the Yandex
token is sensitive and the method can break if Yandex changes private APIs.

Useful reference:

<https://yandex-music.readthedocs.io/en/main/token.html>

High-level process:

1. Be signed in to the Yandex account that owns the Yandex Music library.
2. Obtain a Yandex Music compatible OAuth token using one of the methods
   described by the `yandex-music` project documentation.
3. Export it locally:

   ```bash
   export YANDEX_MUSIC_TOKEN='your_yandex_music_token'
   ```

4. Validate it with a small dry run before importing anything:

   ```bash
   ./run_yandex_likes_to_spotify.sh --dry-run --limit 5
   ```

Security notes:

- Treat `YANDEX_MUSIC_TOKEN` like a password for your Yandex Music account.
- Do not paste it into public chats, GitHub issues, screenshots, or Notion pages.
- Prefer storing it only in a local `.env` file or password manager.
- If a token leaks, revoke it in Yandex account security/OAuth settings and
  generate a new one.

### Quick Credential Check

After exporting all three variables, run:

```bash
python3 - <<'PY'
import os
for name in ("YANDEX_MUSIC_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
    value = os.getenv(name)
    print(f"{name}: {'set' if value else 'missing'}")
PY
```

This only checks that variables are present. It does not print secret values.

## Install

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

or with regular Python:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Dry Run

```bash
./run_yandex_likes_to_spotify.sh --dry-run --limit 20
```

## Import

```bash
./run_yandex_likes_to_spotify.sh \
  --playlist-name 'Yandex Music Likes Import' \
  --market US
```

The first Spotify run prints an auth URL. Open it, authorize, then paste the redirected URL back into the prompt.

## Recommended Workflow

1. Run a small dry run:

   ```bash
   ./run_yandex_likes_to_spotify.sh --dry-run --limit 20 --market US
   ```

2. Open `reports/yandex_likes_to_spotify_report.json`.

3. Check:

   - `matched`: confident matches that can be imported;
   - `review`: possible matches that need manual review;
   - `not_found`: no good Spotify result.

4. If the report looks good, run without `--dry-run`.

5. For a full import, remove `--limit`.

## Output

Default report:

```text
reports/yandex_likes_to_spotify_report.json
```

Review `review` and `not_found` before trusting a large import.

## What About Playlists, Albums, Artists, Dislikes?

Planned next modules:

- Yandex playlists -> Spotify playlists.
- Yandex liked albums -> Spotify saved albums.
- Yandex liked artists -> Spotify followed artists.
- Yandex dislikes -> JSON/CSV blacklist report. Spotify does not have a clean global "disliked tracks" import target, so dislikes should be preserved as metadata and used to avoid future recommendations/imports.

## Tests

```bash
.venv/bin/python -m unittest -v
```

The current tests cover matching helper behavior. Network/API behavior is intentionally not tested without real credentials.
