# Pink Spec Agent

Локальный мультиагентный ассистент: идея → полная спецификация проекта.

## Быстрый старт (Docker, одна команда)

```bash
# 1. Установи Ollama и скачай модели (см. models/README.md)
ollama pull llama3.2
ollama pull nomic-embed-text

# 2. Запуск
cp .env.example .env
make up
```

Открой [`http://localhost:3000`](http://localhost:3000)

## Зеркала (работают из РФ)

Все зеркала в `mirrors.env` — единый источник для Docker, make и compose.

| Что | Зеркало | Fallback |
|-----|---------|----------|
| **Docker Hub** | `dockerhub.timeweb.cloud` (Timeweb, RU) | — |
| **PyPI** | `pypi.tuna.tsinghua.edu.cn` (Tsinghua) | Aliyun |
| **npm** | `registry.npmmirror.com` | Aliyun npm |
| **PyTorch CUDA** | `download.pytorch.org` | зеркала cu124 нет |

Проверено с российского IP. PyTorch CUDA wheels — только с официального индекса.

Опционально — глобальное зеркало Docker в daemon.json:

```bash
make setup-mirrors   # sudo, Timeweb
```

## Команды

```bash
make up              # собрать и запустить
make logs            # логи
make down            # остановить
make status          # статус
make clean           # удалить контейнеры + volumes
make help            # справка
```

## Локально (без Docker)

```bash
make install
make dev
```

## Требования

- Docker + Docker Compose
- **Ollama** на хосте (`http://localhost:11434`) или в compose
- Модели: `llama3.2` (LLM), `nomic-embed-text` (embeddings)

Спецификация: [`docs/SPEC_AGENT.md`](docs/SPEC_AGENT.md)
