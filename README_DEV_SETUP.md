# 🎧 Spotify Bot — DEV / PROD Workflow Guide

## ⚙️ Основные ветки

| Ветка | Назначение |
|--------|------------|
| **`main`** | Боевая версия бота (продакшен). Работает на сервере через `systemd`. |
| **`dev`** | Тестовая ветка для разработки и проверок новых фич локально. |

---

## 🧑‍💻 Локальная разработка

### 1️⃣ Клонировать репозиторий
```bash
git clone git@github.com:eolv1n/spotify_bot.git
cd spotify_bot
```

### 2️⃣ Переключиться на ветку `dev`
```bash
git checkout dev
```

### 3️⃣ Активировать виртуальное окружение
```bash
source venv/bin/activate
```

Если окружения нет:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### 4️⃣ Настроить `.env`
Создай или обнови файл `.env` в корне проекта:

```bash
TELEGRAM_TOKEN=твой_токен_бота
SPOTIFY_CLIENT_ID=spotify_client_id
SPOTIFY_CLIENT_SECRET=spotify_client_secret
AUTO_DELETE_DELAY=10
```

- `AUTO_DELETE_DELAY` — время (в секундах), через которое бот удаляет сообщения в группах.  
  Если не нужно автоудаление — поставь `0`.

---

### 5️⃣ Запуск локально
```bash
python3 bot.py
```

Бот запустится в тестовом режиме, можно проверять функционал прямо в Telegram.

---

## 🚀 После доработки

### 6️⃣ Проверить и закоммитить изменения
```bash
git status
git add .
git commit -m "описание новой фичи"
```

### 7️⃣ Отправить на GitHub
```bash
git push origin dev
```

Теперь фича доступна в ветке `dev` на GitHub.

---

## 🧪 Проверка фичи

- Протестируй новую функцию локально.
- Убедись, что всё работает корректно, нет ошибок и бот не падает.
- После теста можно переходить к релизу.

---

## 🔀 Релиз (слияние с main)

```bash
git checkout main
git pull origin main
git merge dev
git push origin main
```

---

## 🏗️ Обновление продакшена (на сервере)

```bash
ssh eolv1n@vm4349106
cd ~/spotify_bot
git pull origin main
sudo systemctl restart spotify_bot
sudo systemctl status spotify_bot -l
```

---

## 🧹 Если что-то пошло не так

Посмотреть ошибки:
```bash
sudo tail -n 50 /var/log/spotify_bot_error.log
```

Откатиться на предыдущий коммит:
```bash
git log --oneline
git checkout <commit_id>
sudo systemctl restart spotify_bot
```

---

## 💡 Удобные алиасы для быстрого деплоя

Добавь в `~/.bashrc`:
```bash
alias bot-pull="cd ~/spotify_bot && git pull origin main && sudo systemctl restart spotify_bot"
alias bot-log="sudo tail -n 40 /var/log/spotify_bot.log"
```

Теперь деплой можно сделать одной командой:
```bash
bot-pull
```

---

## 🧾 Кратко

| Этап | Команда | Где |
|------|----------|-----|
| Разработка | `git checkout dev` | локально |
| Тест | `python3 bot.py` | локально |
| Пуш в dev | `git push origin dev` | локально |
| Мерж в main | `git merge dev && git push origin main` | локально |
| Деплой | `git pull origin main && systemctl restart spotify_bot` | сервер |

---
