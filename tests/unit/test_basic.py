# tests/unit/test_basic.py
# flake8: noqa: E402
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import bot

extract_yandex_track_ref = bot.extract_yandex_track_ref
extract_apple_music_song_url = bot.extract_apple_music_song_url
build_caption = bot.build_caption
build_inline_description = bot.build_inline_description
generate_keyboard = bot.generate_keyboard
get_cached_track = bot.get_cached_track
is_suspicious_yandex_label = bot.is_suspicious_yandex_label
parse_apple_music = bot.parse_apple_music
parse_yandex_music = bot.parse_yandex_music
parse_music_url = bot.parse_music_url
parse_soundcloud = bot.parse_soundcloud
set_cached_track = bot.set_cached_track

def test_math_addition():
    """Пример самого простого юнит-теста."""
    assert 2 + 3 == 5


def test_extract_apple_music_song_url():
    assert (
        extract_apple_music_song_url(
            "https://music.apple.com/us/album/the-light-remixes-single/1811230937?i=1811230938"
        )
        == "https://music.apple.com/us/song/1811230938"
    )
    assert (
        extract_apple_music_song_url(
            "https://music.apple.com/us/song/without-hesitation-live-feat-marlene-lamb/1811230938"
        )
        == "https://music.apple.com/us/song/1811230938"
    )


def test_string_contains():
    """Проверка строки."""
    s = "spotify bot"
    assert "bot" in s


@pytest.mark.parametrize("text, expected", [
    ("HELLO".lower(), "hello"),
    ("Bot".capitalize(), "Bot"),
])
def test_parametrized(text, expected):
    assert text == expected


@pytest.mark.asyncio
async def test_parse_apple_music():
    """Тест парсинга Apple Music через ld+json song page."""
    with patch('app.sources.aiohttp.ClientSession.get') as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value='''
        <html>
        <head>
        <meta property="og:image" content="https://example.com/image.jpg">
        <script id="schema:song" type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "MusicComposition",
          "name": "Song Name",
          "datePublished": "2023-04-22",
          "audio": {
            "@type": "MusicRecording",
            "name": "Song Name",
            "datePublished": "2023-04-22",
            "image": "https://example.com/image.jpg",
            "byArtist": [
              {"@type": "MusicGroup", "name": "Artist Name"}
            ],
            "inAlbum": {
              "@type": "MusicAlbum",
              "name": "Album Name"
            }
          }
        }
        </script>
        <meta property="og:image" content="https://example.com/image.jpg">
        </head>
        </html>
        ''')
        mock_get.return_value.__aenter__.return_value = mock_resp

        result = await parse_apple_music("https://music.apple.com/us/album/song/id123")
        assert result["artist"] == "Artist Name"
        assert result["track"] == "Song Name"
        assert result["album"] == "Album Name"
        assert result["release_date"] == "22.04.2023"


@pytest.mark.asyncio
async def test_parse_apple_music_falls_back_to_meta_tags():
    with patch('app.sources.aiohttp.ClientSession.get') as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value='''
        <html>
        <head>
        <meta name="apple:title" content="Song Name">
        <meta name="apple:description" content="Listen to Song Name by Artist Name on Apple Music. 2023. Duration: 3:00">
        <meta property="og:image" content="https://example.com/image.jpg">
        </head>
        </html>
        ''')
        mock_get.return_value.__aenter__.return_value = mock_resp

        result = await parse_apple_music("https://music.apple.com/us/song/song-name/123")
        assert result["artist"] == "Artist Name"
        assert result["track"] == "Song Name"
        assert result["label"] == "Apple Music"


@pytest.mark.asyncio
async def test_parse_soundcloud():
    """Тест парсинга SoundCloud (mock)."""
    with patch('bot.aiohttp.ClientSession.get') as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value='''
        <html>
        <head>
        <meta property="og:title" content="Artist - Track">
        <meta property="og:image" content="https://example.com/image.jpg">
        </head>
        </html>
        ''')
        mock_get.return_value.__aenter__.return_value = mock_resp

        result = await parse_soundcloud("https://soundcloud.com/artist/track")
        assert result["artist"] == "Artist"
        assert result["track"] == "Track"


