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
    logging.warning("Некорректное значение AUTO_DELETE_DELAY='%s'. Автоудаление отключено.", AUTO_DELETE_DELAY_RAW)
    AUTO_DELETE_DELAY = 0
else:
    if AUTO_DELETE_DELAY > 0:
        logging.info("🕒 Автоудаление сообщений включено. Задержка: %s секунд.", AUTO_DELETE_DELAY)

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
        "• Отправь ссылку на трек или плейлист Spotify — я покажу подробности.\n"
        "• Работаю в личных сообщениях и группах.\n"
        "• Поддерживаю короткие ссылки <code>spotify.link</code>.\n\n"
        "🎵 Inline режим: напиши <code>@имя_бота</code> и вставь ссылку на трек.\n\n"
        "📖 Пример:\n"
        "<code>https://open.spotify.com/track/xxxxxxxxxxxxxxxx</code>"
    )
    await message.answer(text, parse_mode="HTML")


# === Spotify Auth ===
async def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, auth=aiohttp.BasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)) as resp:
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


# === Получаем треки из плейлиста (с пагинацией и лейблами) ===
async def get_playlist_tracks(playlist_url: str):
    match = re.search(r"playlist/([A-Za-z0-9]+)", playlist_url)
    if not match:
        return ["❌ Не удалось распознать ссылку на плейлист."], playlist_url

    playlist_id = match.group(1)
    token = await get_spotify_token()
    if not token:
        return ["⚠️ Не удалось получить токен Spotify."], playlist_url

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # 🔹 Получаем основную информацию о плейлисте
        async with session.get(f"https://api.spotify.com/v1/playlists/{playlist_id}", headers=headers) as resp:
            if resp.status != 200:
                txt = await resp.text()
                logging.error(f"Ошибка Spotify API ({resp.status}): {txt}")
                return [f"❌ Ошибка при получении плейлиста: {resp.status}"], playlist_url
            playlist_data = await resp.json()

        playlist_name = playlist_data.get("name", "Без названия")
        playlist_owner = playlist_data.get("owner", {}).get("display_name", "Неизвестный автор")
        playlist_url_full = playlist_data.get("external_urls", {}).get("spotify", playlist_url)

        # 🔹 Загружаем все треки с пагинацией
        limit = 100
        offset = 0
        all_tracks = []

        while True:
            url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit={limit}&offset={offset}"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logging.error(f"Ошибка при загрузке треков: {resp.status}")
                    break
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    break
                all_tracks.extend(items)
                offset += limit
                logging.info(f"📦 Загружено {len(all_tracks)} треков...")

        if not all_tracks:
            return ["⚠️ В плейлисте нет треков или доступ ограничен."], playlist_url_full

        # 🔹 Извлекаем треки с лейблами
        tracks = []
        album_cache = {}

        for i, item in enumerate(all_tracks, start=1):
            track = item.get("track")
            if not track:
                continue

            artist = ", ".join(a["name"] for a in track["artists"])
            name = track["name"]
            album_id = track.get("album", {}).get("id")

            label = "Unknown Label"
            if album_id:
                if album_id in album_cache:
                    label = album_cache[album_id]
                else:
                    try:
                        async with session.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers) as album_resp:
                            if album_resp.status == 200:
                                album_data = await album_resp.json()
                                label = album_data.get("label", "Unknown Label")
                                album_cache[album_id] = label
                    except Exception as e:
                        logging.error(f"Ошибка при получении альбома {album_id}: {e}")

            tracks.append(f"{i}. {artist} — {name} [{label}]")
            await asyncio.sleep(0.05)

        header = f"📀 <b>{playlist_name}</b>\n👤 {playlist_owner}\n\n"
        footer = f"\n\n💿 Всего треков: {len(tracks)}"
        full_text = header + "\n".join(tracks) + footer

        MAX_LENGTH = 4000
        parts = [full_text[i:i + MAX_LENGTH] for i in range(0, len(full_text), MAX_LENGTH)]

        return parts, playlist_url_full

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


# === Обработка ссылок ===
@dp.message()
async def handle_spotify_link(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()

    # === Плейлист ===
    if "spotify.com/playlist/" in url or "spotify.link/" in url:
        playlist_parts, playlist_url = await get_playlist_tracks(url)

        # отправляем все части, кнопку добавляем только в последней
        for i, part in enumerate(playlist_parts):
            reply_markup = None
            if i == len(playlist_parts) - 1:  # последняя часть
                reply_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🎧 Открыть плейлист в Spotify", url=playlist_url)]
                    ]
                )

            await bot.send_message(
                message.chat.id,
                part,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        # удаляем исходное сообщение, если нужно
        if should_auto_delete(message.chat):
            asyncio.create_task(auto_delete_messages(AUTO_DELETE_DELAY, [message]))
        return


    # === Короткие ссылки ===
    if "spotify.link/" in url:
        url = await resolve_spotify_link(url)
        if not url:
            await message.reply("Не удалось раскрыть короткую ссылку 😕")
            return

    # === Трек ===
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

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎧 Spotify", url=url)]])

    if image_url:
        await bot.send_photo(message.chat.id, photo=image_url, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await bot.send_message(message.chat.id, text=caption, parse_mode="Markdown", reply_markup=keyboard)

    if should_auto_delete(message.chat):
        asyncio.create_task(auto_delete_messages(AUTO_DELETE_DELAY, [message]))


# === Запуск ===
async def on_startup():
    logging.info("✅ Бот запущен и готов к работе (включая inline-режим)")

dp.startup.register(on_startup)


async def main():
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Бот упал: {e}, перезапуск через 5 секунд")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
