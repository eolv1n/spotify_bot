import asyncio
import json
import logging
import re
import threading
from urllib.parse import parse_qs, urlparse

import aiohttp
from bs4 import BeautifulSoup
from yandex_music import Client as YandexMusicClient

from app.cache import get_cached_track, init_cache_db, set_cached_track
from app.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from app.formatting import (
    build_track_payload,
    format_date_ru,
    get_meta_content,
    is_suspicious_yandex_label,
    normalize_text,
    tokenize_text,
)

_yandex_client = None
_yandex_client_lock = threading.Lock()

SUPPORTED_TRACK_SERVICES = {
    "spotify",
    "apple_music",
    "yandex_music",
    "soundcloud",
    "youtube_music",
}
SOUNDCLOUD_NON_TRACK_PREFIXES = {
    "charts",
    "discover",
    "genres",
    "search",
    "sets",
    "station",
    "stream",
    "upload",
    "you",
}


def classify_music_url(url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    path_parts = [part for part in path.split("/") if part]
    query = parse_qs(parsed.query)

    if host == "spotify.link":
        return {
            "service": "spotify_shortlink",
            "kind": "shortlink",
            "supported": True,
        }

    if host in {"on.soundcloud.com", "soundcloud.app.goo.gl"}:
        return {
            "service": "soundcloud_shortlink",
            "kind": "shortlink",
            "supported": True,
        }

    if host == "open.spotify.com":
        if "track" in path_parts:
            return {"service": "spotify", "kind": "track", "supported": True}
        if "album" in path_parts:
            return {"service": "spotify", "kind": "album", "supported": False}
        if "playlist" in path_parts:
            return {"service": "spotify", "kind": "playlist", "supported": False}
        if "artist" in path_parts:
            return {"service": "spotify", "kind": "artist", "supported": False}

    if host == "music.apple.com":
        if "i" in query or "song" in path_parts:
            return {"service": "apple_music", "kind": "track", "supported": True}
        if "album" in path_parts:
            return {"service": "apple_music", "kind": "album", "supported": False}
        if "playlist" in path_parts:
            return {"service": "apple_music", "kind": "playlist", "supported": False}
        if "artist" in path_parts:
            return {"service": "apple_music", "kind": "artist", "supported": False}

    if host == "music.yandex.ru":
        if "track" in path_parts:
            return {"service": "yandex_music", "kind": "track", "supported": True}
        if "album" in path_parts:
            return {"service": "yandex_music", "kind": "album", "supported": False}
        if "playlists" in path_parts or "users" in path_parts:
            return {"service": "yandex_music", "kind": "playlist", "supported": False}
        if "artist" in path_parts:
            return {"service": "yandex_music", "kind": "artist", "supported": False}

    if host == "soundcloud.com":
        if "sets" in path_parts:
            return {"service": "soundcloud", "kind": "set", "supported": False}
        if len(path_parts) >= 2 and path_parts[0] not in SOUNDCLOUD_NON_TRACK_PREFIXES:
            return {"service": "soundcloud", "kind": "track", "supported": True}
        return {"service": "soundcloud", "kind": "page", "supported": False}

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        if host == "youtu.be":
            return {"service": "youtube", "kind": "video", "supported": False}
        if host == "music.youtube.com":
            if "list" in query or "playlist" in path_parts:
                return {"service": "youtube_music", "kind": "playlist", "supported": False}
            if parsed.path == "/watch" and "v" in query:
                return {"service": "youtube_music", "kind": "track", "supported": True}
            return {"service": "youtube_music", "kind": "page", "supported": False}
        if "list" in query or "playlist" in path_parts:
            return {"service": "youtube", "kind": "playlist", "supported": False}
        if "shorts" in path_parts:
            return {"service": "youtube", "kind": "short", "supported": False}
        if parsed.path == "/watch" and "v" in query:
            return {"service": "youtube", "kind": "video", "supported": True}
        return {"service": "youtube", "kind": "page", "supported": False}

    return {"service": None, "kind": None, "supported": False}


def build_unsupported_url_message(classification: dict) -> str | None:
    service = classification.get("service")
    kind = classification.get("kind")

    if not service:
        return None

    service_names = {
        "spotify": "Spotify",
        "apple_music": "Apple Music",
        "yandex_music": "Яндекс.Музыка",
        "soundcloud": "SoundCloud",
        "youtube": "YouTube",
        "youtube_music": "YouTube Music",
    }
    kind_names = {
        "album": "альбом",
        "artist": "страница артиста",
        "page": "страница сервиса",
        "playlist": "плейлист",
        "set": "сет",
        "short": "shorts-видео",
        "video": "видео",
    }

    service_name = service_names.get(service, service)
    kind_name = kind_names.get(kind, "ссылка")

    if service == "youtube":
        return (
            f"Распознал {service_name}, но пока умею работать только с музыкальными "
            f"стриминг-ссылками, а не с типом `{kind_name}` 😕"
        )

    if service == "youtube_music":
        return (
            f"Распознал {service_name}, но пока умею разбирать только ссылки на отдельные "
            f"треки, а не `{kind_name}` 😕"
        )

    return (
        f"Похоже, это не ссылка на трек, а `{kind_name}` в {service_name}. "
        "Сейчас я умею разбирать только треки."
    )


def extract_json_from_script(script_text: str):
    start = script_text.find("{")
    end = script_text.rfind("}") + 1
    if start == -1 or end <= start:
        return None

    try:
        return json.loads(script_text[start:end])
    except json.JSONDecodeError:
        return None


def get_yandex_client():
    global _yandex_client
    if _yandex_client is None:
        with _yandex_client_lock:
            if _yandex_client is None:
                _yandex_client = YandexMusicClient().init()
    return _yandex_client


def extract_track_id(spotify_url: str):
    match = re.search(r"track/([A-Za-z0-9]+)", spotify_url)
    return match.group(1) if match else None


async def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            data=data,
            auth=aiohttp.BasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        ) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")


