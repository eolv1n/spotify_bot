# Spotify Bot: правила работы агента

## Внешний проектный контекст

У проекта есть Obsidian vault. Перед планированием или продолжением задач
сверяться с каноничной project note:

- `/home/eolv/obsidian/projects/spotify-bot/spotify-bot.md`

Для текущего фокуса и результатов дня дополнительно проверять:

- `/home/eolv/obsidian/daily/YYYY-MM-DD.md`

Репозиторий остаётся источником истины для кода, тестов и технической
документации. Obsidian хранит межсессионный статус, приоритеты, решения и
операционный контекст. При расхождении не закрывать и не переписывать задачи
автоматически: сначала определить, устарела заметка или реализация.

Не переносить в Git секреты и runtime-данные из Obsidian. После значимой работы
обновлять project note и оставлять в daily только краткий результат и evidence.

## Текущий runtime boundary

- Каноничный dev workspace: `/home/eolv/projects/spotify_bot` на `eolv`.
- Production checkout: `/opt/spotify_bot` на `baloonz`.
- Базовый `docker-compose.yml` — production-контур с WireGuard; не запускать
  его локально как обычную dev-команду.
- Локальная разработка использует `deploy/docker-compose.dev.yml` без
  WireGuard и production runtime.
- Не менять production `baloonz` до зелёных локальных проверок и CI.
