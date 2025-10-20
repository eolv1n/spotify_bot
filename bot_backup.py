import re
import logging
import aiohttp
import asyncio
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram import F

logging.basicConfig(level=logging.INFO)

# === ��������� ===
TELEGRAM_TOKEN = "8308095609:AAFHss0CMKkxOAYjDkOPr7sDeJP-02DSmDo"
SPOTIFY_CLIENT_ID = "5ea15db26330436db6972095e7f51756"
SPOTIFY_CLIENT_SECRET = "f12340e1ba414140b369805fada35ea0"

# === ������� ���� � ��������� ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


# === �������� ����� Spotify ===
async def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, data=data, auth=aiohttp.BasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        ) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")


# === ��������� ID ����� �� ������ ===
def extract_track_id(spotify_url: str):
    match = re.search(r"track/([A-Za-z0-9]+)", spotify_url)
    return match.group(1) if match else None


# === ���������� �������� ������ Spotify ===
async def resolve_spotify_link(short_url: str) -> str:
    """���������� �������� ������ Spotify �� ������� URL"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(short_url, allow_redirects=True) as resp:
                return str(resp.url)
        except Exception as e:
            logging.error(f"������ ��������� ������: {e}")
            return None


# === �������� ���������� � ����� ===
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
            album_name = data["album"]["name"]
            image_url = data["album"]["images"][0]["url"] if data["album"]["images"] else None
            return {"artist": artist_names, "track": track_name, "album": album_name, "image": image_url}


# === ��������� ���������� �� �������� ===
def generate_keyboard(track, artist, spotify_url):
    query_encoded = quote(f"{track} {artist}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="������� �� Spotify", url=spotify_url)],
            [
                InlineKeyboardButton(text="���������", url="https://vk.com/audio"),
                InlineKeyboardButton(text="������.������", url=f"https://music.yandex.ru/search?text={query_encoded}"),
            ],
            [
                InlineKeyboardButton(text="SoundCloud", url=f"https://soundcloud.com/search?q={query_encoded}"),
                InlineKeyboardButton(text="Apple Music", url=f"https://music.apple.com/search?term={query_encoded}"),
            ],
            [
                InlineKeyboardButton(text="YouTube", url=f"https://www.youtube.com/results?search_query={query_encoded}")
            ]
        ]
    )


# === ��������� ��������� � �������� (�������� � � �����, � � ��) ===
@dp.message()
async def handle_spotify_link(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()

    # ���������� �������� ������
    if "spotify.link/" in url:
        url = await resolve_spotify_link(url)
        if not url:
            await message.reply("�� ������� �������� �������� ������ ??")
            return

    if "open.spotify.com/track/" not in url:
        return

    track_id = extract_track_id(url)
    if not track_id:
        await message.reply("�� ������� ���������� ������ ??")
        return

    track_info = await get_track_info(track_id)
    if not track_info:
        await message.reply("�� ������� �������� ���������� � ����� ??")
        return

    artist = track_info["artist"]
    track = track_info["track"]
    album = track_info["album"]
    image_url = track_info["image"]

    # ��������������: ������� � ���� � ������������, ������ � ������ ������
    caption = f"`{artist} � {track}`\n***{album}***"
    keyboard = generate_keyboard(track, artist, url)

    if image_url:
        await message.reply_photo(photo=image_url, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await message.reply(caption, parse_mode="Markdown", reply_markup=keyboard)


# === Inline-����� (@botname + ������) ===
@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text:
        return

    # ���������� �������� ������
    if "spotify.link/" in text:
        text = await resolve_spotify_link(text)
        if not text:
            return

    if "open.spotify.com/track/" not in text:
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

    caption = f"`{artist} � {track}`\n***{album}***"
    keyboard = generate_keyboard(track, artist, text)

    result = InlineQueryResultArticle(
        id=track_id,
        title=f"{artist} � {track}",
        description=album,
        thumb_url=image_url,
        input_message_content=InputTextMessageContent(
            message_text=caption,
            parse_mode="Markdown"
        ),
        reply_markup=keyboard
    )

    await query.answer([result], cache_time=1, is_personal=True)


# === ������� ������� ===
async def on_startup():
    logging.info("? ��� ������� � ����� � ������ (������� inline-�����)")


dp.startup.register(on_startup)


# === ������ ===
async def main():
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"��� ����: {e}, ���������� ����� 5 ������")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
