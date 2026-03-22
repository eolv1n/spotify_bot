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

Точка входа проекта — [`bot.py`](/home/eolv1n/projects/spotify_bot/bot.py), но основная логика теперь разложена по модульной структуре в [`app/`](/home/eolv1n/projects/spotify_bot/app).

Текущие модули:

- [`app/config.py`](/home/eolv1n/projects/spotify_bot/app/config.py) — загрузка `.env`, настройка runtime и валидация окружения
- [`app/cache.py`](/home/eolv1n/projects/spotify_bot/app/cache.py) — `sqlite`-кеш для уже разобранных URL
- [`app/formatting.py`](/home/eolv1n/projects/spotify_bot/app/formatting.py) — форматирование дат, caption и display-логика
- [`app/sources.py`](/home/eolv1n/projects/spotify_bot/app/sources.py) — интеграции и парсеры `Spotify`, `Apple Music`, `SoundCloud`, `Яндекс.Музыки`
- [`app/telegram_app.py`](/home/eolv1n/projects/spotify_bot/app/telegram_app.py) — `aiogram` handlers, inline-режим и обработка сообщений

Что это даёт:

- код больше не живёт одним монолитом
- легче добавлять новые источники
- проще тестировать source-логику отдельно от Telegram-слоя
- меньше риск ломать весь бот при точечной правке одного адаптера

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

Для серверного деплоя теперь удобнее держать этот файл вне репозитория, например в
`/opt/spotify_bot_runtime/bot.env`.

## Установка на новый сервер

Теперь проект можно раскладывать как "инфраструктуру как код": код живёт отдельно,
runtime-конфиги отдельно, а установка делается одним bootstrap-скриптом.

Самый быстрый вариант для нового сервера:

```bash
curl -fsSL https://raw.githubusercontent.com/eolv1n/spotify_bot/main/install.sh | sudo bash
```

Если нужно переопределить путь или ветку:

```bash
curl -fsSL https://raw.githubusercontent.com/eolv1n/spotify_bot/main/install.sh | \
  sudo INSTALL_DIR=/opt/spotify_bot REPO_REF=main bash
```

Этот инсталлер:

- при необходимости поставит `git`
- склонирует или обновит репозиторий в `INSTALL_DIR`
- запустит внутренний bootstrap, который уже поставит `Docker` и подготовит runtime

Ручной сценарий тоже остаётся доступным:

1. Склонируй репозиторий или скачай его на сервер.
2. Скопируй шаблон install-конфига:

```bash
cp deploy/install.conf.example deploy/install.conf
```

3. При необходимости поменяй пути и ветку в `deploy/install.conf`.
4. Запусти bootstrap:

```bash
sudo bash scripts/bootstrap_server.sh
```

Что сделает bootstrap:

- установит `Docker`, `docker compose` и `Git` на Debian/Ubuntu
- склонирует или обновит репозиторий в `INSTALL_DIR`
- создаст runtime-директории
- создаст шаблоны `bot.env` и `wg0.conf`, если их ещё нет
- запустит `deploy.sh`, если конфиги уже заполнены

Runtime по умолчанию:

- env-файл: `/opt/spotify_bot_runtime/bot.env`
- кеш: `/opt/spotify_bot_runtime/cache`
- WireGuard: `/opt/spotify_bot_runtime/wireguard/wg_confs/wg0.conf`

Если bootstrap создал шаблоны впервые, он остановится и попросит заполнить:

- `/opt/spotify_bot_runtime/bot.env`
- `/opt/spotify_bot_runtime/wireguard/wg_confs/wg0.conf`

После этого достаточно повторно выполнить:

```bash
sudo /opt/spotify_bot/deploy.sh
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

## Структура проекта

```text
spotify_bot/
  app/
    config.py
    cache.py
    formatting.py
    sources.py
    telegram_app.py
  tests/
    unit/
    integration/
    e2e/
  bot.py
  Dockerfile
  docker-compose.yml
  deploy.sh
  install.sh
  deploy/
    install.conf.example
  scripts/
    bootstrap_server.sh
```

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
- Для `Яндекс.Музыки` стабильность может зависеть от сетевой доступности `api.music.yandex.net` из региона, где запущен сервер

## Репозиторий

- GitHub: `github.com/eolv1n/spotify_bot`
- Telegram: `@eolv1n`
