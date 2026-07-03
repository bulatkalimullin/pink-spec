#!/usr/bin/env bash
# Проверка: agent-worker в Docker может достучаться до Ollama на хосте
set -euo pipefail

URL="${1:-http://host.docker.internal:11435}"
CONTAINER="${2:-pink-spec-agent-worker}"

echo "Проверка Ollama из контейнера ${CONTAINER} → $URL"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "⚠ ${CONTAINER} не запущен — сначала: make up"
  exit 1
fi

if docker exec "${CONTAINER}" curl -sf --max-time 5 "${URL}/api/tags" >/dev/null; then
  echo "✓ Ollama доступен из Docker"
  docker exec "${CONTAINER}" curl -s "${URL}/api/tags" | python3 -c "
import sys, json
d = json.load(sys.stdin)
models = d.get('models', [])
print(f'  Моделей в Ollama: {len(models)}')
for m in models:
    print('  -', m.get('name'))
"
  echo ""
  echo "Папка models/llm/*.gguf НЕ подхватывается автоматически."
  echo "Импорт: make import-models"
  exit 0
fi

echo "✗ Ollama НЕ доступен из Docker"
echo ""
echo "Причина: Ollama (snap) слушает только 127.0.0.1:11434"
echo ""
echo "Исправление (один раз, нужен sudo):"
echo "  sudo snap set ollama host=0.0.0.0:11434"
echo "  sudo snap restart ollama"
echo ""
echo "Затем:"
echo "  docker compose restart agent-worker backend"
echo "  bash scripts/check-ollama-docker.sh"
exit 1
