#!/usr/bin/env bash
#########################################
# GitHub CI/CD 用的
# ops/deploy_container.sh
#########################################
set -euo pipefail

IMAGE="$1"
CONTAINER_NAME="$2"
GHCR_SECRET_ARN="$3"
GHCR_USERNAME="$4"
APP_ENV="${5:-prod}"                # 可選：預設 prod
AWS_SECRETS_ID="${6:-}"             # 可選：不傳則空
PORT="${PORT:-8080}"                # 可覆蓋：預設 8080
HEALTH_PATH="${HEALTH_PATH:-/healthz}"  # 可覆蓋：預設 /healthz
DATA_DIR_HOST="${DATA_DIR_HOST:-/opt/rag-qa-bot/data}"  # 掛載用

echo "🚀 Deploying $IMAGE as $CONTAINER_NAME"

# 1) GHCR 登入（不回印 PAT）
GHCR_PAT=$(aws secretsmanager get-secret-value --secret-id "$GHCR_SECRET_ARN" --query 'SecretString' --output text)
echo "$GHCR_PAT" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin > /dev/null 2>&1

# 2) 先拉映像
echo "📥 Pull image..."
docker pull "$IMAGE"

# 3) 備份舊容器（若存在）並釋放連接埠
OLD="${CONTAINER_NAME}_backup_$(date +%s)"
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "💾 Backup current container -> $OLD"
  docker rename "$CONTAINER_NAME" "$OLD" || true
  echo "🛑 Stop backup to free port"
  docker stop "$OLD" || true               # ← 關鍵：避免 8080 佔用
fi

# 4) 跑新容器（正確映射 8080:8080，注入 env，掛載資料夾）
echo "🏃 Run new container..."
mkdir -p "$DATA_DIR_HOST" || true
# ⚠️ 建議在機器上 chown 10001:10001 /opt/rag-qa-bot/data 以符合容器內 appuser
if ! docker run -d --name "$CONTAINER_NAME" \
  --restart always \
  -p "${PORT}:${PORT}" \
  -v "${DATA_DIR_HOST}:/data" \
  -e "PORT=${PORT}" \
  -e "APP_ENV=${APP_ENV}" \
  $( [ -n "$AWS_SECRETS_ID" ] && echo -e "-e AWS_SECRETS_ID=${AWS_SECRETS_ID}" ) \
  "$IMAGE"
then
  echo "❌ Failed to start new container"
  # 回復舊容器
  if docker ps -a --format '{{.Names}}' | grep -qx "$OLD"; then
    echo "🔄 Restoring backup"
    docker rename "$OLD" "$CONTAINER_NAME" || true
    docker start "$CONTAINER_NAME" || true
  fi
  exit 1
fi

# 5) 健康檢查 & 失敗回滾（與 Dockerfile 預設 /healthz 一致）
echo "⏳ Health check..."
for i in {1..30}; do
  if curl -sf "http://127.0.0.1:${PORT}${HEALTH_PATH}" >/dev/null; then
    echo "✅ Healthy"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "❌ Health check failed; logs:"
    docker logs "$CONTAINER_NAME" --tail 200 || true
    docker rm -f "$CONTAINER_NAME" || true
    if docker ps -a --format '{{.Names}}' | grep -qx "$OLD"; then
      docker rename "$OLD" "$CONTAINER_NAME" || true
      docker start "$CONTAINER_NAME" || true
      echo "🔄 Rolled back"
    fi
    exit 1
  fi
  sleep 2
done

# 6) 清理備份與舊 image
if docker ps -a --format '{{.Names}}' | grep -qx "$OLD"; then
  echo "🗑️ Remove backup $OLD"
  docker rm -f "$OLD" || true
fi

echo "🧹 Prune images"
docker image prune -f || true

echo "✅ Deployment successful!"
