# Чек-лист миграции production VPS

Этот чек-лист описывает перенос `spotify_bot` на новый VPS. Секреты, приватные
SSH/WireGuard-ключи и значения из `bot.env` нельзя сохранять в репозитории,
логах или evidence-файлах.

## 1. До окна работ

- [ ] Зафиксировать provider, IP, console access, billing и SSH alias нового VPS
      в закрытой проектной заметке.
- [ ] Проверить SSH по ключу в двух независимых сессиях и сохранить аварийный
      console access.
- [ ] Проверить ОС, Docker Engine, Docker Compose plugin, свободные RAM/disk,
      `/lib/modules`, `/dev/net/tun`, открытые порты и существующие Docker-сети.
- [ ] Убедиться, что имена `spotify_bot` и `spotify_bot_wg` не заняты, а Docker
      subnet не пересекается с host/VPN-сетями.
- [ ] Установить deploy public key и отдельно подтвердить, что именно GitHub
      Actions key разрешён на новом VPS.
- [ ] Создать runtime layout:

  ```bash
  sudo install -d -m 700 /opt/spotify_bot_runtime
  sudo install -d -m 700 /opt/spotify_bot_runtime/cache
  sudo install -d -m 700 /opt/spotify_bot_runtime/wireguard/wg_confs
  ```

- [ ] Передать `bot.env` и `wg0.conf` защищённым каналом и выставить `0600`.
- [ ] Снять зашифрованный backup старого runtime вне обоих VPS: `bot.env`,
      `wg0.conf`, cache DB и текущий Git SHA.
- [ ] Не менять GitHub deploy target и не отключать старый VPS до cutover.

### Safety gate для соседних сервисов

Если на target уже работают VPN/proxy-контейнеры:

- [ ] До staging сохранить evidence: `docker ps`, published ports, restart
      policies, `ip -br address`, `ip route`, Docker networks и memory usage.
- [ ] Не менять Docker daemon config, host firewall, sysctl, Amnezia/VPN
      configs, существующие Docker networks и restart policies.
- [ ] Не выполнять `docker compose down` вне `/opt/spotify_bot`, `docker
      system prune`, удаление чужих images/networks или общий restart Docker.
- [ ] Все Compose-команды выполнять из `/opt/spotify_bot` и адресовать только
      `wireguard`/`spotify_bot`.
- [ ] После каждого шага сравнивать status, ports и routes соседних сервисов с
      baseline. При расхождении остановить только bot stack и не продолжать
      cutover.

## 2. Staging на новом VPS

У Telegram polling с одним token не может быть двух активных production
экземпляров. Один и тот же WireGuard peer (`PrivateKey`/tunnel address) также
нельзя одновременно поднимать на двух VPS: gateway будет переносить endpoint
между хостами. Поэтому на staging-этапе старые bot и WG остаются единственными
production-инстансами.

- [ ] Клонировать текущий `main` в `/opt/spotify_bot`.
- [ ] Проверить итоговый Compose contract:

  ```bash
  cd /opt/spotify_bot
  export BOT_ENV_FILE=/opt/spotify_bot_runtime/bot.env
  export BOT_CACHE_DIR=/opt/spotify_bot_runtime/cache
  export WG_CONFIG_DIR=/opt/spotify_bot_runtime/wireguard
  docker compose config --quiet
  ```

- [ ] Собрать image без запуска production poller:

  ```bash
  docker compose build spotify_bot
  ```

- [ ] Если для нового VPS создан отдельный временный WG peer, поднять только
      `wireguard` и проверить handshake/egress. Если переносится прежний peer,
      WG-проверку отложить до cutover и не запускать sidecar параллельно.
- [ ] Убедиться, что существующие host-level VPN/Amnezia-контейнеры, их порты,
      маршруты и health не изменились.
- [ ] Проверить memory pressure/OOM events; bot staging не должен ухудшать
      доступность соседних сервисов.
- [ ] Проверить `stat`: `bot.env` и `wg0.conf` имеют mode `0600`.

## 3. Cutover

- [ ] Зафиксировать Git SHA и состояние старого stack.
- [ ] Остановить старые `spotify_bot` и `wireguard`, оставив runtime для
      быстрого rollback:

  ```bash
  cd /opt/spotify_bot
  docker compose stop spotify_bot wireguard
  ```

- [ ] Сделать финальный согласованный snapshot cache. Для SQLite использовать
      остановленный файл или SQLite backup, а не копирование во время записи.
- [ ] Сначала запустить новый WG, проверить handshake, DNS, Telegram API,
      Spotify API и `music.yandex.ru`, затем запустить новый poller:

  ```bash
  cd /opt/spotify_bot
  export BOT_ENV_FILE=/opt/spotify_bot_runtime/bot.env
  export BOT_CACHE_DIR=/opt/spotify_bot_runtime/cache
  export WG_CONFIG_DIR=/opt/spotify_bot_runtime/wireguard
  docker compose up -d wireguard
  # выполнить network smoke
  docker compose up -d spotify_bot
  ```

- [ ] Проверить отсутствие restart loop и Telegram polling conflict.
- [ ] Выполнить real smoke: обычная track link и inline query; проверить Spotify
      и Yandex из namespace бота.
- [ ] Только после ручного smoke переключить `SERVER_HOST`/SSH target GitHub
      Actions и выполнить один контролируемый deploy из `main`.

## 4. Rollback

Если новый poller или его egress не работает:

1. Остановить `spotify_bot` и `wireguard` на новом VPS.
2. Запустить прежние `wireguard` и `spotify_bot` на старом VPS.
3. Вернуть прежний GitHub deploy target.
4. Проверить Telegram smoke на старом VPS.

Не удалять новый или старый runtime при rollback. Автоматический rollback
`deploy.sh` откатывает только bot image и не восстанавливает WG/runtime/network.

## 5. Acceptance и decommission

- [ ] GitHub Actions deploy на новый VPS успешен.
- [ ] `spotify_bot_wg` healthy, handshake свежий, `spotify_bot` стабильно работает.
- [ ] Telegram polling/inline, Spotify и Yandex smoke проходят.
- [ ] Host-level VPN/Amnezia-сервисы не деградировали.
- [ ] Секреты не попали в Git, image layers, Actions logs или документацию.
- [ ] После окна наблюдения старый stack остановлен, backup сохранён на
      согласованный срок, старый VPS отменён.
