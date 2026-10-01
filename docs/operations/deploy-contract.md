# Production deploy contract

## Назначение и source

Код и deploy-конфигурация находятся в `eolv1n/spotify_bot`, ветка `main`.
Production checkout — `/opt/spotify_bot` на EU `baloonz`.
`deploy.sh` выполняет fast-forward, build, SHA-tag, recreate только бота и
bounded smoke. Предыдущий image сохраняется как `spotify_bot:prev`.
CI запускается на push и PR; production deploy запускается явно через
`workflow_dispatch` с `deploy=true` после открытия временного SSH-окна.

## Runtime и маршруты

- Env: `/opt/spotify_bot_runtime/bot.env`, mode `0600`.
- Cache: `/opt/spotify_bot_runtime/cache`.
- Telegram, Spotify и остальные HTTP-клиенты используют прямой EU egress.
- Только клиент `yandex-music` получает `YANDEX_PROXY_URL` и timeout 15 секунд.
  Это покрывает init, поиск, lookup и refinement.
- Production: `YANDEX_PROXY_URL=http://10.243.93.1:21081`.
- RU proxy слушает только приватный GRE-адрес. UFW разрешает вход на
  `bzgre0` только от `10.243.93.2`. Для proxy используется уже установленный
  проверенный `/opt/baloonz-gost/gost`; client-side зависимости не добавляются.
- При отказе proxy Яндекс сообщает об ошибке; автоматического обхода через
  EU или домашний WireGuard нет.
- `spotify_bot_wg` остановлен; config и контейнер сохраняются для ручного
  восстановления. Default Compose и deploy больше не поднимают его.

## RU proxy

Source unit: `deploy/ru-proxy/spotify-yandex-proxy.service`.
Перед установкой проверить working GRE, GOST artifact и отсутствие другого
listener на `10.243.93.1:21081`. Сохранить исходные unit/UFW state в root-only
backup. Установить unit в `/etc/systemd/system/`, проверить
`systemd-analyze verify`, добавить точное правило:

```bash
ufw allow in on bzgre0 from 10.243.93.2 to 10.243.93.1 port 21081 proto tcp comment 'spotify-yandex-proxy'
systemctl daemon-reload
systemctl enable --now spotify-yandex-proxy.service
```

Проверить actual API search и track lookup с EU через proxy и российский
egress. Откат proxy: остановить/disable новую службу, удалить только её
UFW rule, восстановить прежний unit при его наличии и daemon-reload.
Основные службы GOST/GRE и клиентского каскада не перезапускать.

## Deploy и smoke

```bash
cd /opt/spotify_bot
export BOT_ENV_FILE=/opt/spotify_bot_runtime/bot.env
export BOT_CACHE_DIR=/opt/spotify_bot_runtime/cache
./deploy.sh
```

Smoke требует running bot, polling marker с текущего запуска, Telegram
`getMe`, Spotify token exchange, реальный поиск и получение трека через
RU Yandex proxy, read-only SQLite `quick_check`. Секреты не выводятся.

## Первый cutover и rollback

До первого selective deploy отдельно сохранить предыдущий Compose,
image tag и env в root-only backup. При неуспехе первого переключения
вернуть прежний env/Compose/image и пересоздать WG и bot в старом режиме.
Обычный image rollback не откатывает сетевую архитектуру.

После принятия selective режима deploy rollback возвращает только image и
повторяет smoke. Он не меняет UFW, Docker daemon, env, cache или соседние
контейнеры. Для ручного возврата full-tunnel используется дополнительный
`deploy/docker-compose.wireguard.yml` вместе с default Compose, явно заданным
`PROD_WG_CONFIG_DIR` и `--project-directory /opt/spotify_bot`.
При этом `YANDEX_PROXY_URL` нужно убрать из runtime env: иначе Яндекс продолжит
использовать недоступный GRE proxy. WG bootstrap hook сохраняется.

## Временное SSH-окно GitHub Actions

Управление идёт с рабочего устройства: RU напрямую, EU через RU ProxyJump.
До открытия окна проверить host, UFW baseline и наличие Actions `SSH_KEY`,
соответствующего публичному root deploy key на EU. Сначала поставить systemd
rollback timer на 20 минут, затем открыть временный IPv4 TCP/22. Запустить
CI вручную с `deploy=true`; по завершении убрать только временное правило,
отменить timer и независимо проверить UFW, deployed SHA и smoke.
Постоянный публичный SSH и новый management relay не нужны.

Операторская команда: `./scripts/actions_deploy.sh`. Она проверяет наличие
secret, ставит rollback timer до открытия TCP/22, запускает только явный
workflow dispatch, ждёт результат, закрывает окно и повторяет smoke по SSH.
Если управление оборвётся, transient timer закроет окно через 20 минут при
работающем host. Во время окна host не перезагружать: transient timer не
переживает reboot. Обслуживание и reboot выполняются после закрытия окна.