async def resolve_spotify_link(short_url: str) -> str:
    return await resolve_redirect_url(short_url)


async def resolve_redirect_url(short_url: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(short_url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception as exc:
            logging.error("Ошибка раскрытия ссылки: %s", exc)
            return None


async def get_album_label(album_id: str) -> str:
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.spotify.com/v1/albums/{album_id}",
            headers=headers,
        ) as resp:
            if resp.status != 200:
                return "Unknown Label"
            data = await resp.json()
            return data.get("label", "Unknown Label")


def extract_apple_music_song_url(url: str) -> str | None:
    storefront_match = re.search(r"music\.apple\.com/([a-z]{2})/", url)
    storefront = storefront_match.group(1) if storefront_match else "us"

    song_id_match = re.search(r"[?&]i=(\d+)", url)
    if song_id_match:
        return f"https://music.apple.com/{storefront}/song/{song_id_match.group(1)}"

    direct_song_match = re.search(
        r"music\.apple\.com/[a-z]{2}/song/(?:[^/]+/)?(\d+)",
        url,
    )
    if direct_song_match:
        return f"https://music.apple.com/{storefront}/song/{direct_song_match.group(1)}"

    return None


def parse_apple_music_ld_json(soup: BeautifulSoup):
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            audio = item.get("audio")
            if not isinstance(audio, dict):
                continue

            track = audio.get("name") or item.get("name")
            in_album = audio.get("inAlbum") or {}
            album = in_album.get("name") if isinstance(in_album, dict) else None
            album = album or "Unknown Album"
            artist_nodes = audio.get("byArtist") or item.get("byArtist") or []
            if isinstance(artist_nodes, dict):
                artist_nodes = [artist_nodes]
            artist_names = [
                node["name"]
                for node in artist_nodes
                if isinstance(node, dict) and node.get("name")
            ]
            release_date = (
                audio.get("datePublished")
                or item.get("datePublished")
                or "Unknown Date"
            )
            image = audio.get("image") or item.get("image")

            if track and artist_names:
                return {
                    "artist": ", ".join(artist_names),
                    "track": track,
                    "album": album,
                    "image": image,
                    "release_date": format_date_ru(str(release_date)),
                }
    return None


async def parse_apple_music(url: str):
    candidate_urls = [url]
    canonical_song_url = extract_apple_music_song_url(url)
    if canonical_song_url and canonical_song_url not in candidate_urls:
        candidate_urls.insert(0, canonical_song_url)

    async with aiohttp.ClientSession() as session:
        for candidate_url in candidate_urls:
            async with session.get(
                candidate_url,
                headers={"User-Agent": "Mozilla/5.0"},
            ) as resp:
                if resp.status != 200:
                    continue

                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                parsed_from_schema = parse_apple_music_ld_json(soup)
                if parsed_from_schema:
                    return build_track_payload(
                        artist=parsed_from_schema["artist"],
                        track=parsed_from_schema["track"],
                        album=parsed_from_schema["album"],
                        image=parsed_from_schema["image"],
                        label="Apple Music",
                        release_date=parsed_from_schema["release_date"],
                        source="apple_music",
                        source_url=url,
                    )

                title_text = (
                    get_meta_content(soup, name="apple:title")
                    or get_meta_content(soup, property_name="og:title")
                )
                desc_text = (
                    get_meta_content(soup, name="apple:description")
                    or get_meta_content(soup, property_name="og:description")
                )
                image_url = get_meta_content(soup, property_name="og:image")

                if not title_text or not desc_text:
                    continue

                artist = None
                track = title_text
                if " by " in title_text and " on Apple Music" in title_text:
                    song_artist = title_text.replace(" on Apple Music", "").split(" by ", 1)
                    track = song_artist[0].strip()
                    artist = song_artist[1].strip()

                album = "Unknown Album"
                release_date = "Unknown Date"
                if (
                    "Listen to " in desc_text
                    and " by " in desc_text
                    and " on Apple Music." in desc_text
                ):
                    artist = artist or desc_text.split(" by ", 1)[1].split(
                        " on Apple Music.",
                        1,
                    )[0].strip()
                if " · " in desc_text:
                    parts = desc_text.split(" · ")
                    if len(parts) >= 2:
                        album = parts[0].replace("Song", "").strip() or "Unknown Album"
                        release_date = parts[1].strip()

                if not artist:
                    continue

                return build_track_payload(
                    artist=artist,
                    track=track,
                    album=album,
                    image=image_url,
                    label="Apple Music",
                    release_date=release_date,
                    source="apple_music",
                    source_url=url,
                )

    return None


def extract_yandex_track_ref(url: str):
    track_match = re.search(r"/track/(\d+)", url)
    album_match = re.search(r"/album/(\d+)", url)

    if not track_match:
        return None

    track_id = track_match.group(1)
    album_id = album_match.group(1) if album_match else None
    return f"{track_id}:{album_id}" if album_id else track_id


def extract_yandex_label_name(album) -> str:
    label = "Яндекс.Музыка"
    labels = getattr(album, "labels", None) or []
    first_label = next(iter(labels), None)
    if isinstance(first_label, dict):
        return first_label.get("name") or label
    if first_label is not None:
        return getattr(first_label, "name", None) or label
    return label


def build_yandex_payload(track, url: str):
    artist_names = ", ".join(
        artist.name for artist in (track.artists or []) if getattr(artist, "name", None)
    ) or "Unknown Artist"
    track_name = track.title or "Unknown"

    album = next(iter(track.albums or []), None)
    album_name = getattr(album, "title", None) or "Unknown Album"
    raw_release_date = (
        getattr(album, "release_date", None)
        or getattr(album, "original_release_year", None)
        or getattr(album, "year", None)
        or "Unknown Date"
    )
    release_date = format_date_ru(str(raw_release_date))
    label = extract_yandex_label_name(album)

    image_url = None
    cover_uri = getattr(track, "cover_uri", None)
    if cover_uri:
        image_url = f"https://{cover_uri.replace('%%', '400x400')}"

    return build_track_payload(
        artist=artist_names,
        track=track_name,
        album=album_name,
        image=image_url,
        label=label,
        release_date=release_date,
        source="yandex_music",
        source_url=url,
    )


def score_yandex_candidate(
    candidate_track,
    expected_track: str,
    expected_artist: str,
    expected_album: str,
) -> int:
    score = 0
    candidate_title = getattr(candidate_track, "title", "") or ""
    candidate_artist = ", ".join(
        artist.name for artist in (candidate_track.artists or []) if getattr(artist, "name", None)
    )
    candidate_album = (
        getattr(next(iter(candidate_track.albums or []), None), "title", "") or ""
    )
    candidate_label = extract_yandex_label_name(
        next(iter(candidate_track.albums or []), None)
    )

    if normalize_text(candidate_title) == normalize_text(expected_track):
        score += 100

    expected_artist_tokens = tokenize_text(expected_artist)
    candidate_artist_tokens = tokenize_text(candidate_artist)
    if expected_artist_tokens and candidate_artist_tokens:
        overlap = len(expected_artist_tokens & candidate_artist_tokens)
        score += int((overlap / len(expected_artist_tokens)) * 50)

    if (
        expected_album != "Unknown Album"
        and normalize_text(candidate_album) == normalize_text(expected_album)
    ):
        score += 20

    score += min(len(candidate_track.artists or []), 3) * 5

    if candidate_label and candidate_label != "Яндекс.Музыка":
        score += 10
    if is_suspicious_yandex_label(candidate_label):
        score -= 25

    album = next(iter(candidate_track.albums or []), None)
    if getattr(album, "release_date", None):
        score += 8
    elif getattr(album, "year", None):
        score += 4

    return score


async def refine_yandex_payload(url: str, base_track, base_payload: dict):
    current_label = base_payload.get("label", "Яндекс.Музыка")
    artist_field = base_payload.get("artist", "")
    should_refine = is_suspicious_yandex_label(current_label) or (
        "&" in artist_field and len(base_track.artists or []) <= 1
    )
    if not should_refine:
        return base_payload

    query = f"{base_payload.get('artist', '')} {base_payload.get('track', '')}".strip()
    if not query:
        return base_payload

    try:
        client = get_yandex_client()
        search_result = await asyncio.to_thread(client.search, query)
    except Exception as exc:
        logging.warning(
            "Не удалось выполнить поиск Яндекс.Музыки для уточнения %s: %s",
            url,
            exc,
        )
        return base_payload

    candidates = (getattr(getattr(search_result, "tracks", None), "results", None) or [])[:10]
    if not candidates:
        return base_payload

    current_score = score_yandex_candidate(
        base_track,
        expected_track=base_payload.get("track", ""),
        expected_artist=base_payload.get("artist", ""),
        expected_album=base_payload.get("album", ""),
    )
    best_track = base_track
    best_score = current_score

    for candidate in candidates:
        score = score_yandex_candidate(
            candidate,
            expected_track=base_payload.get("track", ""),
            expected_artist=base_payload.get("artist", ""),
            expected_album=base_payload.get("album", ""),
        )
        if score > best_score:
            best_score = score
            best_track = candidate

    if best_track is base_track or best_score < current_score + 15:
        return base_payload

    refined_payload = build_yandex_payload(best_track, url)
    refined_label = refined_payload.get("label", "")
    base_label = base_payload.get("label", "")
    refined_date = refined_payload.get("release_date", "")
    base_date = base_payload.get("release_date", "")

    if is_suspicious_yandex_label(refined_label):
        return base_payload

    if refined_label == "Яндекс.Музыка" and base_label not in {"", "Яндекс.Музыка"}:
        refined_payload["label"] = base_label
    if refined_date == "Unknown Date" and base_date not in {"", "Unknown Date"}:
        refined_payload["release_date"] = base_date

    return refined_payload


async def parse_yandex_music(url: str):
    track_ref = extract_yandex_track_ref(url)
    if not track_ref:
        return None

    try:
        client = get_yandex_client()
        tracks = await asyncio.to_thread(client.tracks, [track_ref])
    except Exception as exc:
        logging.warning("Не удалось получить данные Яндекс.Музыки для %s: %s", url, exc)
        return None

    track = tracks[0] if tracks else None
    if not track:
        return None

    base_payload = build_yandex_payload(track, url)
    return await refine_yandex_payload(url, track, base_payload)


async def parse_soundcloud(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            title_text = get_meta_content(soup, property_name="og:title")
            image_url = get_meta_content(soup, property_name="og:image")

            if not title_text:
                return None

            cleaned_title = clean_soundcloud_title(title_text)
            if " - " in cleaned_title:
                artist, track = cleaned_title.split(" - ", 1)
            else:
                return None

            return build_track_payload(
                artist=artist.strip(),
                track=track.strip(),
                album="Unknown Album",
                image=image_url,
                label="SoundCloud",
                release_date="Unknown Date",
                source="soundcloud",
                source_url=url,
            )


def clean_soundcloud_title(title: str) -> str:
    cleaned = (title or "").strip()
    cleaned = re.sub(r"^\s*(?:premiere|exclusive|free download)\s*:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\[[^\]]+\]\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\((?:official|premiere|exclusive)[^)]+\)\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


def clean_youtube_music_artist(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"\s*-\s*Topic\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*VEVO\s*$", "", cleaned, flags=re.I)
    return cleaned or "Unknown Artist"


def clean_youtube_music_track(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"\s*\((official|official audio|official video|lyric video)[^)]+\)\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*\[(official|official audio|official video|lyrics?)[^\]]+\]\s*$", "", cleaned, flags=re.I)
    return cleaned or "Unknown Track"


async def parse_youtube_music(url: str):
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(oembed_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    artist = clean_youtube_music_artist(data.get("author_name", "Unknown Artist"))
    track = clean_youtube_music_track(data.get("title", "Unknown Track"))
    image_url = data.get("thumbnail_url")

    return build_track_payload(
        artist=artist,
        track=track,
        album="Unknown Album",
        image=image_url,
        label="YouTube Music",
        release_date="Unknown Date",
        source="youtube_music",
        source_url=url,
    )


def is_probable_youtube_track(title: str, author_name: str) -> bool:
    normalized_title = (title or "").lower()
    normalized_author = (author_name or "").lower()
    track_markers = (
        " - ",
        "official audio",
        "lyric",
        "visualizer",
        "topic",
    )
    return any(marker in normalized_title for marker in track_markers) or "topic" in normalized_author


async def parse_youtube(url: str):
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(oembed_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    raw_title = data.get("title", "Unknown Track")
    raw_author = data.get("author_name", "Unknown Artist")
    image_url = data.get("thumbnail_url")

    if not is_probable_youtube_track(raw_title, raw_author):
        return None

    cleaned_title = clean_youtube_music_track(raw_title)
    if " - " in cleaned_title:
        artist, track = cleaned_title.split(" - ", 1)
        artist = artist.strip()
        track = track.strip()
    else:
        artist = clean_youtube_music_artist(raw_author)
        track = cleaned_title

    return build_track_payload(
        artist=artist,
        track=track,
        album="Unknown Album",
        image=image_url,
        label="YouTube",
        release_date="Unknown Date",
        source="youtube",
        source_url=url,
    )


async def get_track_info(track_id: str):
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers=headers,
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

            artist_names = ", ".join(artist["name"] for artist in data["artists"])
            track_name = data["name"]
            album_data = data["album"]
            album_name = album_data["name"]
            album_id = album_data["id"]
            image_url = album_data["images"][0]["url"] if album_data.get("images") else None
            release_date_raw = album_data.get("release_date", "Unknown Date")
            release_date = format_date_ru(release_date_raw)

        label = await get_album_label(album_id)
        return {
            "artist": artist_names,
            "track": track_name,
            "album": album_name,
            "image": image_url,
            "label": label,
            "release_date": release_date,
            "source": "spotify",
            "source_url": f"https://open.spotify.com/track/{track_id}",
        }


async def search_spotify_tracks(query: str):
    token = await get_spotify_token()
    if not token:
        logging.warning("Не удалось получить Spotify token для поиска")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": 5}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params=params,
        ) as resp:
            if resp.status != 200:
                txt = await resp.text()
                logging.warning("Spotify search error: %s %s", resp.status, txt)
                return []
            data = await resp.json()
            return data.get("tracks", {}).get("items", []) or []


async def parse_music_url(url: str):
    cached = get_cached_track(url)
    if cached:
        return cached

    classification = classify_music_url(url)
    if not classification.get("supported"):
        return None

    parsed = None
    if classification["service"] == "apple_music":
        parsed = await parse_apple_music(url)
    elif classification["service"] == "yandex_music":
        parsed = await parse_yandex_music(url)
    elif classification["service"] == "soundcloud":
        parsed = await parse_soundcloud(url)
    elif classification["service"] == "youtube_music":
        parsed = await parse_youtube_music(url)
    elif classification["service"] == "youtube":
        parsed = await parse_youtube(url)
    elif classification["service"] == "spotify":
        track_id = extract_track_id(url)
        if track_id:
            parsed = await get_track_info(track_id)

    if parsed:
        set_cached_track(url, parsed)
    return parsed


init_cache_db()
