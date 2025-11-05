import re
import logging
import aiohttp
import asyncio
import os
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

# === Настройка логов ===
logging.basicConfig(level=logging.INFO)

# === Загрузка .env ===
load_dotenv()

# === Настройки окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
AUTO_DELETE_DELAY_RAW = os.getenv("AUTO_DELETE_DELAY", "0")

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

if not TELEGRAM_TOKEN or not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("❌ Не найдены необходимые переменные окружения! Проверь .env файл.")

# === Создаем бота и диспетчер ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === /help ===
@dp.message(Command("help"))
@dp.message(F.text.lower().startswith("/help"))
async def send_help(message: types.Message):
    text = (
        "🎧 <b>Spotify Info Bot</b>\n\n"
        "Я помогу узнать информацию о треках Spotify и найти их в других музыкальных сервисах.\n\n"
        "📌 <b>Что я умею:</b>\n"
        "• Отправь ссылку на трек Spotify — я покажу исполнителя, название и альбом.\n"
        "• Работаю в личных сообщениях и в групповых чатах.\n"
        "• Можно использовать в inline-режиме — просто напиши <code>@имя_бота</code> и вставь ссылку на трек.\n"
        "• Поддерживаются ссылки на Spotify и короткие ссылки <code>spotify.link</code>.\n\n"
        "🎵 В карточке трека ты найдёшь кнопки для перехода на Spotify, YouTube Music, Apple Music, "
        "Яндекс.Музыку, SoundCloud и ВКонтакте.\n\n"
        "📖 <b>Пример:</b>\n"
        "<code>https://open.spotify.com/track/xxxxxxxxxxxxxxxx</code>"
    )
    await message.answer(text, parse_mode="HTML")

# === Spotify Auth ===
async def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, data=data, auth=aiohttp.BasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        ) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")

# === Извлекаем ID трека ===
def extract_track_id(spotify_url: str):
    match = re.search(r"track/([A-Za-z0-9]+)", spotify_url)
    return match.group(1) if match else None

# === Раскрываем короткие ссылки ===
async def resolve_spotify_link(short_url: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(short_url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception as e:
            logging.error(f"Ошибка раскрытия ссылки: {e}")
            return None

# === Получаем информацию о треке ===
async def get_track_info(track_id: str):
    token = await get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.spotify.com/v1/tracks/{track_id}", headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

            artist_names = ", ".join(artist["name"] for artist in data["artists"])
            track_name = data["name"]
            album_data = data["album"]
            album_name = album_data["name"]
            album_id = album_data["id"]
            image_url = album_data["images"][0]["url"] if album_data.get("images") else None
            release_date = album_data.get("release_date", "Unknown Date")

        # Получаем лейбл
        async with session.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers) as album_resp:
            if album_resp.status == 200:
                album_json = await album_resp.json()
                label = album_json.get("label", "Unknown Label")
            else:
                label = "Unknown Label"

        return {
            "artist": artist_names,
            "track": track_name,
            "album": album_name,
            "image": image_url,
            "label": label,
            "release_date": release_date,
        }
    
# === Получаем треки из плейлиста ===
async def get_playlist_tracks(playlist_url: str):
    match = re.search(r"playlist/([A-Za-z0-9]+)", playlist_url)
    if not match:
        return "❌ Не удалось распознать ссылку на плейлист."

    playlist_id = match.group(1)
    token = await get_spotify_token()
    if not token:
        return "⚠️ Не удалось получить токен Spotify."

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", headers=headers
        ) as resp:
            if resp.status != 200:
                return f"❌ Ошибка при получении данных: {resp.status}"
            data = await resp.json()

    tracks = []
    for i, item in enumerate(data.get("items", []), start=1):
        track = item.get("track")
        if not track:
            continue
        artist = ", ".join(a["name"] for a in track["artists"])
        name = track["name"]
        label = track.get("album", {}).get("label", "Unknown Label")
        tracks.append(f"{i}. {artist} — {name} [{label}]")

    if not tracks:
        return "⚠️ В плейлисте нет треков или доступ ограничен."

    playlist_text = "\n".join(tracks)
    return f"📜 <b>Список треков из плейлиста:</b>\n\n{playlist_text}"

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
def generate_keyboard(track, artist, spotify_url):
    query_encoded = quote(f"{track} {artist}")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Spotify", url=spotify_url)],
            [
                InlineKeyboardButton(text="🎵 ВКонтакте", url="https://vk.com/audio"),
                InlineKeyboardButton(text="🎶 Яндекс.Музыка", url=f"https://music.yandex.ru/search?text={query_encoded}"),
            ],
            [
                InlineKeyboardButton(text="☁️ SoundCloud", url=f"https://soundcloud.com/search?q={query_encoded}"),
                InlineKeyboardButton(text="🍎 Apple Music", url=f"https://music.apple.com/search?term={query_encoded}"),
            ],
            [
                InlineKeyboardButton(text="▶️ YouTube", url=f"https://www.youtube.com/results?search_query={query_encoded}"),
                InlineKeyboardButton(text="🎵 YouTube Music", url=f"https://music.youtube.com/search?q={query_encoded}")
            ]
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
# === Отправка длинного текста ===
async def send_long_message(bot, chat_id, text, parse_mode="HTML"):
    MAX_LENGTH = 4000
    for i in range(0, len(text), MAX_LENGTH):
        part = text[i:i + MAX_LENGTH]
        await bot.send_message(chat_id, part, parse_mode=parse_mode)

