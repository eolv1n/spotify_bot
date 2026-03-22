import asyncio
import logging
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from app.config import AUTO_DELETE_DELAY, TELEGRAM_TOKEN
from app.formatting import build_caption, build_inline_description
from app.sources import (
    build_unsupported_url_message,
    classify_music_url,
    get_album_label,
    parse_music_url,
    resolve_redirect_url,
    resolve_spotify_link,
    search_spotify_tracks,
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


def build_inline_notice_result(query_text: str, message: str):
    return InlineQueryResultArticle(
        id=f"notice-{hash(query_text)}",
        title="Ссылка пока не поддерживается",
        description=message,
        input_message_content=InputTextMessageContent(message_text=message),
    )


def generate_keyboard(track, artist, source_url, source="spotify"):
    query_encoded = quote(f"{track} {artist}")
    source_button_labels = {
        "spotify": "🎧 Spotify",
        "apple_music": "🍎 Apple Music",
        "yandex_music": "🎶 Яндекс.Музыка",
        "soundcloud": "☁️ SoundCloud",
        "youtube": "▶️ YouTube",
        "youtube_music": "🎵 YouTube Music",
    }
    source_button_label = source_button_labels.get(source, "🔗 Открыть источник")
    music_buttons = [
        (
            "spotify",
            "🎧 Spotify",
            f"https://open.spotify.com/search/{query_encoded}",
        ),
        ("vk", "🎵 ВКонтакте", "https://vk.com/audio"),
        (
            "yandex_music",
            "🎶 Яндекс.Музыка",
            f"https://music.yandex.ru/search?text={query_encoded}",
        ),
        (
            "soundcloud",
            "☁️ SoundCloud",
            f"https://soundcloud.com/search?q={query_encoded}",
        ),
        (
            "apple_music",
            "🍎 Apple Music",
            f"https://music.apple.com/search?term={query_encoded}",
        ),
        (
            "youtube",
            "▶️ YouTube",
            f"https://www.youtube.com/results?search_query={query_encoded}",
        ),
        (
            "youtube_music",
            "🎵 YouTube Music",
            f"https://music.youtube.com/search?q={query_encoded}",
        ),
    ]
    filtered_buttons = [
        InlineKeyboardButton(text=text, url=url)
        for button_source, text, url in music_buttons
        if button_source != source
    ]
    keyboard_rows = [[InlineKeyboardButton(text=source_button_label, url=source_url)]]
    for index in range(0, len(filtered_buttons), 2):
        keyboard_rows.append(filtered_buttons[index:index + 2])

    return InlineKeyboardMarkup(
        inline_keyboard=keyboard_rows
    )


def should_auto_delete(chat: types.Chat) -> bool:
    return AUTO_DELETE_DELAY > 0 and chat.type in {"group", "supergroup"}


async def auto_delete_messages(delay: int, messages: list[types.Message]):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception as exc:
            logging.warning("Не удалось удалить сообщение %s: %s", msg.message_id, exc)


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


@dp.inline_query()
async def inline_handler(query: InlineQuery):
    text = query.query.strip()
    if not text:
        return

    results = []
    initial_classification = classify_music_url(text)
    if initial_classification.get("service") or "spotify.link/" in text:
        if initial_classification.get("service") == "spotify_shortlink":
            text = await resolve_spotify_link(text)
            if not text:
                return
        elif initial_classification.get("service") == "soundcloud_shortlink":
            text = await resolve_redirect_url(text)
            if not text:
                return
        classification = classify_music_url(text)

        if not classification.get("supported"):
            message = build_unsupported_url_message(classification)
            if message:
                results.append(build_inline_notice_result(text, message))
                await query.answer(results, cache_time=1, is_personal=True)
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

        caption = build_caption(artist, track, album, release_date, label, source)
        keyboard = generate_keyboard(track, artist, source_url, source)
        results.append(
            InlineQueryResultArticle(
                id=f"{label.lower()}-{hash(text)}",
                title=f"{artist} — {track}",
                description=build_inline_description(album, label, source),
                thumb_url=image_url,
                input_message_content=InputTextMessageContent(
                    message_text=caption,
                    parse_mode="Markdown",
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
            image_url = item.get("album", {}).get("images", [{}])[0].get("url")
            spotify_url = item.get("external_urls", {}).get("spotify", "")
            album_id = item.get("album", {}).get("id")
            label = item.get("album", {}).get("label") or await get_album_label(album_id)
            release_date = item.get("album", {}).get("release_date", "Unknown Date")
            source = "spotify"

            caption = build_caption(artist, track, album, release_date, label, source)
            keyboard = generate_keyboard(track, artist, spotify_url, source)
            results.append(
                InlineQueryResultArticle(
                    id=track_id,
                    title=f"{artist} — {track}",
                    description=build_inline_description(album, label, source),
                    thumb_url=image_url,
                    input_message_content=InputTextMessageContent(
                        message_text=caption,
                        parse_mode="Markdown",
                    ),
                    reply_markup=keyboard,
                )
            )

    await query.answer(results, cache_time=1, is_personal=True)


@dp.message()
async def handle_music_link(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()
    classification = classify_music_url(url)
    if classification.get("service") == "spotify_shortlink":
        url = await resolve_spotify_link(url)
        if not url:
            await message.reply("Не удалось раскрыть короткую ссылку 😕")
            return
        classification = classify_music_url(url)
    elif classification.get("service") == "soundcloud_shortlink":
        url = await resolve_redirect_url(url)
        if not url:
            await message.reply("Не удалось раскрыть короткую ссылку SoundCloud 😕")
            return
        classification = classify_music_url(url)

    if classification.get("service"):
        if not classification.get("supported"):
            unsupported_message = build_unsupported_url_message(classification)
            if unsupported_message and message.chat.type == "private":
                await message.reply(unsupported_message)
            return

        track_info = await parse_music_url(url)
        if not track_info:
            if message.chat.type == "private":
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

        caption = build_caption(artist, track, album, release_date, label, source)
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


async def on_startup():
    logging.info("✅ Бот запущен и готов к работе (включая inline-режим)")


dp.startup.register(on_startup)


async def main():
    try:
        await dp.start_polling(bot)
    except Exception as exc:
        logging.error("❌ Бот упал: %s", exc)
    finally:
        await bot.session.close()
        logging.info("🧩 Бот завершил работу корректно.")