@pytest.mark.asyncio
async def test_parse_yandex_music():
    """Тест парсинга Яндекс.Музыки через yandex-music client."""
    album = type(
        "Album",
        (),
        {
            "title": "Album Name",
            "year": 2024,
            "release_date": "2024-01-01T00:00:00+03:00",
            "labels": [{"name": "Anjunadeep"}],
        },
    )()
    artist_one = type("Artist", (), {"name": "Artist One"})()
    artist_two = type("Artist", (), {"name": "Artist Two"})()
    track = type(
        "Track",
        (),
        {
            "title": "Track Name",
            "cover_uri": "avatars.yandex.net/get-music-content/12345/%%",
            "artists": [artist_one, artist_two],
            "albums": [album],
        },
    )()

    client = type("Client", (), {"tracks": lambda self, refs: [track]})()
    with patch("app.sources.get_yandex_client", return_value=client):
        result = await parse_yandex_music("https://music.yandex.ru/album/1/track/123")
        assert result["artist"] == "Artist One, Artist Two"
        assert result["track"] == "Track Name"
        assert result["album"] == "Album Name"
        assert result["release_date"] == "01.01.2024"
        assert result["label"] == "Anjunadeep"
        assert result["image"] == "https://avatars.yandex.net/get-music-content/12345/400x400"


@pytest.mark.asyncio
async def test_parse_yandex_music_with_empty_albums():
    """Пустой список альбомов не должен ронять парсер."""
    artist = type("Artist", (), {"name": "Artist One"})()
    track = type(
        "Track",
        (),
        {
            "title": "Track Name",
            "cover_uri": None,
            "artists": [artist],
            "albums": [],
        },
    )()

    client = type("Client", (), {"tracks": lambda self, refs: [track]})()
    with patch("app.sources.get_yandex_client", return_value=client):
        result = await parse_yandex_music("https://music.yandex.ru/album/1/track/123")
        assert result["artist"] == "Artist One"
        assert result["album"] == "Unknown Album"
        assert result["release_date"] == "Unknown Date"
        assert result["label"] == "Яндекс.Музыка"


def test_extract_yandex_track_ref():
    assert extract_yandex_track_ref("https://music.yandex.ru/album/1/track/123") == "123:1"
    assert extract_yandex_track_ref("https://music.yandex.ru/track/123") == "123"
    assert extract_yandex_track_ref("https://example.com") is None


def test_is_suspicious_yandex_label():
    assert is_suspicious_yandex_label("Креатив-ИН") is True
    assert is_suspicious_yandex_label("Anjunadeep") is False


def test_build_caption_hides_generic_yandex_label():
    caption = build_caption(
        "Artist",
        "Track",
        "Album",
        "01.01.2024",
        "Яндекс.Музыка",
        "yandex_music",
    )
    assert "Label:" not in caption


def test_build_caption_hides_generic_apple_music_label():
    caption = build_caption(
        "Artist",
        "Track",
        "Album",
        "01.01.2024",
        "Apple Music",
        "apple_music",
    )
    assert "Label:" not in caption


def test_build_caption_hides_suspicious_yandex_label():
    caption = build_caption(
        "Artist",
        "Track",
        "Album",
        "01.01.2024",
        "Креатив-ИН",
        "yandex_music",
    )
    assert "Label:" not in caption


def test_build_inline_description_hides_generic_yandex_label():
    assert build_inline_description("Album", "Яндекс.Музыка", "yandex_music") == "Album"


def test_build_inline_description_hides_generic_apple_music_label():
    assert build_inline_description("Album", "Apple Music", "apple_music") == "Album"


def test_generate_keyboard_does_not_duplicate_apple_music_button():
    keyboard = generate_keyboard(
        "Track",
        "Artist",
        "https://music.apple.com/us/song/example/123",
        "apple_music",
    )
    button_texts = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert button_texts.count("🍎 Apple Music") == 1
    assert button_texts[0] == "🍎 Apple Music"
    assert button_texts.count("🎧 Spotify") == 1


def test_generate_keyboard_does_not_duplicate_soundcloud_button():
    keyboard = generate_keyboard(
        "Track",
        "Artist",
        "https://soundcloud.com/artist/track",
        "soundcloud",
    )
    button_texts = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert button_texts.count("☁️ SoundCloud") == 1
    assert button_texts[0] == "☁️ SoundCloud"
    assert button_texts.count("🎧 Spotify") == 1


def test_generate_keyboard_does_not_duplicate_spotify_button():
    keyboard = generate_keyboard(
        "Track",
        "Artist",
        "https://open.spotify.com/track/example",
        "spotify",
    )
    button_texts = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert button_texts.count("🎧 Spotify") == 1
    assert button_texts[0] == "🎧 Spotify"


def test_build_inline_description_keeps_normal_label():
    assert build_inline_description("Album", "Anjunadeep", "yandex_music") == "Album | Anjunadeep"


