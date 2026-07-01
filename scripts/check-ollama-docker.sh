#!/usr/bin/env bash
# Проверка: backend в Docker может достучаться до Ollama на хосте
set -euo pipefail

URL="${1:-http://host.docker.internal:11435}"

echo "Проверка Ollama из контейнера backend → $URL"

if ! docker compose ps backend 2>/dev/null | grep -q running; then
  echo "⚠ backend не запущен — сначала: make up"
  exit 1
fi

if docker exec pink-spec-backend curl -sf --max-time 5 "${URL}/api/tags" >/dev/null; then
  echo "✓ Ollama доступен из Docker"
  docker exec pink-spec-backend curl -s "${URL}/api/tags" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for m in d.get('models', []):
    print('  -', m.get('name'))
"
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
echo "  docker compose restart backend"
echo "  bash scripts/check-ollama-docker.sh"
exit 1
