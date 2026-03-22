# Music Info Bot

Telegram-бот для разбора музыкальных ссылок и показа информации о треках. Проект начинался как Spotify-бот, а сейчас развивается в универсальный music-link parser с упором на Python, DevOps-практику и аккуратный CI/CD.

## Что умеет бот

- Принимает ссылки на треки из `Spotify`, `Apple Music`, `SoundCloud` и `Яндекс.Музыки`
- Показывает исполнителя, трек, альбом, дату релиза и источник
- Поддерживает `spotify.link`
- Работает в обычных сообщениях и в inline-режиме
- Для Spotify использует официальный API
- Для Apple Music и SoundCloud использует HTML/OpenGraph-парсинг и эвристики
- Для Яндекс.Музыки использует open-source библиотеку `yandex-music`
- Кеширует результаты разбора ссылок в `sqlite`

## Текущий статус интеграций

| Источник | Статус | Как работает |
|---|---|---|
| Spotify | Стабильно | Официальный Spotify Web API |
| Apple Music | Работает | OpenGraph и HTML-парсинг |
| SoundCloud | Работает | OpenGraph и HTML-парсинг |
| Яндекс.Музыка | Работает | `yandex-music` open-source client |

## Стек

### Backend

- `Python 3`
- `aiogram 3`
- `aiohttp`
- `python-dotenv`
- `beautifulsoup4`
- `yandex-music`
- `sqlite3` из стандартной библиотеки

### Тесты и качество

- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `flake8`

### Инфраструктура и DevOps

- `Git` и GitHub
- `GitHub Actions`
- `Docker` и `docker-compose`
- `systemd`
- `Linux / Bash`

## Архитектура

Основная логика сейчас находится в [`bot.py`](/home/eolv1n/projects/spotify_bot/bot.py).

Ключевые блоки:

- Telegram-бот и роутинг сообщений на `aiogram`
- Spotify API-клиент для авторизации и получения метаданных
- Парсеры `Apple Music`, `SoundCloud`
- Интеграция с `Яндекс.Музыкой` через open-source client `yandex-music`
- Универсальная функция `parse_music_url(...)`
- Локальный `sqlite`-кеш для уже разобранных URL
- Inline-поиск по Spotify

## Переменные окружения

Минимально нужны:

```env
TELEGRAM_TOKEN=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
```

Дополнительно:

```env
AUTO_DELETE_DELAY=0
CACHE_DB_PATH=cache/music_cache.sqlite3
CACHE_TTL_SECONDS=43200
```

## Быстрый старт

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env  # если создашь шаблон
python3 bot.py
```

Если `.env.example` нет, создай `.env` вручную.

## Тесты

```bash
venv/bin/python -m pytest -q
```

Проверка синтаксиса:

```bash
python3 -m py_compile bot.py
```

## Что уже проверено

- Юнит-тесты проходят локально
- Работает локальная авторизация Spotify
- Живые тесты в Telegram подтвердили работу Spotify, Apple Music и SoundCloud
- Яндекс.Музыка переведена с HTML-парсинга на open-source client `yandex-music`

## Известные ограничения

- `Apple Music` и `SoundCloud` пока разбираются эвристически, поэтому часть метаданных может быть неполной
- Весь runtime пока сосредоточен в одном файле `bot.py`; следующий шаг — вынести адаптеры источников в отдельные модули

## Репозиторий

- GitHub: `github.com/eolv1n/spotify_bot`
- Telegram: `@eolv1n`
