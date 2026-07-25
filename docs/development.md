# DEV Setup Guide

Этот документ описывает локальную разработку, тестирование, ветвление и деплой для `Music Info Bot`.

## Стек разработки

- `Python 3`
- `venv`
- `aiogram 3`
- `aiohttp`
- `beautifulsoup4`
- `yandex-music`
- `sqlite`
- `pytest`, `pytest-asyncio`, `pytest-cov`
- `flake8`
- `GitHub Actions`
- `Docker`
- `systemd`

## Структура проекта

Сейчас проект уже не монолитный и разделён на модули:

- [`bot.py`](../bot.py) — совместимая точка входа
- [`app/config.py`](../app/config.py) — переменные окружения и runtime-конфиг
- [`app/cache.py`](../app/cache.py) — `sqlite`-кеш
- [`app/formatting.py`](../app/formatting.py) — форматирование и текстовые представления
- [`app/sources.py`](../app/sources.py) — интеграции и парсеры источников
- [`app/telegram_app.py`](../app/telegram_app.py) — Telegram handlers и orchestration
- [`tests/unit/`](../tests/unit) — юнит-тесты
- [`tests/integration/`](../tests/integration) — интеграционные проверки
- [`tests/e2e/`](../tests/e2e) — smoke/e2e сценарии

## Структура окружений

| Окружение | Назначение |
|---|---|
| `main` | актуальная стабильная ветка |
| feature-ветки | доработка отдельных задач |
| локальный запуск | ручная проверка в Telegram |
| VPS/Docker Compose | production runtime |

## 1. Клонирование проекта

```bash
git clone git@github.com:eolv1n/spotify_bot.git
cd spotify_bot
```

## 2. Виртуальное окружение

Если `venv` ещё нет:

```bash
python3 -m venv venv
```

Активация:

```bash
source venv/bin/activate
```

Установка зависимостей:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 3. Настройка `.env`

Создай файл `.env` в корне проекта:

```env
TELEGRAM_TOKEN=your_test_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
AUTO_DELETE_DELAY=0
CACHE_DB_PATH=cache/music_cache.sqlite3
CACHE_TTL_SECONDS=43200
```

### Где взять Spotify ключи

1. Открой `https://developer.spotify.com/dashboard`
2. Создай приложение
3. Возьми `Client ID`
4. Открой `View client secret` и забери `Client Secret`

### Важно

- не коммить `.env`
- не публикуй токены в README, issue и PR
- если секрет случайно утёк, перевыпусти его

## 4. Локальный запуск бота

```bash
venv/bin/python bot.py
```

После запуска можно писать тестовому боту в Telegram и отправлять ссылки:

- `Spotify`
- `Apple Music`
- `SoundCloud`
- `Яндекс.Музыка`

### Локальный запуск через Docker без WireGuard

Для dev-среды не используй базовый `docker-compose.yml`: он описывает продовый
контур и всегда тянет `wireguard`.

Подними отдельный dev-контур:

```bash
cp .env.dev.example .env.dev
# заполни .env.dev токеном тестового Telegram-бота и Spotify credentials
docker compose -f deploy/docker-compose.dev.yml up -d --build
```

Проверить логи:

```bash
docker logs -f spotify_bot_dev
```

Остановить:

```bash
docker compose -f deploy/docker-compose.dev.yml down
```

Dev-контур специально использует отдельные имена:

- контейнер: `spotify_bot_dev`
- образ: `spotify_bot:dev`
- env-файл: `.env.dev`
- кеш: `./cache/dev`

## 5. Локальные тесты

Полный прогон:

```bash
venv/bin/python -m pytest -q
```

Проверка синтаксиса:

```bash
python3 -m py_compile bot.py app/*.py
```

Линтер:

```bash
venv/bin/python -m flake8
```

## 6. Smoke-test сценарий

Минимальный smoke-test перед пушем:

1. Запустить бота локально
2. Проверить `/help`
3. Отправить Spotify-ссылку
4. Отправить Apple Music-ссылку
5. Отправить SoundCloud-ссылку
6. Отправить ссылку Яндекс.Музыки
7. Проверить inline-поиск по тексту
8. Проверить, что бот не падает на невалидной ссылке

## 7. Рабочий git-flow

Создать ветку под задачу:

```bash
git switch -c feature/my-change
```

Проверить статус:

```bash
git status
```

Закоммитить изменения:

```bash
git add .
git commit -m "feat: short description"
```

Подтянуть свежий `main` перед финализацией:

```bash
git fetch origin
git rebase origin/main
```

## 8. GitHub Actions

CI сейчас используется для:

- запуска тестов
- расчёта coverage
- публикации артефактов отчётов
- базовой проверки качества кода

Перед пушем локально желательно повторить хотя бы:

```bash
venv/bin/python -m flake8
venv/bin/python -m pytest -q
```

Локальную тестовую и runtime-грязь можно быстро убрать так:

```bash
bash scripts/clean.sh
```

## 9. Docker и прод

В проекте есть:

- [`Dockerfile`](../Dockerfile)
- [`docker-compose.yml`](../docker-compose.yml)
- [`deploy/docker-compose.dev.yml`](../deploy/docker-compose.dev.yml)
- [`deploy.sh`](../deploy.sh)
- [`deploy/wireguard/wg_confs/wg0.conf.example`](../deploy/wireguard/wg_confs/wg0.conf.example)
- [`scripts/diag_wg.sh`](../scripts/diag_wg.sh)

Продовый запуск рассчитан на базовый `docker compose`:

- сервис `wireguard` поднимает WG-клиент
- сервис `spotify_bot` использует `network_mode: service:wireguard`
- весь сетевой стек бота идёт через контейнер `wireguard`

Локальный dev-запуск вынесен в `deploy/docker-compose.dev.yml`, чтобы тестовый
контур не зависел от WireGuard и не использовал production runtime-настройки.

Перед первым деплоем на сервере:

```bash
sudo install -d -m 700 /opt/spotify_bot_runtime/wireguard/wg_confs
sudo cp deploy/wireguard/wg_confs/wg0.conf.example \
  /opt/spotify_bot_runtime/wireguard/wg_confs/wg0.conf
sudo chmod 600 /opt/spotify_bot_runtime/wireguard/wg_confs/wg0.conf
```

После этого заполни `wg0.conf` своими ключами и endpoint.

Важно:

- живой `WireGuard`-конфиг хранится вне git-репозитория
- это защищает деплой от конфликтов прав доступа после запуска контейнера
- при необходимости можно переопределить путь через `WG_CONFIG_DIR`

Обычный деплой через сервер:

```bash
ssh <server>
cd /opt/spotify_bot
./deploy.sh
```

Полный production layout и bootstrap описаны в
[`README.md`](../README.md#установка-на-новый-сервер).

## 10. Отладка на сервере

Проверить состояние compose-сервисов:

```bash
docker compose ps
```

Базовая диагностика WireGuard и маршрута до Яндекса:

```bash
bash scripts/diag_wg.sh
```

Посмотреть последние логи:

```bash
docker logs --tail=50 spotify_bot_wg
docker logs --tail=50 spotify_bot
```

## 11. Что стоит улучшить дальше

- разнести `app/sources.py` на отдельные адаптеры по сервисам
- улучшить парсинг `Apple Music` и `SoundCloud`
- расширить интеграционные и e2e-тесты
