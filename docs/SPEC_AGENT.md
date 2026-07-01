# Pink Spec Agent — полная спецификация

> Версия: 1.1 | Дата: 2026-07-01 | Статус: Source of Truth

## Оглавление

1. [Видение продукта](#1-видение-продукта)
2. [Уровни спецификации (L1–L4)](#2-уровни-спецификации)
3. [Мультиагентная система — роли](#3-мультиагентная-система)
4. [Context Manager — суммаризация](#4-context-manager)
5. [Embedding Saturation](#5-embedding-saturation)
6. [Папка tasks/ — микро-задачи](#6-папка-tasks)
7. [Стек и деплой](#7-стек-и-деплой)
8. [JSON-конфиг правил](#8-json-конфиг-правил)
9. [LangGraph — оркестрация](#9-langgraph-оркестрация)
10. [Ollama интеграция](#10-ollama-интеграция)
11. [API и WebSocket](#11-api-и-websocket)
12. [UI спецификация (Mission Control)](#12-ui-спецификация)
13. [Выходные артефакты](#13-выходные-артефакты)
14. [Структура репозитория](#14-структура-репозитория)
15. [Fallback-стратегии](#15-fallback-стратегии)
16. [Failure modes и Recovery](#16-failure-modes-и-recovery)
17. [Безопасность и ограничения](#17-безопасность-и-ограничения)

---

## 1. Видение продукта

**Pink Spec Agent** — локальный мультиагентный инженерный ассистент.

**Принимает:**
- Идею проекта (свободный текст)
- JSON-конфиг с правилами (`schema_version: "1.0"`)

**Генерирует:**
- Product spec, architecture spec, API/data model, UI spec, roadmap, риски, trade-offs
- Папку `tasks/` с микро-задачами для поэтапной реализации

**Ключевой принцип:** Supervisor контролирует глубину, агент документирует допущения, пользователь видит **каждый шаг** в Mission Control UI в реальном времени. Nothing Silent.

---

## 2. Уровни спецификации

| Level | ID | Время | Артефакты | Tasks | Review |
|-------|-----|-------|-----------|-------|--------|
| **Brief** | `L1` | 2–5 мин | `product_outline`, `architecture_sketch` | нет | 0 |
| **Standard** | `L2` | 10–15 мин | L1 + `product_spec`, `architecture_spec`, `roadmap` | 15–30 задач | 1x |
| **Full** | `L3` | 20–30 мин | все + OpenAPI + UI spec + risk register | 50–100 задач | 2–3x |
| **Exhaustive** | `L4` | без лимита* | L3 + ADR deep-dive, NFR matrix, test strategy, ops runbook | 100+, итеративно | до approve |

\* **L4 — «до талого»:** нет фиксированного бюджета. Safety hard cap: default 2 ч (configurable). Supervisor работает пока `completion_criteria` не выполнены все.

### L4 completion criteria

| Критерий | Условие |
|----------|---------|
| `artifacts_complete` | Все L4-артефакты существуют и non-empty |
| `reviewer_approved` | Reviewer pass + confidence ≥ 0.85 |
| `no_critical_gaps` | Нет open questions priority=critical |
| `tasks_coverage` | Coverage map ≥ 95% spec sections |
| `cross_artifact_consistent` | 0 critical contradictions |
| `saturation_done` | Saturation complete или fallback с ASSUMPTION |
| `rules_compliant` | Все critical/high agent_rules проверены |

### Минимальные требования L4 (`.env`)

| Параметр | Рекомендация | Почему |
|----------|--------------|--------|
| `LLM_MAX_TOKENS` | ≥ 8192 | JSON batches (25 tasks) и exhaustive specs обрезаются при 2048 |
| `OLLAMA_TIMEOUT_SEC` | ≥ 300 | Длинная генерация на локальной модели |
| `OLLAMA_LLM_MODEL` | 7B+ (напр. `qwen2.5:7b`) | `gemma3:4b` часто даёт `completed_partial` |

При `completed_partial` смотри `output/{session_id}/gaps.md` (секция **Unmet L4 Criteria**) и событие `session_completed_partial` в Activity.

### Time budget по уровням

| Level | `max_duration_sec` | При превышении |
|-------|-------------------|----------------|
| L1 | 300 | Graceful degradation → partial export |
| L2 | 900 | Skip optional agents |
| L3 | 1800 | Сократить review |
| L4 | null | Safety cap 7200 (2 ч) |

**Anti-loop guard:** один агент >5 раз подряд без прогресса → fallback / escalate / force finalize с `gaps.md`.

---

## 3. Мультиагентная система

Реализация: LangGraph Supervisor pattern. Каждый агент — subgraph с собственным system prompt и output schema.

### Роли агентов

| Агент | Роль | Выход |
|-------|------|-------|
| **Supervisor** | Маршрутизация, quality gates, time budget / completion criteria, retry, fallbacks | `next_agent`, `directives`, `status_report` |
| **Product Analyst** | Personas, use cases, user stories, scope | `product_spec.md` |
| **Architect** | C4, ADR, deployment, security boundaries | `architecture_spec.md` |
| **API Designer** | REST/WS контракты, schemas | `api_spec.openapi.yaml`, `data_model.md` |
| **UI Designer** | Screens, flows, components | `ui_spec.md` |
| **Task Decomposer** | Декомпозиция roadmap → микро-задачи | `tasks/**/*.md`, `TASK_INDEX.md` |
| **Researcher** | RAG retrieval, domain research | `context_brief`, retrieved chunks |
| **Reviewer** | Consistency, NFR, rules compliance | `review_report`, pass/fail |
| **Context Manager** | Summarization, state compression, handoff | `session_summary`, `agent_handoff` |

### Supervisor — поведение

**L1–L3:** time budget → graceful degradation при 85% лимита.

**L4:** completion criteria → refinement loop до approve (bounded by safety cap).

**Directives** (передаются каждому агенту):
- `spec_level`, оставшийся time budget
- `relevant_summary` — сжатый контекст, НЕ raw history
- `rules_snapshot` — critical/high rules только
- `directives` — что делать / чего избегать / ссылка на предыдущий output

**Retry limits:** L1–L3 — max 2/agent; L4 — unlimited (bounded criteria + anti-loop).

### Routing by spec_level

| Step | L1 | L2 | L3 | L4 |
|------|----|----|----|----|
| Researcher + saturation | optional | yes | full | full + extended |
| Product Analyst | outline | full | full + extras | full + iterative refine |
| Architect | sketch | C4 L2 | C4 + ADR | C4 + ADR deep-dive |
| API Designer | skip | skip | full | full + refine |
| UI Designer | skip | skip | full | full + refine |
| Task Decomposer | skip | 15–30 | 50–100 | 100+ until coverage |
| Reviewer | skip | 1x | 2–3x | until approve |

**Parallelism (L3/L4):** API Designer + UI Designer параллельно после Architect; merge через Context Manager.

---

## 4. Context Manager

Управляет context window — предотвращает раздувание при длинных сессиях.

### Уровни суммаризации

| Уровень | Триггер | Размер |
|---------|---------|--------|
| Turn summary | После каждого агента | 200–400 tokens |
| Phase summary | После группы агентов | 500–800 tokens |
| Session summary | При 70% token budget / перед export | Полная картина |

### Rolling context window

```python
class ContextState(TypedDict):
    raw_messages: list[Message]    # последние N turns
    turn_summaries: list[str]      # все turn summaries
    phase_summary: str
    session_summary: str
    token_budget_used: int
    saturation_report: dict | None
```

**Правило:** агент получает `phase_summary` + `turn_summaries[-3:]` + artifact excerpts — не полный raw log.

**Summarization output format:** Decisions / Assumptions / Open items / Artifacts touched.

---

## 5. Embedding Saturation

Активируется при `rag.enabled: true`. Researcher + Context Manager выполняют saturation loop перед фазой Planning.

### Алгоритм

```
seed_queries(idea)
  → retrieve(top_k)
  → score_novelty(chunks)
  → if novelty > threshold: expand_queries → retrieve
  → else: merge_deduplicate → saturation_summary → context_brief
```

### Параметры

| Параметр | Default | Описание |
|----------|---------|----------|
| `max_iterations` | 5 | Макс. циклов retrieve |
| `top_k` | 8 | Chunks за итерацию |
| `novelty_threshold` | 0.15 | Min cosine distance к уже collected |
| `min_chunks` | 10 | Мин. chunks перед выходом (L3+) |
| `query_expansion` | true | LLM генерирует follow-up queries |

**Novelty score:** для нового chunk — min distance к collected set; avg novelty < threshold → saturation complete.

**Выход:** `saturation_report` + `context_brief` для Supervisor.

**Без embeddings:** full-text scan, saturation skipped, `saturation.status: "skipped"` в manifest.

---

## 6. Папка tasks/

Генерируется Task Decomposer (L2+). Каждая задача = атомарный шаг 15–60 мин работы.

### Структура вывода

```
output/{session_id}/
├── manifest.json
├── product_spec.md
├── architecture_spec.md
├── api_spec.openapi.yaml
├── ui_spec.md
├── data_model.md
├── roadmap.md
├── risk_register.md
├── gaps.md            # при partial export
└── tasks/
    ├── TASK_INDEX.md
    ├── phase-01-foundation/
    │   ├── 001-init-repo.md
    │   ├── 002-docker-compose.md
    │   └── 003-env-config.md
    ├── phase-02-backend/
    │   ├── 010-fastapi-scaffold.md
    │   └── 011-database-models.md
    └── phase-03-frontend/
        ├── 020-vite-setup.md
        └── 021-shadcn-init.md
```

### Формат файла задачи (NNN-slug.md)

```markdown
---
id: "010"
phase: "02-backend"
title: "Scaffold FastAPI application"
priority: high
estimated_minutes: 45
depends_on: ["001", "002"]
spec_refs: ["architecture_spec.md#api-layer", "api_spec.openapi.yaml"]
---

## Goal
One sentence — что должно работать после выполнения.

## Context
2–3 предложения связи с общим проектом.

## Steps
1. ...
2. ...

## Acceptance Criteria
- [ ] ...
- [ ] ...

## Notes / Pitfalls
- ...

## Verification
Как проверить (command, endpoint, manual check).
```

### TASK_INDEX.md — обязательные секции

- Mermaid dependency graph (`task010 --> task011`)
- Таблица: ID | Phase | Title | Depends | Est. | Status
- Critical path highlight
- Mapping tasks → spec sections

**По уровням:** L1: нет tasks. L2: 3–5 phases, 15–30 tasks. L3: 5–8 phases, 50–100 tasks. L4: 5–8 phases + итеративное дополнение до coverage ≥ 95%.

---

## 7. Стек и деплой

| Слой | Технология |
|------|------------|
| API / WS | FastAPI, `websockets`, SSE fallback |
| Orchestration | LangChain + LangGraph |
| LLM | Ollama (`/api/chat`, OpenAI-compatible `/v1`) |
| Embeddings | Ollama (`/api/embeddings`, модели `nomic-embed-text` и др.) |
| Vector store | ChromaDB (local `./data/vectors`) |
| UI | React + TypeScript + Vite + shadcn/ui + Tailwind CSS |
| Persistence | SQLite |
| Monitoring | `psutil` + optional `pynvml` |
| DevOps | Docker Compose + Ollama (host или контейнер) |

**Deployment:** `docker compose up`. Ollama — на хосте или сервис `ollama` в compose. Secrets и URL через `.env`.

### Ollama в Docker Compose (опционально)

```yaml
services:
  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: [ollama_data:/root/.ollama]
    # deploy.resources.reservations.devices — GPU при необходимости

  backend:
    environment:
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on: [ollama]
```

Модели подтягиваются один раз: `docker exec -it <ollama> ollama pull llama3.2`.

---

## 8. JSON-конфиг правил

Полная схема с defaults:

```json
{
  "schema_version": "1.0",
  "spec_level": "L2",
  "l4": {
    "safety_cap_sec": 7200,
    "completion_confidence": 0.85,
    "tasks_coverage_pct": 95
  },
  "project": {
    "name": "my-service",
    "domain": "fintech",
    "idea_summary": null
  },
  "constraints": {
    "stack": {
      "backend": ["python", "fastapi"],
      "frontend": ["react", "typescript"],
      "forbidden": []
    },
    "deployment": "local",
    "budget": "low",
    "timeline_weeks": 8
  },
  "nfr": {
    "latency_p95_ms": 500,
    "availability": "99.5%",
    "security": ["oauth2", "audit_log"]
  },
  "output": {
    "language": "ru",
    "format": "markdown",
    "include_diagrams": true
  },
  "agent_rules": [
    {
      "id": "no_overengineering",
      "priority": "high",
      "rule": "Предпочитай простые решения; не добавляй микросервисы без явной необходимости"
    },
    {
      "id": "ask_before_assume",
      "priority": "medium",
      "rule": "Если критичный параметр отсутствует — пометь как ASSUMPTION"
    }
  ],
  "ollama": {
    "base_url": "http://localhost:11434",
    "llm_model": "llama3.2",
    "fallback_models": ["mistral", "qwen2.5:7b"],
    "embedding_model": "nomic-embed-text",
    "embedding_fallback": "keyword",
    "temperature": 0.2,
    "max_tokens": 4096,
    "keep_alive": "5m",
    "timeout_sec": 120,
    "retry_on_error": 3,
    "retry_backoff_sec": [2, 5, 15]
  },
  "rag": {
    "enabled": true,
    "sources": ["./docs", "./examples"],
    "top_k": 8,
    "saturation": {
      "max_iterations": 5,
      "novelty_threshold": 0.15,
      "min_chunks": 10,
      "query_expansion": true
    }
  },
  "context": {
    "summarization_enabled": true,
    "max_raw_turns": 6,
    "compress_at_token_pct": 70
  },
  "monitoring": {
    "enabled": true,
    "interval_sec": 3,
    "warn_cpu_pct": 90,
    "warn_ram_pct": 85,
    "warn_gpu_mem_pct": 90,
    "show_per_core": false
  },
  "resilience": {
    "agent_timeout_sec": 600,
    "stuck_detection_sec": 300,
    "hitl_timeout_sec": 3600,
    "max_review_cycles": 10,
    "circuit_breaker_failures": 3,
    "circuit_breaker_cooldown_sec": 60,
    "checkpoint_every_agent": true,
    "auto_resume_on_reconnect": true
  }
}
```

**Приоритет правил:** `critical` > `high` > `medium` > `low`. Конфликты → `RuleConflictResolver` → `question_asked` → user pick → lock в manifest.

---

## 9. LangGraph — оркестрация

### Global State

```python
class MultiAgentState(TypedDict):
    session_id: str
    idea: str
    rules: dict
    spec_level: str           # L1|L2|L3|L4
    time_budget_sec: int | None
    started_at: float
    current_agent: str
    agent_outputs: dict[str, str]
    artifacts: dict[str, str]
    tasks: list[dict]
    assumptions: list[str]
    open_questions: list[str]
    context: ContextState
    saturation_report: dict | None
    supervisor_directives: dict
    review_reports: list[dict]
    review_cycles: int
    agent_call_counts: dict[str, int]  # anti-loop guard
    status: str
    errors: list[str]
    checkpoints: list[str]
    recovery_trace: list[dict]
```

### Graph flow

```
validate_input
  → supervisor
    ├─ researcher → context_manager → supervisor
    ├─ product_analyst → context_manager → supervisor
    ├─ architect → context_manager → supervisor
    ├─ [L3+] api_designer ┐
    │                      ├─ parallel merge → context_manager → supervisor
    ├─ [L3+] ui_designer  ┘
    ├─ [L2+] task_decomposer → supervisor
    ├─ reviewer → supervisor (fail) | export (pass)
    └─ wait_user → supervisor
```

---

## 10. Ollama интеграция

Все LLM и embeddings идут **только через Ollama** — локальный inference-сервер. Hugging Face Inference API, `transformers` и `sentence-transformers` не используются.

### Требования

- Ollama установлен на хосте или в отдельном контейнере (`ollama/ollama`)
- Модели заранее скачаны: `ollama pull llama3.2`, `ollama pull nomic-embed-text`
- Backend обращается к `ollama.base_url` (default `http://localhost:11434`; в Docker — `http://host.docker.internal:11434` или сервис `ollama:11434`)

### Provider abstraction

```python
# backend/app/llm/ollama_provider.py

class OllamaLLMProvider(Protocol):
    async def generate(self, messages: list[Message], **kwargs) -> str: ...
    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]: ...

class OllamaEmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...
```

**Транспорт:**
- Chat: `POST {base_url}/api/chat` (stream: `stream: true`) или OpenAI-compatible `POST {base_url}/v1/chat/completions`
- Embeddings: `POST {base_url}/api/embeddings` с полем `model` и `input`
- Health: `GET {base_url}/api/tags` — список доступных моделей

**Клиент:** `httpx.AsyncClient` или `ollama` Python SDK. Таймауты и `keep_alive` из конфига.

Конфиг из JSON (`rules.ollama`) переопределяет `.env`; `.env` — fallback для `base_url` и имён моделей.

### Рекомендуемые модели

| Назначение | Модель Ollama | Примечание |
|------------|---------------|------------|
| LLM (default) | `llama3.2` | 3B, быстрый на CPU/GPU |
| LLM (fallback) | `mistral`, `qwen2.5:7b` | по убыванию приоритета |
| Embeddings | `nomic-embed-text` | 768 dim, RAG |
| Embeddings (alt) | `mxbai-embed-large` | выше качество, больше RAM |

### Embeddings / RAG pipeline

```
ingest(sources) → chunk(RecursiveCharacterTextSplitter)
  → embed(OllamaEmbeddingProvider)
  → store(Chroma, collection="pink_spec_{session_id}")
  → saturation_loop → context_brief
```

При недоступности Ollama embeddings → `embedding_fallback: "keyword"` (BM25) → full-text scan.

---

## 11. API и WebSocket

### 11.1 REST Endpoints

| Method | Path | Описание |
|--------|------|----------|
| POST | `/api/v1/sessions` | Создать сессию |
| POST | `/api/v1/sessions/{id}/start` | Старт графа `{idea, rules}` |
| GET | `/api/v1/sessions/{id}` | Статус, артефакты, questions |
| GET | `/api/v1/spec-levels` | Metadata L1–L4 |
| GET | `/api/v1/sessions/{id}/supervisor` | Status report, agent, ETA |
| GET | `/api/v1/sessions/{id}/tasks` | Tasks tree |
| GET | `/api/v1/sessions/{id}/tasks/{task_id}` | Single task markdown |
| POST | `/api/v1/sessions/{id}/answers` | HITL ответы |
| GET | `/api/v1/sessions/{id}/artifacts/{type}` | Скачать артефакт |
| GET | `/api/v1/sessions/{id}/health` | `{status, stuck_reason, recoverable}` |
| POST | `/api/v1/sessions/{id}/resume` | Resume from checkpoint |
| POST | `/api/v1/sessions/{id}/recover` | Manual recovery action |
| GET | `/api/v1/sessions/{id}/logs` | Log history `?from_seq=0&limit=500` |
| GET | `/api/v1/sessions/{id}/export` | ZIP bundle |
| POST | `/api/v1/rag/ingest` | Загрузка reference docs |
| GET | `/api/v1/system/metrics` | Snapshot метрик (polling fallback) |
| GET | `/api/v1/health` | Health + Ollama connectivity (`/api/tags`) |
| GET | `/api/v1/schema/rules` | JSON Schema для UI |

### 11.2 WebSocket `/ws/sessions/{id}`

**Envelope format:**

```json
{
  "type": "log_entry",
  "ts": "2026-06-30T12:34:56.789Z",
  "seq": 142,
  "session_id": "uuid",
  "payload": {}
}
```

`seq` — monotonic counter; UI запрашивает `/logs?from_seq=N` при gap detection.

#### Все WS event types (server → client)

| `type` | Level | Payload |
|--------|-------|---------|
| `log_entry` | info/debug/warn/error | `{level, agent_id, message}` |
| `supervisor_routing` | info | `{next_agent, reason, remaining_sec}` |
| `agent_started` | info | `{agent_id, agent_name, pass_number}` |
| `agent_completed` | info | `{agent_id, duration_ms, status}` |
| `token_delta` | debug | `{agent_id, delta}` |
| `saturation_progress` | info | `{iteration, chunks, novelty}` |
| `summary_updated` | info | `{level, preview}` |
| `fallback_triggered` | warn | `{layer, step, message}` |
| `assumption_logged` | warn | `{text, agent_id}` |
| `question_asked` | info | `{question_id, text, options}` |
| `completion_check` | info | `{criteria, all_met}` |
| `budget_warning` | warn | `{remaining_sec, mode}` |
| `artifact_preview` | info | `{artifact_type, chunk}` |
| `task_batch_generated` | info | `{phase, count}` |
| `checkpoint_saved` | info | `{checkpoint_id, agent_id}` |
| `session_stuck` | warn | `{reason, since_sec, suggested_actions}` |
| `agent_timeout` | error | `{agent_id, timeout_sec}` |
| `circuit_breaker_open` | warn | `{agent_id, retry_after_sec}` |
| `circuit_breaker_closed` | info | `{agent_id}` |
| `recovery_started` | info | `{action, target_agent}` |
| `system_metrics` | — | см. §11.3 |
| `system_warning` | warn | `{metric, value, threshold, hint}` |
| `error` | error | `{code, message, recoverable}` |
| `done` | info | `{duration_sec, artifacts_count}` |
| `session_snapshot` | — | `{status, agents, log_tail, metrics_snapshot}` |

#### Client → server events

| `type` | Описание |
|--------|----------|
| `answer` | HITL ответ `{question_id, answer}` |
| `cancel` | Остановить сессию |
| `pause` / `resume` | Пауза/возобновление (L3/L4) |
| `retry_node` | Retry текущего агента |
| `subscribe` | `{agents, levels}` — фильтр |
| `request_snapshot` | Запросить state |

#### Connection lifecycle

| Этап | Поведение |
|------|-----------|
| Connect | Авто после POST /start |
| Reconnect | Backoff 1s→2s→5s→10s, max 10 попыток |
| Resume | Server шлёт `session_snapshot` + последние 200 log entries |
| Disconnect | SSE fallback → polling `/sessions/{id}` каждые 2s |
| Heartbeat | ping/pong каждые 30s; warning если нет pong 60s |

### 11.3 System Metrics

**Backend (psutil + optional pynvml):**

| Метрика | Источник |
|---------|---------|
| `cpu_percent` | `psutil.cpu_percent()` |
| `ram_percent` / `ram_used_mb` / `ram_total_mb` | `psutil.virtual_memory()` |
| `swap_percent` | `psutil.swap_memory()` |
| `disk_percent` | `psutil.disk_usage(output_path)` |
| `process_rss_mb` | `psutil.Process().memory_info()` |
| `gpu.util_percent` / `gpu.mem_used_mb` / `gpu.temp_c` | `pynvml` (optional) |

Сбор каждые 3 сек (configurable). Broadcast через тот же WS как `system_metrics`. Не пишется в `session_logs`.

---

## 12. UI спецификация

### 12.0 Принцип: полная прозрачность (Nothing Silent)

Пользователь **всегда** знает что делает агент. Любое действие backend → UI ≤500ms.

**Запрещено:**
- Silent fallback (без `fallback_triggered` в ленте + toast)
- Silent skip агента (без ASSUMPTION)
- Silent degradation (без `budget_warning` / `degraded` badge)
- Silent retry (без log entry «Retry #N»)
- Ошибки только в server logs

#### Карта: событие → UI surface (100% coverage)

| WS `type` | UI surface | Дополнительно |
|-----------|-----------|---------------|
| `log_entry` | Activity Feed | — |
| `supervisor_routing` | Timeline + Feed + Supervisor card | «Why» tooltip |
| `agent_started` / `agent_completed` | Timeline step + Feed | Duration badge |
| `token_delta` | Feed (toggle) + Artifact preview | Collapsed by default |
| `saturation_progress` | Feed + Saturation widget | Progress bar |
| `summary_updated` | Feed + Context panel | Expandable preview |
| `fallback_triggered` | Feed + Fallbacks tab + toast warn | Chain history |
| `assumption_logged` | Feed + Assumptions panel | Persistent list |
| `question_asked` | Dialog + Feed + sidebar badge | Blocking |
| `completion_check` | L4 checklist | Real-time ✓/✗ |
| `budget_warning` | Feed + banner + toast | Remaining time |
| `system_metrics` | Metrics bar + chart | — |
| `system_warning` | Metrics pulse + Feed + toast | Threshold |
| `artifact_preview` | Artifacts live tab | Streaming |
| `task_batch_generated` | Feed + Tasks tree refresh | Count badge |
| `session_stuck` | Recovery Panel + Feed + toast | Actions |
| `agent_timeout` | Recovery Panel + Feed + toast error | Agent name |
| `circuit_breaker_open` | Session Health + Feed | Countdown |
| `recovery_started` | Feed + Recovery Panel | Action label |
| `checkpoint_saved` | Feed + Session Health | ID |
| `error` | Feed + Recovery Panel + toast | Recoverable flag |
| `done` | Full summary + redirect CTA | Duration |
| `session_snapshot` | Full state rehydrate | All panels sync |

### 12.1 Design System — shadcn/ui

**Stack:** React + TypeScript + Vite + shadcn/ui (new-york) + Tailwind CSS

**Тема (CSS variables):**

```css
--primary: 330 70% 60%;          /* pink accent */
--primary-foreground: 0 0% 100%;
--background: 240 10% 4%;        /* zinc-950, dark default */
--card: 240 6% 10%;
--muted: 240 4% 16%;
--border: 240 4% 16%;
--ring: 330 70% 60%;
```

**Зависимости:**

| Пакет | Назначение |
|-------|------------|
| `shadcn/ui` | Component library |
| `tailwindcss` + `@tailwindcss/typography` | Layout + prose |
| `lucide-react` | Иконки |
| `recharts` | Sparklines |
| `@monaco-editor/react` | JSON Rules Editor |
| `react-markdown` + `remark-gfm` | Artifacts preview |
| `sonner` | Toast notifications |

**shadcn компоненты:**

```bash
npx shadcn@latest init  # style: new-york, base: zinc
npx shadcn@latest add button card badge progress tabs dialog sheet scroll-area
npx shadcn@latest add separator tooltip select input textarea switch sonner
npx shadcn@latest add sidebar command accordion alert skeleton toggle dropdown-menu
npx shadcn@latest add resizable table
```

### 12.2 Mission Control — Agent Workspace

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Pink Spec │ Session: my-service │ L3 │ ● Running │ WS Connected │ 🔔 3       │
├───────────┬────────────────────────────────────────────┬────────────────────┤
│           │  Supervisor Card + ETA / L4 checklist       │  Session Health    │
│  Sidebar  ├─────────────────────┬──────────────────────┤  Checkpoint: 2m    │
│  Overview │  Agent Timeline     │  Activity Feed        │  Circuit: OK       │
│  Activity │  (states, duration) │  (ALL events)         │  Assumptions: 2    │
│  Context  │                     │  [filters] [export]   │  Fallbacks: 1      │
│  Artifacts├─────────────────────┴──────────────────────┤  Open Q: 1         │
│  Tasks    │  Tabs: Live Artifacts │ Tasks │ Saturation   │                    │
│  Fallbacks│  (streaming preview)                        │  [Recovery Panel]  │
│  Recovery ├────────────────────────────────────────────┴────────────────────┤
│  Settings │  System Metrics: CPU ████░ 68% │ RAM █████ 82% │ GPU 92%         │
└───────────┴────────────────────────────────────────────────────────────────┘
```

#### Sidebar sections

| Section | Содержание | Триггер обновления |
|---------|------------|-------------------|
| Overview | Idea, spec level, elapsed, progress % | realtime |
| Activity | Activity Feed (focus mode) | WS stream |
| Context | Phase/session summaries, saturation | `summary_updated` |
| Artifacts | Live preview md/yaml | `artifact_preview` |
| Tasks | Mini tree + count | `task_batch_generated` |
| Fallbacks | Chronological fallback chain | `fallback_triggered` |
| Assumptions | All ASSUMPTIONs + who/when | `assumption_logged` |
| Decisions | Locked user decisions | on answer |
| Recovery | Stuck reason, health, actions | `session_stuck` |

#### Activity Feed

- Structured rows: Lucide icon + timestamp + agent badge + level color + message
- Click row → `Sheet` Event Inspector: full JSON payload, copy
- Filters: agent, level, type, tags `[Recovery]` `[Fallback]`
- Unread badge на sidebar при critical/warn вне вкладки
- Export: `.jsonl` full session trace

#### Post-completion Summary

При `done` / `completed_partial`:
- Duration, agents run, retries, fallbacks, assumptions counts
- Links to all artifacts + `gaps.md`
- Timeline replay (read-only)

### 12.3 Экраны

| Экран | Route | Функции |
|-------|-------|---------|
| Home | `/` | Idea input, Spec Level L1–L4 picker, preview |
| Rules Editor | `/rules` | Monaco JSON + live validation + presets |
| Agent Workspace | `/workspace/:id` | Mission Control |
| Artifacts Viewer | `/artifacts/:id` | Specs + Tasks + gaps.md |
| Settings | `/settings` | Ollama URL, models, monitoring, resilience |

### 12.4 Frontend component map

| Файл | Назначение |
|------|------------|
| `pages/Home.tsx` | Idea + spec level selector |
| `pages/RulesEditor.tsx` | Monaco + validation |
| `pages/AgentWorkspace.tsx` | Mission Control layout |
| `pages/ArtifactsViewer.tsx` | Tabs viewer |
| `pages/Settings.tsx` | Ollama + monitoring config |
| `components/workspace/ActivityFeed.tsx` | Центральная лента |
| `components/workspace/AgentTimeline.tsx` | All agents states |
| `components/workspace/SupervisorCard.tsx` | ETA / L4 checklist |
| `components/workspace/RecoveryPanel.tsx` | Actions when stuck |
| `components/observability/EventInspectorSheet.tsx` | Full payload |
| `components/observability/NotificationCenter.tsx` | 🔔 dropdown |
| `components/observability/AssumptionsPanel.tsx` | Persistent list |
| `components/observability/FallbacksPanel.tsx` | Chain history |
| `components/observability/SessionHealthCard.tsx` | Checkpoint/circuit |
| `components/artifacts/LiveArtifactsPreview.tsx` | Streaming markdown |
| `components/artifacts/TasksExplorer.tsx` | Tree + preview |
| `components/metrics/SystemMetricsPanel.tsx` | CPU/RAM/GPU bars |
| `components/metrics/MetricSparkline.tsx` | Recharts mini chart |
| `components/layout/AppSidebar.tsx` | Nav + sections |
| `components/layout/Header.tsx` | Status bar |
| `hooks/useAgentWebSocket.ts` | WS lifecycle |
| `hooks/useActivityFeed.ts` | Ring buffer 5000, filters |
| `hooks/useSystemMetrics.ts` | Metrics ring buffer |
| `hooks/useNotifications.ts` | Unread warn/error |
| `stores/sessionStore.ts` | Global session state |

---

## 13. Выходные артефакты

### manifest.json

```json
{
  "session_id": "uuid",
  "spec_level": "L3",
  "generated_at": "2026-06-30T12:34:56Z",
  "duration_sec": 1742,
  "rules_hash": "sha256:...",
  "artifacts": {
    "product_spec": "product_spec.md",
    "architecture_spec": "architecture_spec.md",
    "api_spec": "api_spec.openapi.yaml",
    "ui_spec": "ui_spec.md",
    "data_model": "data_model.md",
    "roadmap": "roadmap.md",
    "risk_register": "risk_register.md"
  },
  "tasks": {
    "index": "tasks/TASK_INDEX.md",
    "count": 67,
    "phases": 6
  },
  "context": {
    "session_summary": "...",
    "saturation": {"status": "complete", "chunks": 24, "iterations": 4}
  },
  "assumptions": [],
  "decisions": [],
  "agent_trace": [
    {"agent": "supervisor", "action": "route", "target": "researcher", "ts": "..."}
  ],
  "recovery_trace": [],
  "gaps_file": null
}
```

### gaps.md (при partial export)

```markdown
# Gaps & Recovery Report

## Session
- status: completed_partial
- reason: safety_cap | stuck | user_force | budget_exceeded

## Failed / Skipped Steps
- [Architect] timeout after 600s → used simplified sketch

## Unresolved Questions
- ...

## Manual Follow-up
1. ...
```

---

## 14. Структура репозитория

```
pink-spec/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── sessions.py
│   │   │   │   ├── rag.py
│   │   │   │   ├── system.py
│   │   │   │   └── schema.py
│   │   │   └── websocket.py
│   │   ├── agent/
│   │   │   ├── supervisor.py
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   ├── agents/
│   │   │   │   ├── product_analyst.py
│   │   │   │   ├── architect.py
│   │   │   │   ├── api_designer.py
│   │   │   │   ├── ui_designer.py
│   │   │   │   ├── task_decomposer.py
│   │   │   │   ├── researcher.py
│   │   │   │   ├── reviewer.py
│   │   │   │   └── context_manager.py
│   │   │   └── prompts/
│   │   ├── llm/
│   │   │   ├── ollama_provider.py
│   │   │   └── fallback_chain.py
│   │   ├── rag/
│   │   │   ├── ingest.py
│   │   │   ├── retriever.py
│   │   │   └── saturation.py
│   │   ├── schemas/
│   │   │   ├── rules.py
│   │   │   ├── events.py
│   │   │   └── state.py
│   │   ├── services/
│   │   │   ├── log_bus.py
│   │   │   ├── session_watchdog.py
│   │   │   ├── system_monitor.py
│   │   │   ├── session.py
│   │   │   └── export.py
│   │   └── db/
│   │       ├── models.py
│   │       └── connection.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── components.json
│   ├── tailwind.config.ts
│   ├── vite.config.ts
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/              # shadcn/ui
│   │   │   ├── layout/
│   │   │   ├── workspace/
│   │   │   ├── observability/
│   │   │   ├── metrics/
│   │   │   └── artifacts/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── lib/
│   │   ├── App.tsx
│   │   └── index.css
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── SPEC_AGENT.md            ← этот файл
│   ├── examples/
│   │   ├── rules-web-app.json
│   │   ├── rules-ml-pipeline.json
│   │   └── rules-minimal.json
│   └── templates/
│       ├── task.md
│       └── TASK_INDEX.md
├── models/                      # документация по Ollama-моделям (README)
├── output/                      # gitignored
├── data/                        # vectors, gitignored
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 15. Fallback-стратегии

### LLM fallbacks

| Step | Действие |
|------|----------|
| 1 | Primary model (`ollama.llm_model`) |
| 2 | `ollama.fallback_models[]` по порядку (другие теги Ollama) |
| 3 | Template-based degraded mode из `docs/templates/` |
| 4 | Fail session + partial export если артефакты уже есть |

### Embedding fallbacks

| Step | Действие |
|------|----------|
| 1 | Ollama embeddings (`ollama.embedding_model`) |
| 2 | Keyword/BM25 retrieval |
| 3 | Full-text scan uploaded docs |
| 4 | Saturation skipped → `saturation.status: "fallback_no_embeddings"` |

### Agent fallbacks

| Step | Действие |
|------|----------|
| 1 | Retry same agent (exponential backoff) |
| 2 | Simplified prompt — shorter output schema |
| 3 | Substitute agent (e.g. Architect делает minimal API sketch) |
| 4 | Skip + log ASSUMPTION |
| 5 | L4: user escalation через `question_asked` |

### Transport fallbacks

WebSocket → SSE (`/api/v1/sessions/{id}/stream`) → polling REST каждые 2s. UI auto-detect.

### Spec-level fallbacks (L1–L3 при budget exceeded)

1. Graceful degradation (сократить scope)
2. Downgrade artifact set (L3 → L2)
3. Force export partial + `gaps.md`

---

## 16. Failure modes и Recovery

### Session state machine

```
pending → running ↔ paused
running → waiting_user ↔ stuck
running → degraded → completed_partial
running → completed
stuck → failed (unrecoverable)
stuck → completed_partial (force export)
```

### Каталог сценариев

#### A. LLM и генерация

| Сценарий | Detection | Recovery |
|----------|-----------|----------|
| LLM timeout | `agent_timeout_sec` (600s) | Cancel → fallback model → simplified prompt |
| Empty response | Output validator | Retry 2x → template fill |
| Invalid JSON | Pydantic validation | «fix JSON» prompt → 3x → skip + ASSUMPTION |
| Context overflow | Ollama 400 / token counter | Emergency summarization → retry compressed |
| Ollama unavailable | Connection refused / timeout | Retry backoff → fallback model → template mode |
| Model not found | Ollama 404 (`model not found`) | UI hint: `ollama pull <model>` → fallback model |
| Hallucination loop | Same n-gram > 5 times | Truncate → retry temperature=0 |

#### B. Multi-agent / Supervisor

| Сценарий | Detection | Recovery |
|----------|-----------|----------|
| Review loop | `review_cycles > max_review_cycles` (10) | Force pass + `review_waiver` in manifest |
| Routing cycle A→B→A | Route history hash repeats 3x | Break → export partial or escalate |
| Anti-loop (same agent) | 5+ calls без score delta | Simplify / escalate / gaps |
| Dead-end routing | `next_agent: null` 2x | Default → Reviewer → partial |
| Conflicting rules | RuleConflictResolver | `question_asked` → user pick |

#### C. RAG / Embeddings

| Сценарий | Detection | Recovery |
|----------|-----------|----------|
| Saturation не сходится | `max_iterations` hit | Partial + ASSUMPTION |
| Chroma unavailable | Health check | Disable RAG; full-text fallback |
| Corrupt upload | Ingest validator | Skip file + warn |
| Empty corpus | `chunk_count == 0` | Skip enrichment; warn in manifest |

#### D. HITL и пользователь

| Сценарий | Detection | Recovery |
|----------|-----------|----------|
| User не отвечает | `hitl_timeout_sec` (3600) | Reminder toast → ASSUMPTION default → continue |
| User cancel | WS message | Stop after current agent → partial export |
| Tab closed | WS disconnect | Session continues; checkpoint; resume on reconnect |
| Duplicate start | Idempotency key | Reject or attach to existing run |

#### E. Infrastructure

| Сценарий | Detection | Recovery |
|----------|-----------|----------|
| OOM / RAM > 95% | SystemMonitor `system_warning` | Pause → summarize → resume or smaller Ollama model |
| Disk full | IOError on export | Stop → export what fits → error |
| Backend crash | Process die | On restart: offer resume from checkpoint |
| SQLite locked | DB timeout | Retry 3x → in-memory queue → flush later |

### Watchdog & Circuit Breaker

**Watchdog triggers (→ `stuck`):**
- `last_state_change_at > stuck_detection_sec` (300s)
- `agent running > agent_timeout_sec` (600s)
- `review_cycles > max_review_cycles`

**Circuit breaker:** 3 consecutive failures → open 60s → WS `circuit_breaker_open`. Supervisor routes around.

### Checkpoint & Resume

- После каждого агента (L3/L4): persist `MultiAgentState` → SQLite `session_checkpoints`
- Artifacts flushed to `output/{session_id}/`
- On reconnect: `session_snapshot` + `resume_from_checkpoint`

### Recovery actions (via REST)

```
POST /sessions/{id}/recover
{
  "action": "retry_agent" | "skip_agent" | "force_export" | "restart_from",
  "target_agent": "architect"  // optional
}
```

---

## 17. Безопасность и ограничения

- Ollama `base_url` — только server-side; при внешнем Ollama — без публичного exposure
- Проверка доступности моделей при старте сессии (`GET /api/tags`)
- Upload RAG: whitelist `.md`, `.txt`, `.pdf`; max 10MB
- Hard cap: L1–L3 — 35 min; L4 — `safety_cap_sec` (default 2ч, max 4ч)
- L3/L4: checkpoint после каждого агента (resume on disconnect)
- Sandbox: агент НЕ исполняет код — только документы
- Rate limit на `/start`: 5 req/min локально
- Idempotency key на `/start` для предотвращения дублей
