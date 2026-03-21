import re
import json
import time
import sqlite3
import logging
import aiohttp
import asyncio
import os
from contextlib import closing

# --- 🔒 Безопасная проверка окружения ---
# Если мы запускаемся в тестах (pytest) или в CI/CD — подставляем фиктивные значения
if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI") == "true":
    for key in ("TELEGRAM_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
        os.environ.setdefault(key, f"fake-{key.lower()}")
else:
    # Продакшн-режим — требуется реальный .env
    from dotenv import load_dotenv
    load_dotenv()
    required = ["TELEGRAM_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise ValueError(f"❌ Не найдены необходимые переменные окружения: {missing}. Проверь .env файл.")

from urllib.parse import quote
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.filters import Command
from dotenv import load_dotenv
from datetime import datetime
from bs4 import BeautifulSoup

# === Настройка логов ===
logging.basicConfig(level=logging.INFO)

# === Загрузка .env ===
load_dotenv()

# === Настройки окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
AUTO_DELETE_DELAY_RAW = os.getenv("AUTO_DELETE_DELAY", "0")
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache/music_cache.sqlite3")
CACHE_TTL_SECONDS_RAW = os.getenv("CACHE_TTL_SECONDS", "43200")

try:
    AUTO_DELETE_DELAY = int(AUTO_DELETE_DELAY_RAW)
    if AUTO_DELETE_DELAY < 0:
        raise ValueError
except (TypeError, ValueError):
    logging.warning(
        "Некорректное значение AUTO_DELETE_DELAY='%s'. Автоудаление отключено.",
        AUTO_DELETE_DELAY_RAW,
    )
    AUTO_DELETE_DELAY = 0
else:
    if AUTO_DELETE_DELAY > 0:
        logging.info(
            "🕒 Автоудаление сообщений включено. Задержка: %s секунд.",
            AUTO_DELETE_DELAY,
        )

try:
    CACHE_TTL_SECONDS = int(CACHE_TTL_SECONDS_RAW)
    if CACHE_TTL_SECONDS <= 0:
        raise ValueError
except (TypeError, ValueError):
    logging.warning("Некорректное значение CACHE_TTL_SECONDS='%s'. Использую 43200 секунд.", CACHE_TTL_SECONDS_RAW)
    CACHE_TTL_SECONDS = 43200

if not TELEGRAM_TOKEN or not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError(
        "❌ Не найдены необходимые переменные окружения! Проверь .env файл."
    )

# === Создаем бота и диспетчер ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

def init_cache_db():
    cache_dir = os.path.dirname(CACHE_DB_PATH)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS url_cache (
                url TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def get_cached_track(url: str):
    now = int(time.time())
    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        row = conn.execute(
            "SELECT payload_json, expires_at FROM url_cache WHERE url = ?",
            (url,),
        ).fetchone()

        if not row:
            return None

        payload_json, expires_at = row
        if expires_at <= now:
            conn.execute("DELETE FROM url_cache WHERE url = ?", (url,))
            conn.commit()
            return None

    try:
        return json.loads(payload_json)
    except json.JSONDecodeError:
        logging.warning("Поврежденный кеш для URL %s, пропускаю запись.", url)
        return None


def set_cached_track(url: str, payload: dict):
    expires_at = int(time.time()) + CACHE_TTL_SECONDS
    with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
        conn.execute(
            """
            INSERT INTO url_cache (url, payload_json, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                payload_json = excluded.payload_json,
                expires_at = excluded.expires_at
            """,
            (url, json.dumps(payload, ensure_ascii=False), expires_at),
        )
        conn.commit()


def get_meta_content(soup: BeautifulSoup, *, property_name: str | None = None, name: str | None = None):
    attrs = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name

    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return None
    return tag.get("content") or None


def build_track_payload(
    *,
    artist: str,
    track: str,
    album: str,
    image: str | None,
    label: str,
    release_date: str,
    source: str,
    source_url: str,
):
    return {
        "artist": artist or "Unknown Artist",
        "track": track or "Unknown Track",
        "album": album or "Unknown Album",
        "image": image,
        "label": label or source,
        "release_date": release_date or "Unknown Date",
        "source": source,
        "source_url": source_url,
    }


def extract_json_from_script(script_text: str):
    start = script_text.find("{")
    end = script_text.rfind("}") + 1
    if start == -1 or end <= start:
        return None

    try:
        return json.loads(script_text[start:end])
    except json.JSONDecodeError:
        return None


init_cache_db()
# === /help ===
@dp.message(Command("help"))
@dp.message(F.text.lower().startswith("/help"))
async def send_help(message: types.Message):
    text = (
        "🎧 <b>Music Info Bot</b>\n\n"
        "Отправь ссылку на трек из Spotify, Apple Music, Яндекс.Музыка или SoundCloud — я покажу подробности.\n"
        "Также можно искать по названию через inline-режим:\n"
        "<code>@имя_бота исполнителль - трек</code>\n\n"
        "📌 Поддерживаю короткие ссылки <code>spotify.link</code>.\n"
        "Работаю в личных сообщениях и группах."
    )
    await message.answer(text, parse_mode="HTML")


# === Spotify Auth ===
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


# === Извлекаем ID трека ===
def extract_track_id(spotify_url: str):
    match = re.search(r"track/([A-Za-z0-9]+)", spotify_url)
    return match.group(1) if match else None


# === Функиця формата даты ===
def format_date_ru(date_str: str) -> str:
    """Преобразует дату Spotify (YYYY-MM-DD или YYYY-MM) в формат DD.MM.YYYY"""
    try:
        if len(date_str) == 10:  # YYYY-MM-DD
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%d.%m.%Y")
        elif len(date_str) == 7:  # YYYY-MM
            dt = datetime.strptime(date_str, "%Y-%m")
            return dt.strftime("%m.%Y")
        elif len(date_str) == 4:  # YYYY
            return date_str
    except Exception:
        pass
    return date_str  # если не удалось преобразовать


# === Раскрываем короткие ссылки ===
async def resolve_spotify_link(short_url: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(short_url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception as e:
            logging.error(f"Ошибка раскрытия ссылки: {e}")
            return None


# === Получаем лейбл альбома ===
async def get_album_label(album_id: str) -> str:
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.spotify.com/v1/albums/{album_id}", headers=headers
        ) as resp:
            if resp.status != 200:
                return "Unknown Label"
            data = await resp.json()
            return data.get("label", "Unknown Label")

# === Парсинг Apple Music ===
async def parse_apple_music(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            title_text = get_meta_content(soup, property_name="og:title")
            desc_text = get_meta_content(soup, property_name="og:description")
            image_url = get_meta_content(soup, property_name="og:image")

            if not title_text or not desc_text:
                return None

            if " by " in title_text and " on Apple Music" in title_text:
                song_artist = title_text.replace(" on Apple Music", "").split(" by ", 1)
                track = song_artist[0].strip()
                artist = song_artist[1].strip()
            else:
                return None

            album = "Unknown Album"
            release_date = "Unknown Date"
            if " · " in desc_text:
                parts = desc_text.split(" · ")
                if len(parts) >= 2:
                    album = parts[0].strip()
                    release_date = parts[1].strip()

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

# === Парсинг Яндекс.Музыка ===
async def parse_yandex_music(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            script_text = None
            for script in soup.find_all("script"):
                text = script.string or script.get_text()
                if text and "window.__DATA__" in text:
                    script_text = text
                    break

            if not script_text:
                return None

            data = extract_json_from_script(script_text)
            if not data:
                return None

            track_data = data.get("entities", {}).get("tracks", {})
            if not track_data:
                return None

            track_id = list(track_data.keys())[0]
            track_info = track_data[track_id]

            artist_names = ", ".join(
                artist.get("name", "Unknown Artist")
                for artist in track_info.get("artists", [])
                if artist.get("name")
            ) or "Unknown Artist"
            track_name = track_info.get("title", "Unknown")

            album_info = next(iter(track_info.get("albums") or []), {})
            album_name = album_info.get("title", "Unknown Album")
            release_date = album_info.get("releaseDate", "Unknown Date")

            image_url = track_info.get("coverUri", "")
            if image_url:
                image_url = f"https://{image_url.replace('%%', '400x400')}"

            return build_track_payload(
                artist=artist_names,
                track=track_name,
                album=album_name,
                image=image_url or None,
                label="Яндекс.Музыка",
                release_date=release_date,
                source="yandex_music",
                source_url=url,
            )

# === Парсинг SoundCloud ===
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

            if " - " in title_text:
                artist, track = title_text.split(" - ", 1)
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

# === Универсальная функция парсинга ===
async def parse_music_url(url: str):
    cached = get_cached_track(url)
    if cached:
        return cached

    parsed = None
    if 'music.apple.com' in url:
        parsed = await parse_apple_music(url)
    elif 'music.yandex.ru' in url:
        parsed = await parse_yandex_music(url)
    elif 'soundcloud.com' in url:
        parsed = await parse_soundcloud(url)
    elif 'open.spotify.com' in url:
        track_id = extract_track_id(url)
        if track_id:
            parsed = await get_track_info(track_id)

    if parsed:
        set_cached_track(url, parsed)
    return parsed

# === Получаем информацию о треке ===
async def get_track_info(track_id: str):
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.spotify.com/v1/tracks/{track_id}", headers=headers
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

            artist_names = ", ".join(artist["name"] for artist in data["artists"])
            track_name = data["name"]
            album_data = data["album"]
            album_name = album_data["name"]
            album_id = album_data["id"]
            image_url = (
                album_data["images"][0]["url"] if album_data.get("images") else None
            )
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


# === Поиск треков по названию ===
async def search_spotify_tracks(query: str):
    token = await get_spotify_token()
    if not token:
        logging.warning("Не удалось получить Spotify token для поиска")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": 5}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.spotify.com/v1/search", headers=headers, params=params
        ) as resp:
            if resp.status != 200:
                txt = await resp.text()
                logging.warning(f"Spotify search error: {resp.status} {txt}")
                return []
            data = await resp.json()
            return data.get("tracks", {}).get("items", []) or []


# === Генерация клавиатуры ===
def generate_keyboard(track, artist, source_url, source="spotify"):
    query_encoded = quote(f"{track} {artist}")
    source_button_label = {
        "spotify": "🎧 Spotify",
        "apple_music": "🍎 Apple Music",
        "yandex_music": "🎶 Яндекс.Музыка",
        "soundcloud": "☁️ SoundCloud",
    }.get(source, "🔗 Открыть источник")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=source_button_label, url=source_url)],
            [
                InlineKeyboardButton(text="🎵 ВКонтакте", url="https://vk.com/audio"),
                InlineKeyboardButton(
                    text="🎶 Яндекс.Музыка",
                    url=f"https://music.yandex.ru/search?text={query_encoded}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="☁️ SoundCloud",
                    url=f"https://soundcloud.com/search?q={query_encoded}",
                ),
                InlineKeyboardButton(
                    text="🍎 Apple Music",
                    url=f"https://music.apple.com/search?term={query_encoded}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="▶️ YouTube",
                    url=f"https://www.youtube.com/results?search_query={query_encoded}",
                ),
                InlineKeyboardButton(
                    text="🎵 YouTube Music",
                    url=f"https://music.youtube.com/search?q={query_encoded}",
                ),
            ],
        ]
    )


# === Автоудаление сообщений ===
def should_auto_delete(chat: types.Chat) -> bool:
    return AUTO_DELETE_DELAY > 0 and chat.type in {"group", "supergroup"}


async def auto_delete_messages(delay: int, messages: list[types.Message]):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение {msg.message_id}: {e}")


# === Inline режим (поиск и ссылки) ===
@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text:
        return

    results = []

    # === Если это ссылка ===
    if any(domain in text for domain in ['open.spotify.com', 'music.apple.com', 'music.yandex.ru', 'soundcloud.com', 'spotify.link']):
        if "spotify.link/" in text:
            text = await resolve_spotify_link(text)
            if not text:
                return

        track_info = await parse_music_url(text)
        if not track_info:
            return

        artist = track_info["artist"]
        track = track_info["track"]
        album = track_info["album"]
        image_url = track_info["image"]
        label = track_info["label"]
        release_date = track_info["release_date"]
        source = track_info.get("source", "spotify")
        source_url = track_info.get("source_url", text)

        caption = (
            f"`{artist} — {track}`\n"
            f"***{album}***\n\n"
            f"Release date: {release_date}\n"
            f"Label: {label}"
        )

        keyboard = generate_keyboard(track, artist, source_url, source)

        results.append(
            InlineQueryResultArticle(
                id=f"{label.lower()}-{hash(text)}",
                title=f"{artist} — {track}",
                description=f"{album} | {label}",
                thumb_url=image_url,
                input_message_content=InputTextMessageContent(
                    message_text=caption, parse_mode="Markdown"
                ),
                reply_markup=keyboard,
            )
        )

    # === Если это текст (поиск по названию) ===
    else:
        items = await search_spotify_tracks(text)
        if not items:
            await query.answer([], cache_time=1, is_personal=True)
            return

        for item in items:
            track_id = item.get("id")
            track = item.get("name", "Unknown")
            artist = ", ".join(a["name"] for a in item.get("artists", [])) or "Unknown"
            album = item.get("album", {}).get("name", "")
            image_url = item.get("album", {}).get("images", [{}])[0].get("url")
            spotify_url = item.get("external_urls", {}).get("spotify", "")
            album_id = item.get("album", {}).get("id")
            label = item.get("album", {}).get("label") or await get_album_label(
                album_id
            )
            release_date = format_date_ru(
                item.get("album", {}).get("release_date", "Unknown Date")
            )

            caption = (
                f"`{artist} — {track}`\n"
                f"***{album}***\n\n"
                f"Release date: {release_date}\n"
                f"Label: {label}"
            )

            keyboard = generate_keyboard(track, artist, spotify_url, "spotify")

            results.append(
                InlineQueryResultArticle(
                    id=track_id,
                    title=f"{artist} — {track}",
                    description=f"{album} | {label}",
                    thumb_url=image_url,
                    input_message_content=InputTextMessageContent(
                        message_text=caption, parse_mode="Markdown"
                    ),
                    reply_markup=keyboard,
                )
            )

    await query.answer(results, cache_time=1, is_personal=True)


# === Обработка ссылок (сообщений) ===
@dp.message()
async def handle_music_link(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()

    # === Короткие ссылки ===
    if "spotify.link/" in url:
        url = await resolve_spotify_link(url)
        if not url:
            await message.reply("Не удалось раскрыть короткую ссылку 😕")
            return

    # === Парсим URL ===
    if any(domain in url for domain in ['open.spotify.com', 'music.apple.com', 'music.yandex.ru', 'soundcloud.com']):
        track_info = await parse_music_url(url)
        if not track_info:
            await message.reply("Не удалось получить информацию о треке 😢")
            return

        artist = track_info["artist"]
        track = track_info["track"]
        album = track_info["album"]
        image_url = track_info["image"]
        label = track_info["label"]
        release_date = track_info["release_date"]
        source = track_info.get("source", "spotify")
        source_url = track_info.get("source_url", url)

        caption = (
            f"`{artist} — {track}`\n"
            f"***{album}***\n\n"
            f"Release date: {release_date}\n"
            f"Label: {label}"
        )

        keyboard = generate_keyboard(track, artist, source_url, source)

        if image_url:
            sent_message = await bot.send_photo(
                chat_id=message.chat.id,
                photo=image_url,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            sent_message = await bot.send_message(
                chat_id=message.chat.id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

        if should_auto_delete(message.chat) and sent_message:
            asyncio.create_task(auto_delete_messages(AUTO_DELETE_DELAY, [message]))
    else:
        return


# === Событие запуска ===
async def on_startup():
    logging.info("✅ Бот запущен и готов к работе (включая inline-режим)")


dp.startup.register(on_startup)


# === Запуск ===
async def main():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"❌ Бот упал: {e}")
    finally:
        await bot.session.close()
        logging.info("🧩 Бот завершил работу корректно.")


if __name__ == "__main__":
    asyncio.run(main())
