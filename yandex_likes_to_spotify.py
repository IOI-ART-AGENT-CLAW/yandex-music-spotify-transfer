#!/usr/bin/env python3
"""Transfer liked Yandex Music tracks to a Spotify playlist.

Credentials are intentionally read from environment variables or CLI args:
  YANDEX_MUSIC_TOKEN
  SPOTIFY_CLIENT_ID
  SPOTIFY_CLIENT_SECRET

The script supports dry-run mode and writes a JSON report so questionable
matches can be reviewed before anything is added to Spotify.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from yandex_music import Client


DEFAULT_SCOPES = "playlist-modify-private playlist-modify-public"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


@dataclass
class YandexTrack:
    yandex_id: str
    title: str
    artists: list[str]
    album: str | None
    duration_ms: int | None

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else ""

    @property
    def display(self) -> str:
        artist = ", ".join(self.artists) if self.artists else "Unknown artist"
        return f"{artist} - {self.title}"


@dataclass
class SpotifyMatch:
    spotify_id: str
    uri: str
    title: str
    artists: list[str]
    album: str | None
    duration_ms: int | None
    score: float
    url: str | None


@dataclass
class MatchResult:
    yandex: YandexTrack
    spotify: SpotifyMatch | None
    status: str
    query: str
    candidates: list[SpotifyMatch]


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = re.sub(r"\([^)]*\)|\[[^]]*]", " ", value)
    value = re.sub(r"\b(remaster(ed)?|explicit|clean|radio edit|mono|stereo)\b", " ", value)
    value = re.sub(r"[^a-zа-яё0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_overlap(a: str, b: str) -> float:
    left = set(normalize(a).split())
    right = set(normalize(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def duration_score(yandex_ms: int | None, spotify_ms: int | None, tolerance_ms: int) -> float:
    if not yandex_ms or not spotify_ms:
        return 0.0
    diff = abs(yandex_ms - spotify_ms)
    if diff <= tolerance_ms:
        return 1.0
    return max(0.0, 1.0 - (diff - tolerance_ms) / 60_000)


def score_candidate(track: YandexTrack, item: dict[str, Any], tolerance_ms: int) -> SpotifyMatch:
    artists = [artist["name"] for artist in item.get("artists", [])]
    album = item.get("album", {}).get("name")
    title_score = token_overlap(track.title, item.get("name", ""))
    artist_score = token_overlap(" ".join(track.artists), " ".join(artists))
    dur_score = duration_score(track.duration_ms, item.get("duration_ms"), tolerance_ms)
    score = 0.55 * title_score + 0.35 * artist_score + 0.10 * dur_score
    return SpotifyMatch(
        spotify_id=item["id"],
        uri=item["uri"],
        title=item.get("name", ""),
        artists=artists,
        album=album,
        duration_ms=item.get("duration_ms"),
        score=round(score, 4),
        url=item.get("external_urls", {}).get("spotify"),
    )


def spotify_call(func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except SpotifyException as exc:
            if exc.http_status != 429:
                raise
            retry_after = int(getattr(exc, "headers", {}).get("Retry-After", 5))
            time.sleep(retry_after + 1)


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_yandex_likes(token: str, limit: int | None) -> list[YandexTrack]:
    client = Client(token).init()
    liked = client.users_likes_tracks().tracks
    if limit:
        liked = liked[:limit]
    track_refs = [f"{track.id}:{track.album_id}" for track in liked if track.album_id]
    tracks = client.tracks(track_refs)

    result: list[YandexTrack] = []
    for track in tracks:
        result.append(
            YandexTrack(
                yandex_id=f"{track.id}:{track.albums[0].id if track.albums else ''}",
                title=track.title,
                artists=[artist.name for artist in track.artists],
                album=track.albums[0].title if track.albums else None,
                duration_ms=getattr(track, "duration_ms", None),
            )
        )
    return result


def build_spotify_client(args: argparse.Namespace) -> spotipy.Spotify:
    client_id = args.spotify_client_id or os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = args.spotify_client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Missing Spotify credentials: set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.")

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=args.redirect_uri,
        scope=DEFAULT_SCOPES,
        open_browser=False,
        cache_path=str(args.cache_path),
    )
    return spotipy.Spotify(auth_manager=auth, requests_timeout=args.timeout)


def find_match(sp: spotipy.Spotify, track: YandexTrack, args: argparse.Namespace) -> MatchResult:
    queries = [
        f'track:"{track.title}" artist:"{track.primary_artist}"',
        f"{track.primary_artist} {track.title}",
        track.display,
    ]
    seen: set[str] = set()
    candidates: list[SpotifyMatch] = []
    used_query = queries[0]

    for query in queries:
        used_query = query
        response = spotify_call(sp.search, q=query, type="track", limit=args.search_limit, market=args.market)
        items = response.get("tracks", {}).get("items", [])
        for item in items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            candidates.append(score_candidate(track, item, args.duration_tolerance_ms))
        if candidates and max(c.score for c in candidates) >= args.min_score:
            break

    candidates.sort(key=lambda item: item.score, reverse=True)
    best = candidates[0] if candidates else None
    if best is None:
        return MatchResult(track, None, "not_found", used_query, candidates)
    if best.score < args.min_score:
        return MatchResult(track, best, "review", used_query, candidates[: args.report_candidates])
    return MatchResult(track, best, "matched", used_query, candidates[: args.report_candidates])


def create_or_get_playlist(sp: spotipy.Spotify, name: str, description: str) -> str:
    user_id = spotify_call(sp.current_user)["id"]
    offset = 0
    while True:
        page = spotify_call(sp.current_user_playlists, limit=50, offset=offset)
        for playlist in page.get("items", []):
            if playlist.get("name") == name and playlist.get("owner", {}).get("id") == user_id:
                return playlist["id"]
        if page.get("next") is None:
            break
        offset += 50

    playlist = spotify_call(
        sp.user_playlist_create,
        user=user_id,
        name=name,
        public=False,
        description=description,
    )
    return playlist["id"]


def write_report(path: Path, results: list[MatchResult], playlist_id: str | None) -> None:
    payload = {
        "playlist_id": playlist_id,
        "summary": {
            "total": len(results),
            "matched": sum(1 for item in results if item.status == "matched"),
            "review": sum(1 for item in results if item.status == "review"),
            "not_found": sum(1 for item in results if item.status == "not_found"),
        },
        "results": [
            {
                "status": result.status,
                "query": result.query,
                "yandex": asdict(result.yandex),
                "spotify": asdict(result.spotify) if result.spotify else None,
                "candidates": [asdict(candidate) for candidate in result.candidates],
            }
            for result in results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transfer Yandex Music liked tracks to Spotify.")
    parser.add_argument("--yandex-token", default=os.getenv("YANDEX_MUSIC_TOKEN"))
    parser.add_argument("--spotify-client-id")
    parser.add_argument("--spotify-client-secret")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--cache-path", type=Path, default=Path(".cache/spotify-token.json"))
    parser.add_argument("--playlist-name", default="Yandex Music Likes Import")
    parser.add_argument("--playlist-description", default="Imported from Yandex Music by Кат/OpenClaw.")
    parser.add_argument("--report", type=Path, default=Path("reports/yandex_likes_to_spotify_report.json"))
    parser.add_argument("--limit", type=int, help="Only process the first N liked tracks.")
    parser.add_argument("--dry-run", action="store_true", help="Search and report only; do not create/add playlist items.")
    parser.add_argument("--market", default=None, help="Spotify market code, e.g. US, TR, KZ. Default uses account market.")
    parser.add_argument("--search-limit", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.72)
    parser.add_argument("--duration-tolerance-ms", type=int, default=4_000)
    parser.add_argument("--report-candidates", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()

    if not args.yandex_token:
        raise SystemExit("Missing Yandex token: set YANDEX_MUSIC_TOKEN or pass --yandex-token.")
    if not 1 <= args.batch_size <= 100:
        raise SystemExit("--batch-size must be between 1 and 100.")
    return args


def main() -> int:
    args = parse_args()
    sp = build_spotify_client(args)
    yandex_tracks = fetch_yandex_likes(args.yandex_token, args.limit)
    results = [find_match(sp, track, args) for track in yandex_tracks]

    playlist_id = None
    if not args.dry_run:
        playlist_id = create_or_get_playlist(sp, args.playlist_name, args.playlist_description)
        uris = [result.spotify.uri for result in results if result.status == "matched" and result.spotify]
        for batch in chunks(uris, args.batch_size):
            spotify_call(sp.playlist_add_items, playlist_id, batch)

    write_report(args.report, results, playlist_id)
    summary = {
        "total": len(results),
        "matched": sum(1 for item in results if item.status == "matched"),
        "review": sum(1 for item in results if item.status == "review"),
        "not_found": sum(1 for item in results if item.status == "not_found"),
        "dry_run": args.dry_run,
        "playlist_id": playlist_id,
        "report": str(args.report),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
