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

## Credentials

Do not put tokens in the repo. Use environment variables:

```bash
export YANDEX_MUSIC_TOKEN='...'
export SPOTIFY_CLIENT_ID='...'
export SPOTIFY_CLIENT_SECRET='...'
```

Spotify app setup:

- Create an app in the Spotify Developer Dashboard.
- Add redirect URI: `http://127.0.0.1:8888/callback`
- Required scopes are `playlist-modify-private playlist-modify-public`.

Yandex Music token:

- Yandex Music has no normal public OAuth app flow for this use case.
- The script relies on the unofficial `yandex-music` library, so the token is sensitive and the API can break.

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