@pytest.mark.asyncio
async def test_parse_yandex_music_prefers_canonical_candidate():
    base_album = type(
        "Album",
        (),
        {
            "title": "Prospect EP",
            "year": 2019,
            "release_date": "2019-10-01T00:00:00+03:00",
            "labels": [{"name": "Креатив-ИН"}],
        },
    )()
    canonical_album = type(
        "Album",
        (),
        {
            "title": "Prospect EP",
            "year": 2019,
            "release_date": "2019-05-28T00:00:00+03:00",
            "labels": [{"name": "Anjunadeep"}],
        },
    )()

    base_track = type(
        "Track",
        (),
        {
            "title": "Follow Me",
            "cover_uri": "avatars.yandex.net/get-music-content/base/%%",
            "artists": [type("Artist", (), {"name": "Nox Vahn & Marsh feat. Mimi Page"})()],
            "albums": [base_album],
        },
    )()
    canonical_track = type(
        "Track",
        (),
        {
            "title": "Follow Me",
            "cover_uri": "avatars.yandex.net/get-music-content/canonical/%%",
            "artists": [
                type("Artist", (), {"name": "Nox Vahn"})(),
                type("Artist", (), {"name": "Marsh"})(),
                type("Artist", (), {"name": "Mimi Page"})(),
            ],
            "albums": [canonical_album],
        },
    )()

    tracks_result = type("TracksResult", (), {"results": [canonical_track]})()
    search_result = type("SearchResult", (), {"tracks": tracks_result})()
    client = type(
        "Client",
        (),
        {
            "tracks": lambda self, refs: [base_track],
            "search": lambda self, query: search_result,
        },
    )()

    with patch("app.sources.get_yandex_client", return_value=client):
        result = await parse_yandex_music("https://music.yandex.ru/album/1/track/123")
        assert result["artist"] == "Nox Vahn, Marsh, Mimi Page"
        assert result["album"] == "Prospect EP"
        assert result["label"] == "Anjunadeep"
        assert result["release_date"] == "28.05.2019"


@pytest.mark.asyncio
async def test_parse_yandex_music_keeps_specific_base_label_when_refined_is_generic():
    base_album = type(
        "Album",
        (),
        {
            "title": "Prospect EP",
            "year": 2019,
            "release_date": "2019-10-01T00:00:00+03:00",
            "labels": [{"name": "Креатив-ИН"}],
        },
    )()
    refined_album = type(
        "Album",
        (),
        {
            "title": "Prospect EP",
            "year": None,
            "release_date": None,
            "labels": [],
        },
    )()

    base_track = type(
        "Track",
        (),
        {
            "title": "Follow Me",
            "cover_uri": "avatars.yandex.net/get-music-content/base/%%",
            "artists": [type("Artist", (), {"name": "Nox Vahn & Marsh feat. Mimi Page"})()],
            "albums": [base_album],
        },
    )()
    refined_track = type(
        "Track",
        (),
        {
            "title": "Follow Me",
            "cover_uri": "avatars.yandex.net/get-music-content/refined/%%",
            "artists": [
                type("Artist", (), {"name": "Nox Vahn"})(),
                type("Artist", (), {"name": "Marsh"})(),
                type("Artist", (), {"name": "Mimi Page"})(),
            ],
            "albums": [refined_album],
        },
    )()

    tracks_result = type("TracksResult", (), {"results": [refined_track]})()
    search_result = type("SearchResult", (), {"tracks": tracks_result})()
    client = type(
        "Client",
        (),
        {
            "tracks": lambda self, refs: [base_track],
            "search": lambda self, query: search_result,
        },
    )()

    with patch("app.sources.get_yandex_client", return_value=client):
        result = await parse_yandex_music("https://music.yandex.ru/album/1/track/123")
        assert result["label"] == "Креатив-ИН"
        assert result["release_date"] == "01.10.2019"


@pytest.mark.asyncio
async def test_parse_music_url_uses_cache():
    """Повторный вызов должен брать данные из кеша без запроса в сеть."""
    url = "https://music.apple.com/us/album/song/id123"
    payload = {
        "artist": "Cached Artist",
        "track": "Cached Track",
        "album": "Cached Album",
        "image": None,
        "label": "Apple Music",
        "release_date": "2025",
        "source": "apple_music",
        "source_url": url,
    }
    set_cached_track(url, payload)

    with patch('app.sources.parse_apple_music', new_callable=AsyncMock) as mock_parser:
        result = await parse_music_url(url)
        assert result == payload
        mock_parser.assert_not_called()
        assert get_cached_track(url) == payload
