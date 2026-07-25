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

Точка входа проекта — [`bot.py`](bot.py), но основная логика разложена по
модулям в [`app/`](app).

Текущие модули:

- [`app/config.py`](app/config.py) — загрузка `.env`, настройка runtime и валидация окружения
- [`app/cache.py`](app/cache.py) — `sqlite`-кеш для уже разобранных URL
- [`app/formatting.py`](app/formatting.py) — форматирование дат, caption и display-логика
- [`app/sources.py`](app/sources.py) — интеграции и парсеры `Spotify`, `Apple Music`, `SoundCloud`, `Яндекс.Музыки`
- [`app/telegram_app.py`](app/telegram_app.py) — `aiogram` handlers, inline-режим и обработка сообщений

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

Скачай installer, при необходимости просмотри его, и запусти локальный файл от root:

```bash
curl -fLO https://raw.githubusercontent.com/eolv1n/spotify_bot/main/install.sh
less install.sh
sudo bash ./install.sh
```

Если нужно переопределить путь или ветку:

```bash
curl -fLO https://raw.githubusercontent.com/eolv1n/spotify_bot/main/install.sh
sudo env INSTALL_DIR=/opt/spotify_bot REPO_REF=main bash ./install.sh
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

Перед переносом production на другой VPS пройди
[чек-лист миграции](docs/operations/server-migration.md). В нём отдельно учтены
staging без второго Telegram poller, cutover, rollback и критерии отключения
старого сервера.

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
cp .env.example .env
python3 bot.py
```

Подробные команды разработки, тестирования и диагностики собраны в
[`docs/development.md`](docs/development.md).

## Docker для dev

Для локальной проверки без WireGuard используй отдельный compose-файл:

```bash
cp .env.dev.example .env.dev
# заполни .env.dev тестовыми токенами
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

Этот контур не поднимает `wireguard`, не использует `network_mode: service:wireguard`
и по умолчанию читает именно `.env.dev`. Обычный `docker-compose.yml` в корне
остаётся production entrypoint с WireGuard.

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
  docs/
    README.md
    development.md
    operations/
      server-migration.md
  deploy/
    docker-compose.dev.yml
    install.conf.example
    wireguard/
  scripts/
    bootstrap_server.sh
    clean.sh
    diag_wg.sh
    server_check.sh
  bot.py
  Dockerfile
  docker-compose.yml
  deploy.sh
  install.sh
```

## Тесты

```bash
venv/bin/python -m pytest -q
```

Проверка синтаксиса:

```bash
python3 -m py_compile bot.py app/*.py
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
