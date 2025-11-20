#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$HOME/spotify_bot"
IMAGE_NAME="spotify_bot"
CONTAINER_NAME="spotify_bot"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

echo "🚀 Deploy Spotify Bot"
log "Repo dir: ${REPO_DIR}"
echo "---------------------------------------------"

cd "$REPO_DIR" || { echo "❌ Cannot cd to $REPO_DIR"; exit 1; }

# 1. Health-check сервера (опциональный, но полезный)
if [[ -x "./server_check.sh" ]]; then
  log "Running server_check.sh..."
  ./server_check.sh
  log "server_check.sh completed successfully"
else
  log "server_check.sh not found or not executable — skipping"
fi

echo "---------------------------------------------"
log "Updating code from git (origin/main)..."
git pull --ff-only origin main
VERSION="$(git rev-parse --short HEAD)"
log "Current git SHA: ${VERSION}"

echo "---------------------------------------------"
# 2. Подготовка rollback: сохраняем прошлый образ
if docker image inspect "${IMAGE_NAME}:latest" &>/dev/null; then
  log "Tagging existing image ${IMAGE_NAME}:latest as ${IMAGE_NAME}:prev (for rollback)"
  docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:prev"
else
  log "No existing ${IMAGE_NAME}:latest image — first deploy, rollback won't be available"
fi

# 3. Сборка нового образа
log "Building new Docker image ${IMAGE_NAME}:${VERSION}..."
docker build \
  -t "${IMAGE_NAME}:${VERSION}" \
  -t "${IMAGE_NAME}:latest" \
  .

log "Image build completed."
echo "---------------------------------------------"

# 4. Останавливаем и удаляем старый контейнер
if docker ps -q -f "name=^${CONTAINER_NAME}$" >/dev/null; then
  log "Stopping running container ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}"
fi

if docker ps -aq -f "name=^${CONTAINER_NAME}$" >/dev/null; then
  log "Removing old container ${CONTAINER_NAME}..."
  docker rm -f "${CONTAINER_NAME}"
fi

echo "---------------------------------------------"
# 5. Стартуем новый контейнер с лимитами ресурсов
log "Starting new container ${CONTAINER_NAME}..."
set +e
docker run -d \
  --name "${CONTAINER_NAME}" \
  --env-file .env \
  --restart unless-stopped \
  --memory=300m \
  --cpus=0.5 \
  "${IMAGE_NAME}:latest"
run_rc=$?
set -e

if [[ "$run_rc" -ne 0 ]]; then
  log "❌ docker run failed with exit code ${run_rc}"
  docker logs --tail=50 "${CONTAINER_NAME}" || true

  # Пытаемся откатиться на предыдущий образ
  if docker image inspect "${IMAGE_NAME}:prev" &>/dev/null; then
    log "Attempting rollback to image ${IMAGE_NAME}:prev..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --env-file .env \
      --restart unless-stopped \
      --memory=300m \
      --cpus=0.5 \
      "${IMAGE_NAME}:prev" || true
    log "Rollback container started (check manually)."
  else
    log "⚠️ No ${IMAGE_NAME}:prev image found — rollback not possible."
  fi

  exit 1
fi

# 6. Быстрый smoke-чек контейнера
sleep 5
STATE="$(docker inspect -f '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "unknown")"
if [[ "$STATE" != "running" ]]; then
  log "❌ Container is not running (state=${STATE})"
  docker logs --tail=50 "${CONTAINER_NAME}" || true

  if docker image inspect "${IMAGE_NAME}:prev" &>/dev/null; then
    log "Attempting rollback to ${IMAGE_NAME}:prev..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --env-file .env \
      --restart unless-stopped \
      --memory=300m \
      --cpus=0.5 \
      "${IMAGE_NAME}:prev" || true
    log "Rollback container started (check manually)."
  else
    log "⚠️ No ${IMAGE_NAME}:prev image found — rollback not possible."
  fi

  exit 1
fi

echo "---------------------------------------------"
log "Container ${CONTAINER_NAME} is running."
log "Last 20 lines of logs:"
docker logs --tail=20 "${CONTAINER_NAME}" || true

log "✅ Deploy finished successfully."
