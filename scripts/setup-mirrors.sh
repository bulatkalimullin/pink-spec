#!/bin/bash
# Глобальное зеркало Docker Hub (Timeweb Cloud) — опционально, нужен sudo.
# Образы в Dockerfile уже тянутся через dockerhub.timeweb.cloud напрямую.
#
# sudo bash scripts/setup-mirrors.sh

set -euo pipefail

MIRROR="https://dockerhub.timeweb.cloud"
DAEMON_JSON="/etc/docker/daemon.json"

echo "→ Docker registry-mirror: ${MIRROR} (Timeweb Cloud)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Нужен sudo: sudo bash scripts/setup-mirrors.sh"
  exit 1
fi

if [ -f "$DAEMON_JSON" ] && command -v jq >/dev/null 2>&1; then
  tmp=$(mktemp)
  jq --arg m "$MIRROR" '
    .["registry-mirrors"] = ((.["registry-mirrors"] // []) + [$m] | unique)
  ' "$DAEMON_JSON" > "$tmp" && mv "$tmp" "$DAEMON_JSON"
else
  cat > "$DAEMON_JSON" << EOF
{
  "registry-mirrors": ["${MIRROR}"]
}
EOF
fi

systemctl restart docker
sleep 2
docker info 2>/dev/null | grep -A 3 "Registry Mirrors" || true
echo "Готово."
