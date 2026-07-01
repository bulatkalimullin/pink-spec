.PHONY: up up-ollama-docker down build logs dev install install-backend install-frontend clean open help setup-mirrors ollama-pull ollama-list

# ─── Env + зеркала ─────────────────────────────────────────────────────────────
-include mirrors.env
ifneq (,$(wildcard ./.env))
    include .env
    export
endif
DOCKER_MIRROR   ?= dockerhub.timeweb.cloud
PYPI_MIRROR     ?= https://pypi.tuna.tsinghua.edu.cn/simple
PYPI_MIRROR_FALLBACK ?= https://mirrors.aliyun.com/pypi/simple
NPM_REGISTRY    ?= https://registry.npmmirror.com
NPM_REGISTRY_FALLBACK ?= https://mirrors.aliyun.com/npm/

export DOCKER_MIRROR PYPI_MIRROR PYPI_MIRROR_FALLBACK NPM_REGISTRY NPM_REGISTRY_FALLBACK

# ─── Ollama models ────────────────────────────────────────────────────────────

## Скачать LLM + embedding модели в контейнер Ollama
ollama-pull:
	@if docker compose ps ollama 2>/dev/null | grep -q running; then \
		docker compose exec ollama ollama pull $${OLLAMA_LLM_MODEL:-qwen2.5:7b}; \
		docker compose exec ollama ollama pull $${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}; \
		for m in $$(echo "$${OLLAMA_LLM_FALLBACKS}" | tr ',' ' '); do \
			[ -n "$$m" ] && docker compose exec ollama ollama pull "$$m" || true; \
		done; \
	else \
		echo "Ollama на хосте — pull локально:"; \
		ollama pull $${OLLAMA_LLM_MODEL:-qwen2.5:7b}; \
		ollama pull $${OLLAMA_EMBEDDING_MODEL:-nomic-embed-text}; \
	fi

ollama-list:
	docker compose exec ollama ollama list

# ─── Docker ───────────────────────────────────────────────────────────────────

## Собрать и запустить (Ollama на хосте — default)
up:
	@test -f .env || (echo "Создай .env: cp .env.example .env" && exit 1)
	docker compose up --build -d
	@echo ""
	@echo "  Frontend: http://localhost:$${FRONTEND_PORT:-3000}"
	@echo "  Backend:  http://localhost:$${BACKEND_PORT:-8000}"
	@echo "  Ollama:   host :$${OLLAMA_PORT:-11434} (OLLAMA_BASE_URL=host.docker.internal)"

## Ollama в Docker (отдельный volume, модели через ollama pull внутри контейнера)
up-ollama-docker:
	@test -f .env || (echo "Создай .env: cp .env.example .env" && exit 1)
	OLLAMA_BASE_URL=http://ollama:11434 docker compose --profile ollama-docker up --build -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-frontend:
	docker compose logs -f frontend

status:
	docker compose ps

restart-backend:
	docker compose restart backend

## (Опционально) Глобальное зеркало Docker Hub в daemon.json — нужен sudo
setup-mirrors:
	sudo bash scripts/setup-mirrors.sh

# ─── Локальный запуск ─────────────────────────────────────────────────────────

install-backend:
	cd backend && uv venv .venv --python /usr/bin/python3.13
	cd backend && . .venv/bin/activate && \
		uv pip install -e ".[dev]" --index-url $(PYPI_MIRROR) && \
		uv pip install pynvml --index-url $(PYPI_MIRROR) || true

install-frontend:
	cd frontend && npm install --legacy-peer-deps --registry $(NPM_REGISTRY)

install: install-backend install-frontend

dev:
	@trap 'kill 0' SIGINT; \
		(cd backend && . .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | sed "s/^/[backend] /") & \
		(cd frontend && npm run dev 2>&1 | sed "s/^/[frontend] /") & \
		wait

clean:
	docker compose down -v --remove-orphans
	rm -rf backend/.venv backend/__pycache__
	rm -rf frontend/node_modules frontend/dist
	rm -rf output/ data/

open:
	xdg-open http://localhost:3000

help:
	@echo ""
	@echo "Pink Spec Agent"
	@echo ""
	@echo "  make up              — Docker: сборка + запуск (Ollama на хосте)"
	@echo "  make up-ollama-docker — Ollama в отдельном контейнере"
	@echo "  bash scripts/check-ollama-docker.sh — проверка доступа к Ollama"
	@echo "  make ollama-pull     — скачать модели в Ollama"
	@echo "  make ollama-list     — список моделей Ollama"
	@echo "  make setup-mirrors   — (опционально) sudo: Timeweb в daemon.json"
	@echo "  make logs / down     — логи / остановка"
	@echo ""
	@echo "  make install && make dev  — локально без Docker (нужен Ollama на :11434)"
	@echo ""
	@echo "Зеркала (mirrors.env):"
	@echo "  Docker Hub : $(DOCKER_MIRROR)"
	@echo "  PyPI       : $(PYPI_MIRROR)"
	@echo "  npm        : $(NPM_REGISTRY)"
	@echo ""