# === Обработка сообщений со ссылками ===
@dp.message()
async def handle_spotify_link(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()

    # === 1️⃣ Проверяем — это ссылка на плейлист? ===
    if "spotify.com/playlist/" in url or "spotify.link/" in url:
        reply_text = await get_playlist_tracks(url)
        await send_long_message(bot, message.chat.id, reply_text, parse_mode="HTML")
        return  # ⚠️ прекращаем выполнение, чтобы не обрабатывать как трек

    # === 2️⃣ Раскрываем короткие ссылки ===
    if "spotify.link/" in url:
        url = await resolve_spotify_link(url)
        if not url:
            await message.reply("Не удалось раскрыть короткую ссылку 😕")
            return

    # === 3️⃣ Проверяем, это трек ===
    if "open.spotify.com/track/" not in url:
        return

    track_id = extract_track_id(url)
    if not track_id:
        await message.reply("Не удалось распознать ссылку 😕")
        return

    track_info = await get_track_info(track_id)
    if not track_info:
        await message.reply("Не удалось получить информацию о треке 😢")
        return

    artist = track_info["artist"]
    track = track_info["track"]
    album = track_info["album"]
    image_url = track_info["image"]
    label = track_info["label"]
    release_date = track_info["release_date"]

    caption = (
        f"`{artist} — {track}`\n"
        f"***{album}***\n\n"
        f"Release date: {release_date}\n"
        f"Label: {label}"
    )

    keyboard = generate_keyboard(track, artist, url)

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

# === Inline-режим ===
@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text:
        return

    results: list[InlineQueryResultArticle] = []

    if "spotify.link/" in text or "open.spotify.com/track/" in text:
        if "spotify.link/" in text:
            text = await resolve_spotify_link(text)
            if not text:
                return

        track_id = extract_track_id(text)
        if not track_id:
            return

        track_info = await get_track_info(track_id)
        if not track_info:
            return

        artist = track_info["artist"]
        track = track_info["track"]
        album = track_info["album"]
        image_url = track_info["image"]
        label = track_info["label"]
        release_date = track_info["release_date"]

        caption = (
            f"`{artist} — {track}`\n"
            f"***{album}***\n\n"
            f"Release date: {release_date}\n"
            f"Label: {label}"
        )

        keyboard = generate_keyboard(track, artist, text)
        results.append(
            InlineQueryResultArticle(
                id=track_id,
                title=f"{artist} — {track}",
                description=album,
                thumb_url=image_url,
                input_message_content=InputTextMessageContent(
                    message_text=caption, parse_mode="Markdown"
                ),
                reply_markup=keyboard,
            )
        )
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
            images = item.get("album", {}).get("images", [])
            image_url = images[0]["url"] if images else None
            spotify_url = item.get("external_urls", {}).get("spotify", "")
            label = item.get("album", {}).get("label", "Unknown Label")
            release_date = item.get("album", {}).get("release_date", "Unknown Date")

            caption = (
                f"`{artist} — {track}`\n"
                f"***{album}***\n\n"
                f"Release date: {release_date}\n"
                f"Label: {label}"
            )

            keyboard = generate_keyboard(track, artist, spotify_url)

            results.append(
                InlineQueryResultArticle(
                    id=track_id or f"{artist}-{track}",
                    title=f"{artist} — {track}",
                    description=album,
                    thumb_url=image_url,
                    input_message_content=InputTextMessageContent(
                        message_text=caption, parse_mode="Markdown"
                    ),
                    reply_markup=keyboard,
                )
            )

    await query.answer(results, cache_time=1, is_personal=True)

# === Событие запуска ===
async def on_startup():
    logging.info("✅ Бот запущен и готов к работе (включая inline-режим)")

dp.startup.register(on_startup)

# === Запуск ===
async def main():
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Бот упал: {e}, перезапуск через 5 секунд")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
