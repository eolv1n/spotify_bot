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

## Структура окружений

| Окружение | Назначение |
|---|---|
| `main` | актуальная стабильная ветка |
| feature-ветки | доработка отдельных задач |
| локальный запуск | ручная проверка в Telegram |
| VPS/systemd | продакшен или постоянный тестовый стенд |

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

## 5. Локальные тесты

Полный прогон:

```bash
venv/bin/python -m pytest -q
```

Проверка синтаксиса:

```bash
python3 -m py_compile bot.py
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
venv/bin/python -m pytest -q
```

## 9. Docker и прод

В проекте есть:

- [`Dockerfile`](/home/eolv1n/projects/spotify_bot/Dockerfile)
- [`docker-compose.yml`](/home/eolv1n/projects/spotify_bot/docker-compose.yml)
- [`deploy.sh`](/home/eolv1n/projects/spotify_bot/deploy.sh)

Если деплой идёт через сервер:

```bash
ssh <server>
cd ~/spotify_bot
git pull origin main
sudo systemctl restart spotify_bot
sudo systemctl status spotify_bot -l
```

## 10. Отладка на сервере

Проверить статус сервиса:

```bash
sudo systemctl status spotify_bot -l
```

Посмотреть последние ошибки:

```bash
sudo tail -n 50 /var/log/spotify_bot_error.log
```

Если нужен ручной health-check:

```bash
bash server_check.sh
```

## 11. Что стоит улучшить дальше

- вынести source adapters из `bot.py` в отдельные модули
- улучшить парсинг `Apple Music` и `SoundCloud`
- добавить `.env.example`
- расширить интеграционные и e2e-тесты
