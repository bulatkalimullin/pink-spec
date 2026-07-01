# Модели Ollama

Все LLM и embeddings загружаются через **Ollama** — отдельный сервис на хосте или в Docker.

## Установка Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# или Docker
docker run -d --gpus all -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
```

## LLM

```bash
ollama pull qwen2.5:7b        # основная (аналог твоего Qwen GGUF)
ollama pull llama3.2          # fallback
ollama pull mistral           # fallback
```

### Свой GGUF (уже скачан в `models/llm/`)

```bash
cat > /tmp/Modelfile <<'EOF'
FROM /models/llm/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
EOF
docker compose exec ollama ollama create qwen-custom -f /tmp/Modelfile
```

В `.env`: `OLLAMA_LLM_MODEL=qwen-custom`

Проверка:

```bash
ollama list
curl http://localhost:11434/api/tags
```

## Embeddings

```bash
ollama pull nomic-embed-text      # default, 768 dim
ollama pull mxbai-embed-large     # выше качество, больше RAM
```

## Docker + Ollama на хосте (snap)

Backend в Docker обращается к `host.docker.internal:11435` через **ollama-proxy**
(snap-Ollama на `127.0.0.1:11434` из контейнера не виден).

Прокси поднимается автоматически: `docker compose up`.

Альтернатива без прокси (нужен sudo):

```bash
sudo snap set ollama host=0.0.0.0:11434
sudo snap restart ollama
# тогда OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Конфигурация в `.env`

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_LLM_FALLBACKS=mistral,qwen2.5:7b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

В Docker backend обращается к хосту:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

или к сервису `ollama` в `docker-compose.yml`:

```env
OLLAMA_BASE_URL=http://ollama:11434
```

## Перезапуск

После `ollama pull` перезапуск Pink Spec не нужен — модели подхватываются по запросу.

```bash
docker compose up -d backend
```
