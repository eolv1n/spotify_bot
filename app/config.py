import logging
import os

from dotenv import load_dotenv


def load_environment():
    # In tests/CI we allow fake credentials so imports do not fail.
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI") == "true":
        for key in ("TELEGRAM_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
            os.environ.setdefault(key, f"fake-{key.lower()}")
    else:
        load_dotenv()
        required = ["TELEGRAM_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
        missing = [value for value in required if not os.getenv(value)]
        if missing:
            raise ValueError(
                f"❌ Не найдены необходимые переменные окружения: {missing}. Проверь .env файл."
            )

    load_dotenv()


def _parse_auto_delete_delay(raw_value: str) -> int:
    try:
        delay = int(raw_value)
        if delay < 0:
            raise ValueError
    except (TypeError, ValueError):
        logging.warning(
            "Некорректное значение AUTO_DELETE_DELAY='%s'. Автоудаление отключено.",
            raw_value,
        )
        return 0
    else:
        if delay > 0:
            logging.info(
                "🕒 Автоудаление сообщений включено. Задержка: %s секунд.",
                delay,
            )
        return delay


def _parse_cache_ttl(raw_value: str) -> int:
    try:
        ttl = int(raw_value)
        if ttl <= 0:
            raise ValueError
    except (TypeError, ValueError):
        logging.warning(
            "Некорректное значение CACHE_TTL_SECONDS='%s'. Использую 43200 секунд.",
            raw_value,
        )
        return 43200
    return ttl


logging.basicConfig(level=logging.INFO)
load_environment()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
AUTO_DELETE_DELAY = _parse_auto_delete_delay(os.getenv("AUTO_DELETE_DELAY", "0"))
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache/music_cache.sqlite3")
CACHE_TTL_SECONDS = _parse_cache_ttl(os.getenv("CACHE_TTL_SECONDS", "43200"))

if not TELEGRAM_TOKEN or not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("❌ Не найдены необходимые переменные окружения! Проверь .env файл.")
