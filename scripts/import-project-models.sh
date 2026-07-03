#!/usr/bin/env bash
# Импорт GGUF из models/llm/ в Ollama (host или контейнер ollama-docker)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLM_DIR="${ROOT}/models/llm"
USE_DOCKER="${USE_DOCKER:-0}"

if [[ ! -d "$LLM_DIR" ]]; then
  echo "Нет каталога $LLM_DIR"
  exit 1
fi

mapfile -t GGUF_FILES < <(find "$LLM_DIR" -maxdepth 1 -name '*.gguf' -type f 2>/dev/null | sort)

if [[ ${#GGUF_FILES[@]} -eq 0 ]]; then
  echo "В models/llm/ нет .gguf файлов."
  echo "Скачай модель в models/llm/ или используй: ollama pull <model>"
  exit 0
fi

run_ollama() {
  if [[ "$USE_DOCKER" == "1" ]]; then
    docker compose --profile ollama-docker exec -T ollama ollama "$@"
  else
    ollama "$@"
  fi
}

echo "Найдено GGUF: ${#GGUF_FILES[@]}"
echo ""

for gguf in "${GGUF_FILES[@]}"; do
  base="$(basename "$gguf" .gguf)"
  # имя модели: локальный тег без спецсимволов
  model_name="project-${base,,}"
  model_name="${model_name//[^a-z0-9._-]/-}"
  model_name="${model_name:0:64}"

  if [[ "$USE_DOCKER" == "1" ]]; then
    # в контейнере ollama volume: ./models:/models
    container_path="/models/llm/$(basename "$gguf")"
    modelfile="FROM ${container_path}"
  else
    modelfile="FROM ${gguf}"
  fi

  echo "→ ollama create ${model_name}"
  echo "  ${modelfile}"
  tmp="$(mktemp)"
  echo "$modelfile" >"$tmp"
  if [[ "$USE_DOCKER" == "1" ]]; then
    docker compose --profile ollama-docker cp "$tmp" ollama:/tmp/Modelfile.project
    run_ollama create "$model_name" -f /tmp/Modelfile.project
  else
    run_ollama create "$model_name" -f "$tmp"
  fi
  rm -f "$tmp"
  echo "  ✓ создана: ${model_name}"
  echo "    В .env: OLLAMA_LLM_MODEL=${model_name}"
  echo ""
done

echo "Текущие модели Ollama:"
run_ollama list
