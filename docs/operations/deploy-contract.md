# Production deploy contract

## Назначение

Этот контракт определяет минимальный воспроизводимый deploy `spotify_bot` на
VPS `baloonz`. Изменение считается доставленным только после runtime smoke, а
не по факту успешной сборки или состояния `Running` у контейнера.

## Source и artifact

- Каноничная ветка: `origin/main`.
- Deploy обновляет checkout только через `git pull --ff-only origin main`.
- Собранный image получает immutable локальный tag по короткому Git SHA:
  `spotify_bot:<sha>`; `spotify_bot:latest` остаётся Compose runtime tag.
- Предыдущий `latest` сохраняется как `spotify_bot:prev` до recreate и
  используется только для bounded rollback bot-контейнера.

## Runtime paths

| Назначение | Каноничный путь |
| --- | --- |
| Checkout | `/opt/spotify_bot` |
| Secrets/env | `/opt/spotify_bot_runtime/bot.env` |
| SQLite cache | `/opt/spotify_bot_runtime/cache` |
| WireGuard config | `/opt/spotify_bot_runtime/wireguard/wg_confs/wg0.conf` |

`bot.env` и `wg0.conf` имеют mode `0600` и не входят в Git. Production bot
использует `network_mode: service:wireguard`; host firewall, Docker daemon и
соседние Amnezia containers не входят в deploy scope.

## Entry point

GitHub Actions и ручной оператор используют один entrypoint:

```bash
cd /opt/spotify_bot
export BOT_ENV_FILE=/opt/spotify_bot_runtime/bot.env
export BOT_CACHE_DIR=/opt/spotify_bot_runtime/cache
export WG_CONFIG_DIR=/opt/spotify_bot_runtime/wireguard
./deploy.sh
```

Deploy выполняет fetch/fast-forward, build, SHA-tag, recreate `wireguard` и
`spotify_bot`, затем вызывает `scripts/prod_smoke.sh`.

## Success и smoke

Deploy успешен, только если одновременно подтверждены:

- оба контейнера `Running`, WireGuard health равен `healthy`;
- в log бота появился startup/polling marker;
- Telegram `getMe` возвращает `ok=true`;
- Spotify client-credentials exchange возвращает access token;
- `https://music.yandex.ru` доступен из network namespace бота;
- cache database открывается read-only и проходит `PRAGMA quick_check`;
- после внешних probes WireGuard имеет завершённый handshake.

Smoke не отправляет сообщения пользователям и не выводит secret values.

## Failure и rollback boundary

Если recreate или smoke не прошли, deploy:

1. сохраняет bounded logs обоих containers;
2. возвращает только `spotify_bot:latest` к `spotify_bot:prev`;
3. пересоздаёт bot-контейнер без изменения WireGuard config;
4. повторяет production smoke;
5. в любом случае завершает новый deploy ошибкой.

Rollback не меняет host firewall, Docker daemon, runtime secrets, cache,
WireGuard config или соседние containers. Если failure относится к этим
границам, требуется отдельная диагностика вместо расширения автоматического
rollback.
