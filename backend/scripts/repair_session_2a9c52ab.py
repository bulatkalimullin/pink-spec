#!/usr/bin/env python3
"""Repair session 2a9c52ab artifacts and tasks. Run inside backend container."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

SESSION = "2a9c52ab-cf69-48d5-bd97-7da2cdc24332"
ROOT = Path("/output") / SESSION
DOCS = ROOT / "docs"
TASKS_DIR = ROOT / "tasks"


def write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {rel} ({len(content)} bytes)")


SPEC_CANON = """# SPEC_CANON — единый source of truth (MVP)

**Session:** 2a9c52ab-cf69-48d5-bd97-7da2cdc24332  
**Version:** 1.1 (repair)  
**Status:** Canonical — все артефакты должны ссылаться на этот документ при противоречиях.

---

## 1. Продукт

Telegram dating bot + Telegram Mini App (WebApp) для подбора людей по локации, интересам и (Phase 2) анализу фото.

**Ключевое ограничение MVP:** после взаимного match — только **обмен Telegram username**, без in-bot чата.

---

## 2. Технологический стек

| Слой | Технология |
|------|------------|
| Backend API | Python 3.12, FastAPI |
| Telegram Bot | aiogram 3.x |
| WebApp | React + Telegram Mini App SDK |
| Database | PostgreSQL 16 |
| Cache / rate limit | Redis 7 |
| Object storage | S3-compatible (фото профилей) |

**Запрещено в MVP:** Node.js backend, MongoDB как primary store, сторонние geo-API.

---

## 3. Идентификаторы

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID | Внутренний primary key |
| `telegram_id` | BIGINT | Уникальный Telegram user id |
| `telegram_username` | VARCHAR(32), nullable | @username |

---

## 4. Matching (MVP)

| Фактор | Вес | Формула |
|--------|-----|---------|
| Location | 0.35 | `1 / (1 + distance_km)` Haversine |
| Interests | 0.45 | Jaccard |
| Age | 0.20 | `1 / (1 + |age_a - age_b|)` |
| Photo | 0.00 | Phase 2 |

---

## 5. NFR

| Метрика | Target |
|---------|--------|
| Throughput | ≥ 3000 RPS |
| `GET /matches/suggest` p95 | ≤ 200 ms |
| Availability | 99.5% |
| TLS | 1.3 |
| Encryption at rest | AES-256 |

---

## 6. Conversation flow

Mutual accept → обмен username. Бот не проксирует сообщения.

См. `user_flow_match_conversation.md` для sequence diagram.

---

## 7. Decisions

| ID | Решение |
|----|---------|
| D1 | UUID + telegram_id |
| D2 | Photo weight = 0 в MVP |
| D3 | Mutual username reveal |
| D4 | PostgreSQL + Redis |
| D5 | FastAPI + aiogram |
| D6 | Нет сторонних geo API |
"""

MATCHING_SPEC = """## Matching Algorithm & Data Model Specification

**Artifact Key:** matching_algorithm_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Introduction

Weighted scoring для рекомендаций. MVP: location, interests, age. Photo analysis — Phase 2.

## 2. Core Matching Algorithm

### 2.1 Input Factors & Weighting (MVP)

| Factor | Weight | Formula |
|--------|--------|---------|
| Location | 35% | `Score_Location = 1 / (1 + distance_km)` via Haversine |
| Interests | 45% | `Score_Interests = |A ∩ B| / |A ∪ B|` (Jaccard) |
| Age | 20% | `Score_Age = 1 / (1 + |age_a - age_b|)` |
| Photo | 0% | Disabled in MVP; Phase 2 target weight 15–20% |

```text
Total_Score = 0.35 * Score_Location + 0.45 * Score_Interests + 0.20 * Score_Age
```

### 2.2 A/B Testing

- Metrics: `accept_rate`, `mutual_match_rate`, `profile_completion_rate`
- Feature flag: `matching_weights_variant`
- Minimum sample: 1000 users per variant before weight change

### 2.3 Ranking

Top-N candidates by `Total_Score`, exclude already declined/blocked, respect `search_radius_km`.

## 3. Data Model

### 3.1 User Profile

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `telegram_id` | BIGINT | Unique |
| `telegram_username` | VARCHAR(32) | Nullable |
| `age` | INTEGER | 18–100 |
| `age_preference` | JSON | min ≤ max |
| `latitude` | FLOAT | -90..90 |
| `longitude` | FLOAT | -180..180 |
| `search_radius_km` | INTEGER | 1–500 |
| `interests` | TEXT[] | 1–20 items |
| `relationship_goal` | ENUM | casual, serious, friendship |
| `photo_url` | TEXT | Nullable |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 3.2 Match

| Field | Type | Description |
|-------|------|-------------|
| `match_id` | UUID | PK |
| `user_id_1` | UUID | FK users |
| `user_id_2` | UUID | FK users |
| `score` | FLOAT | 0.0–1.0 |
| `status` | ENUM | pending, accepted_by_1, mutual, declined, blocked |
| `created_at` | TIMESTAMPTZ | |

## 4. Conversation (reference only)

После mutual accept — обмен Telegram username. In-bot chat **не используется**. См. `user_flow_match_conversation.md`.

## 5. Performance

- Pre-filter candidates by geo bounding box before scoring
- Cache suggestions per user TTL 5 min
- Target p95 ≤ 200 ms at 3000 RPS (see `performance_spec.md`)

## 6. Phase 2 — Photo Analysis

Async pipeline: S3 upload → CV worker → `photo_embedding`. Rebalance weights when enabled.
"""

USER_PROFILE = """## User Profile Schema Design

**Artifact Key:** user_profile_schema
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Introduction

Схема профиля для Telegram bot и Mini App. Расстояние считается Haversine на координатах из Telegram Location — **без внешних geo API**.

## 2. Schema Overview

```json
{
  "id": "uuid",
  "telegram_id": 123456789,
  "telegram_username": "optional",
  "age": 28,
  "age_preference": { "min": 22, "max": 35 },
  "location": { "latitude": 55.7558, "longitude": 37.6173 },
  "search_radius_km": 50,
  "interests": ["hiking", "music"],
  "relationship_goal": "serious",
  "description": "max 500 chars",
  "photo_urls": ["https://..."],
  "privacy_settings": {
    "profile_visible": true,
    "show_distance": true
  },
  "last_active_at": "ISO8601",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

## 3. Validation Rules

| Field | Rules |
|-------|-------|
| `age` | 18–100 |
| `age_preference` | min ≤ max, both 18–100 |
| `latitude` | -90..90 |
| `longitude` | -180..180 |
| `interests` | 1–20, each 2–50 chars, from predefined list + custom |
| `relationship_goal` | enum: casual, serious, friendship |
| `description` | max 500 chars |
| `photo_urls` | max 5, valid HTTPS URLs |
| `search_radius_km` | 1–500 |

## 4. Privacy

- `telegram_id` не отдаётся другим пользователям
- Точные координаты скрыты; показывается distance_km если `show_distance=true`

## 5. Related

- `matching_algorithm_spec.md` — scoring
- `security_spec.md` — encryption
"""

API_SPEC = """# API Endpoint Design

**Artifact Key:** api_endpoint_design
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Introduction

REST API для bot и Mini App. Auth через Telegram `initData`. Target: 3000+ RPS.

## 2. Authentication

Header: `X-Telegram-Init-Data` — HMAC-SHA256 validation per Telegram WebApp spec.
Bot webhook: verify `X-Telegram-Bot-Api-Secret-Token`.

No password/JWT registration — identity from Telegram only.

## 3. Error Model

```json
{ "code": "VALIDATION_ERROR", "message": "human readable", "details": {} }
```

| HTTP | code | When |
|------|------|------|
| 400 | VALIDATION_ERROR | Invalid input |
| 401 | UNAUTHORIZED | Bad initData |
| 404 | NOT_FOUND | Resource missing |
| 429 | RATE_LIMITED | Too many requests |
| 500 | INTERNAL_ERROR | Server error |

## 4. Endpoints

### 4.1 User Profile

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/users/me` | GET | initData | Current profile |
| `/users/me` | PUT | initData | Create/update profile |
| `/users/me` | DELETE | initData | Delete account (GDPR) |

**PUT /users/me request:**
```json
{
  "age": 28,
  "age_preference": { "min": 22, "max": 35 },
  "location": { "latitude": 55.75, "longitude": 37.61 },
  "search_radius_km": 50,
  "interests": ["hiking"],
  "relationship_goal": "serious",
  "description": "..."
}
```

### 4.2 Matches

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/matches/suggest` | GET | initData | Ranked suggestions (limit=20) |
| `/matches/{id}/accept` | POST | initData | Accept match |
| `/matches/{id}/decline` | POST | initData | Decline match |
| `/matches/suggest/reset` | POST | initData | Invalidate suggestion cache |

**GET /matches/suggest response:**
```json
{
  "matches": [
    {
      "match_id": "uuid",
      "score": 0.85,
      "display_name": "Anna",
      "age": 26,
      "distance_km": 3.2,
      "interests": ["hiking", "music"],
      "photo_url": "https://..."
    }
  ]
}
```

### 4.3 Username Reveal

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/matches/{id}/reveal` | GET | initData | Peer username after mutual accept |

Response when mutual: `{ "telegram_username": "@peer", "match_id": "..." }`

## 5. Rate Limiting

- 60 req/min per user (Redis sliding window)
- 10 `/matches/suggest` per min per user

## 6. NFR

- p95 `GET /matches/suggest` ≤ 200 ms
- p95 `PUT /users/me` ≤ 150 ms
"""

USER_FLOW = """## User Flow — Match Suggestion to Conversation

**Artifact Key:** user_flow_match_conversation
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Introduction

Flow: onboarding → suggestions → mutual accept → **обмен Telegram username**. Без in-bot messaging.

## 2. Sequence Diagram

```mermaid
sequenceDiagram
  participant U as User
  participant B as Bot
  participant API as API
  participant P as Peer
  U->>B: /start
  B->>U: Profile wizard
  U->>B: Submit profile
  B->>API: PUT /users/me
  U->>B: Show matches
  B->>API: GET /matches/suggest
  API->>B: Ranked cards
  B->>U: Match card
  U->>B: Accept
  B->>API: POST /matches/id/accept
  API->>P: Pending notification
  P->>B: Accept
  B->>API: POST /matches/id/accept
  API->>U: Peer username
  API->>P: User username
```

## 3. Detailed Steps

### 3.1 Onboarding

1. User sends `/start`
2. Bot explains purpose
3. Collect: age, age preference, location (Telegram share), interests, relationship_goal, optional photo
4. `PUT /users/me`

### 3.2 Match Suggestion

1. User requests matches
2. `GET /matches/suggest`
3. Display: photo, name, age, distance, top interests, score %

### 3.3 Mutual Accept & Username Exchange

1. User taps Accept → `POST /matches/{id}/accept`
2. Peer notified; must also Accept
3. On mutual: both receive `@username` via bot message
4. Users continue in native Telegram DM — bot exits flow

## 4. Error Handling

| Case | Behavior |
|------|----------|
| No matches | Suggest widen radius or add interests |
| Invalid input | Inline validation, retry step |
| Network error | Retry with backoff message |
| Peer declines | Notify user, remove from queue |
| Block | Permanent hide, audit log |

## 5. Edge Cases

- User without `@username`: prompt to set username in Telegram settings before reveal
- One-sided accept: 7-day expiry, then auto-decline
- Re-match after decline: blocked 30 days
"""

SECURITY_SPEC = """# Security Specification

**Artifact Key:** security_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Threat Model

| Threat | Mitigation |
|--------|------------|
| Spoofed Telegram identity | HMAC validate initData |
| Location stalking | Show distance_km only; hide exact coords |
| Fake profiles | Report/block; rate limits on profile creation |
| Data breach | AES-256 at rest, TLS 1.3 in transit |
| Abuse / scraping | Rate limiting, bot detection on suggest endpoint |

## 2. Authentication

- **Mini App / API:** `X-Telegram-Init-Data` HMAC-SHA256 with bot token
- **Bot webhook:** secret token header
- No passwords — bcrypt not required for MVP

## 3. Encryption

| Data | In transit | At rest |
|------|------------|---------|
| API traffic | TLS 1.3 | N/A |
| PII (location, photos) | TLS 1.3 | AES-256 (DB + S3) |
| Redis cache | TLS in prod | encrypted volume |

## 4. Authorization

- Users access only own profile via initData `user.id`
- `/matches/{id}/reveal` only when `status=mutual` and caller is participant

## 5. GDPR / Account Deletion

- `DELETE /users/me` — hard delete PII within 30 days
- Export on request (profile JSON)

## 6. Audit Log

Log: accept, decline, block, username_reveal (user_id, match_id, timestamp)
"""

PERFORMANCE_SPEC = """# Performance Specification

**Artifact Key:** performance_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Targets

| Metric | Target |
|--------|--------|
| Aggregate throughput | ≥ 3000 RPS |
| `GET /matches/suggest` p95 | ≤ 200 ms |
| `PUT /users/me` p95 | ≤ 150 ms |
| Availability | 99.5% monthly |

## 2. Capacity Model

Assumptions: 50k MAU, peak 3000 RPS, avg 20 candidates scored per suggest.

- **Geo pre-filter:** PostGIS `ST_DWithin` → ~200 candidates max
- **Scoring:** in-memory for filtered set, < 5 ms
- **Cache:** Redis suggestion list TTL 300s, key `suggest:{user_id}`
- **DB pool:** 50 connections per API instance, 4 instances

## 3. Scaling

- Horizontal: stateless API behind load balancer
- Read replicas for profile reads
- Async workers for photo analysis (Phase 2)

## 4. Load Testing

- k6 scenario: 3000 RPS mixed (70% suggest, 20% profile, 10% accept)
- Pass criteria: p95 ≤ targets, error rate < 0.1%
"""

PERSONALIZATION_SPEC = """# Personalization Specification

**Artifact Key:** personalization_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## 1. Strategy

MVP: rule-based weighted scoring + implicit feedback. Phase 2: collaborative filtering + photo embeddings.

## 2. Cold Start (new user)

- Use declared interests and location only
- Show diverse top-5 (not only highest score) for exploration
- Prompt profile completion if < 3 interests

## 3. Warm Personalization (implicit feedback)

| Signal | Effect |
|--------|--------|
| Accept match | +weight overlap interests with peer |
| Decline | -0.1 score similar profiles 24h |
| Skip (no action) | neutral |
| Profile edit | invalidate suggest cache |

## 4. Metrics

- `accept_rate` = accepts / impressions
- `mutual_match_rate` = mutual / accepts
- `time_to_mutual` median hours

## 5. Phase 2

- Photo embedding cosine similarity
- Session-based re-ranking from swipe patterns
"""

DEPLOYMENT_SPEC = """# Deployment Specification

**Artifact Key:** deployment_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)

## 1. Environments

| Env | Purpose |
|-----|---------|
| staging | Integration tests |
| production | Live users |

## 2. Components

- `api` — FastAPI (2+ replicas)
- `bot` — aiogram webhook worker
- `postgres` — primary + replica
- `redis` — cache + rate limit
- `minio` or S3 — photos

## 3. CI/CD

GitHub Actions: lint → test → build image → deploy staging → manual promote prod.

## 4. Secrets

Bot token, DB URL, Redis URL, S3 keys — via env / vault. Never in repo.
"""

OBSERVABILITY_SPEC = """# Observability Specification

**Artifact Key:** observability_spec
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)

## 1. Metrics (Prometheus)

- `http_request_duration_seconds` histogram by route
- `matches_suggest_candidates_total`
- `matches_mutual_total`
- `rate_limit_hits_total`

## 2. Alerts

| Alert | Condition |
|-------|-----------|
| High latency | p95 suggest > 300ms for 5m |
| Error spike | 5xx rate > 1% for 5m |
| DB pool exhausted | waiting connections > 10 |

## 3. Logging

Structured JSON: request_id, user_id (hashed), route, status, duration_ms.

## 4. Tracing

OpenTelemetry on API → Postgres, Redis spans.
"""

RISK_REGISTER = """# Risk Register

**Artifact Key:** risk_register
**Project:** Телеграмм бот приложение для свиданий
**Version:** 1.1 (repair)

| ID | Risk | Impact | Likelihood | Mitigation |
|----|------|--------|------------|------------|
| R1 | Photo ML bias | High | Med | Phase 2 only; human review sample |
| R2 | Location stalking | High | Med | Distance only; block/report |
| R3 | Fake profiles | Med | High | Rate limits; report flow |
| R4 | 3000 RPS overload | High | Med | Cache, geo index, load test |
| R5 | Telegram API changes | Med | Low | Pin SDK versions; monitor changelog |
| R6 | Username reveal without consent | High | Low | Mutual accept gate + audit log |
"""

PROJECT_SUMMARY = """# Project Summary

**Artifact Key:** project_summary
**Session:** 2a9c52ab-cf69-48d5-bd97-7da2cdc24332
**Version:** 1.1 (repair)

## Overview

Telegram dating bot + Mini App с подбором по локации, интересам и возрасту. MVP без photo ML. После mutual match — обмен @username.

## Repair Status

Исходная L4-генерация имела 14 failed review cycles. Выполнен manual repair:
- Создан `SPEC_CANON.md` как source of truth
- Исправлены 4 core specs
- Переписаны security, performance, personalization, deployment, observability, risk
- Tasks сжаты с 113 до 30

## Stack

Python FastAPI + aiogram + React Mini App + PostgreSQL + Redis.

## Key NFR

3000 RPS, p95 suggest ≤ 200ms, 99.5% availability.

## Next Steps

1. Implement Phase 1 tasks (see `tasks/TASK_INDEX.md`)
2. k6 load test before production
3. Phase 2: photo analysis pipeline
"""

GENERIC_SPEC = """# Generic Project Specification

**Artifact Key:** generic_spec
**Session:** 2a9c52ab-cf69-48d5-bd97-7da2cdc24332
**Version:** 1.1 (repair)

## Purpose

Telegram-бот для знакомств с рекомендательной системой и Mini App интерфейсом.

## Scope MVP

- Регистрация через Telegram
- Профиль: возраст, локация, интересы, цели
- Рекомендации matches
- Mutual accept → обмен username

## Out of Scope MVP

- In-bot messaging
- Photo ML analysis
- Video chat
- Сторонние интеграции (maps, social)

## Canonical Docs

All details in `SPEC_CANON.md` and linked artifacts.
"""

GAPS_MD = """# Gaps & Recovery Report

## Session
- status: repaired
- reason: manual repair after 14 failed review cycles

## Original Issues (resolved in repair)
- 8 duplicate/broken artifacts with wrong artifact_key
- Missing NFR formalization
- 113 duplicate tasks
- Contradictions between specs (weights, user_id, conversation flow)
- generic_spec corrupted
- RAG collected 0 chunks (embeddings bug)

## Manual Follow-up
1. Run k6 load tests before production deploy
2. Implement Phase 2 photo analysis when MVP stable
3. Legal review for dating app in target jurisdiction
"""

TASK_DEFINITIONS = [
    {
        "id": "001", "phase": "01-foundation", "title": "Initialize Python monorepo",
        "priority": "high", "estimated_minutes": 45, "depends_on": [],
        "spec_refs": ["docs/SPEC_CANON.md#2"],
        "goal": "FastAPI + aiogram project structure with Docker Compose.",
        "context": "Foundation per SPEC_CANON stack.",
        "steps": ["Create backend/ with FastAPI app", "Add aiogram bot package", "Docker Compose: api, bot, postgres, redis"],
        "acceptance_criteria": ["make up starts all services", "Health endpoint returns 200"],
        "notes": "Python only — no Node.js.", "verification": "curl /health",
        "slug": "initialize-python-monorepo",
    },
    {
        "id": "002", "phase": "01-foundation", "title": "Configure PostgreSQL schema migrations",
        "priority": "high", "estimated_minutes": 60, "depends_on": ["01-001"],
        "spec_refs": ["docs/matching_algorithm_spec.md#3"],
        "goal": "Alembic migrations for users and matches tables.",
        "context": "Data model from matching_algorithm_spec.",
        "steps": ["Add Alembic", "Create users table", "Create matches table"],
        "acceptance_criteria": ["alembic upgrade head succeeds"],
        "notes": "Use UUID PKs.", "verification": "psql \\dt",
        "slug": "configure-postgresql-migrations",
    },
    {
        "id": "003", "phase": "01-foundation", "title": "Set up Redis for cache and rate limiting",
        "priority": "high", "estimated_minutes": 30, "depends_on": ["01-001"],
        "spec_refs": ["docs/performance_spec.md#2"],
        "goal": "Redis client and connection pool.",
        "context": "Required for 3000 RPS suggest cache.",
        "steps": ["Add redis dependency", "Create Redis settings", "Health check includes Redis ping"],
        "acceptance_criteria": ["Redis ping in /health"],
        "notes": "", "verification": "Integration test",
        "slug": "setup-redis-cache",
    },
    {
        "id": "004", "phase": "01-foundation", "title": "Implement Telegram initData authentication",
        "priority": "critical", "estimated_minutes": 90, "depends_on": ["01-001"],
        "spec_refs": ["docs/api_endpoint_design.md#2", "docs/security_spec.md#2"],
        "goal": "Validate X-Telegram-Init-Data on API requests.",
        "context": "No password auth.",
        "steps": ["HMAC validation middleware", "Extract telegram_id", "Reject invalid signatures"],
        "acceptance_criteria": ["Valid initData passes", "Invalid returns 401"],
        "notes": "", "verification": "Unit tests with fixture initData",
        "slug": "telegram-initdata-auth",
    },
    {
        "id": "005", "phase": "01-foundation", "title": "Define user profile Pydantic schemas",
        "priority": "high", "estimated_minutes": 45, "depends_on": ["01-002"],
        "spec_refs": ["docs/user_profile_schema.md#3"],
        "goal": "Request/response models with validation.",
        "context": "Matches user_profile_schema validation rules.",
        "steps": ["Create ProfileCreate/Update/Response models", "Add field validators"],
        "acceptance_criteria": ["Invalid age rejected", "Interests 1-20 enforced"],
        "notes": "", "verification": "pytest validators",
        "slug": "user-profile-pydantic-schemas",
    },
    {
        "id": "006", "phase": "02-backend", "title": "Implement PUT/GET/DELETE /users/me",
        "priority": "critical", "estimated_minutes": 120, "depends_on": ["01-004", "01-005"],
        "spec_refs": ["docs/api_endpoint_design.md#4.1"],
        "goal": "Profile CRUD endpoints.",
        "context": "Core user API.",
        "steps": ["Repository layer", "Service layer", "FastAPI routes"],
        "acceptance_criteria": ["CRUD works with auth", "DELETE removes PII"],
        "notes": "", "verification": "API integration tests",
        "slug": "users-me-endpoints",
    },
    {
        "id": "007", "phase": "02-backend", "title": "Implement matching algorithm core",
        "priority": "critical", "estimated_minutes": 180, "depends_on": ["01-002", "01-005"],
        "spec_refs": ["docs/matching_algorithm_spec.md#2", "docs/SPEC_CANON.md#4"],
        "goal": "Haversine + Jaccard + age scoring.",
        "context": "MVP weights from SPEC_CANON.",
        "steps": ["Geo bounding box filter", "Score function", "Rank top-N"],
        "acceptance_criteria": ["Scores 0-1", "Weights match canon", "Unit tests pass"],
        "notes": "Photo weight = 0.", "verification": "pytest matching",
        "slug": "matching-algorithm-core",
    },
    {
        "id": "008", "phase": "02-backend", "title": "Implement GET /matches/suggest with Redis cache",
        "priority": "critical", "estimated_minutes": 120, "depends_on": ["01-003", "02-007"],
        "spec_refs": ["docs/api_endpoint_design.md#4.2", "docs/performance_spec.md"],
        "goal": "Cached match suggestions endpoint.",
        "context": "p95 ≤ 200ms target.",
        "steps": ["Call matching service", "Cache in Redis TTL 300s", "Rate limit 10/min"],
        "acceptance_criteria": ["Returns ranked list", "Cache hit on repeat", "Rate limit works"],
        "notes": "", "verification": "Integration + k6 smoke",
        "slug": "matches-suggest-endpoint",
    },
    {
        "id": "009", "phase": "02-backend", "title": "Implement match accept/decline flow",
        "priority": "high", "estimated_minutes": 90, "depends_on": ["02-008"],
        "spec_refs": ["docs/user_flow_match_conversation.md#3.3"],
        "goal": "POST accept/decline with status machine.",
        "context": "Mutual accept required for reveal.",
        "steps": ["Status transitions", "Notify peer via bot", "Expiry job 7 days"],
        "acceptance_criteria": ["Mutual triggers reveal eligibility", "Decline blocks 30d"],
        "notes": "", "verification": "State machine tests",
        "slug": "match-accept-decline",
    },
    {
        "id": "010", "phase": "02-backend", "title": "Implement GET /matches/{id}/reveal",
        "priority": "high", "estimated_minutes": 60, "depends_on": ["02-009"],
        "spec_refs": ["docs/api_endpoint_design.md#4.3", "docs/security_spec.md#4"],
        "goal": "Username reveal after mutual accept.",
        "context": "Audit log each reveal.",
        "steps": ["Check mutual status", "Return peer username", "Log audit event"],
        "acceptance_criteria": ["403 if not mutual", "Audit log written"],
        "notes": "", "verification": "Integration test",
        "slug": "matches-reveal-endpoint",
    },
    {
        "id": "011", "phase": "02-backend", "title": "Add API rate limiting middleware",
        "priority": "medium", "estimated_minutes": 45, "depends_on": ["01-003"],
        "spec_refs": ["docs/api_endpoint_design.md#5"],
        "goal": "60 req/min per user global limit.",
        "context": "Redis sliding window.",
        "steps": ["Middleware", "429 response", "Metrics counter"],
        "acceptance_criteria": ["429 after limit", "Metrics exported"],
        "notes": "", "verification": "Load test burst",
        "slug": "api-rate-limiting",
    },
    {
        "id": "012", "phase": "02-backend", "title": "Implement structured error responses",
        "priority": "medium", "estimated_minutes": 30, "depends_on": ["01-001"],
        "spec_refs": ["docs/api_endpoint_design.md#3"],
        "goal": "Uniform error JSON model.",
        "context": "All routes use error handler.",
        "steps": ["Exception handlers", "Error codes enum"],
        "acceptance_criteria": ["All errors match schema"],
        "notes": "", "verification": "API tests",
        "slug": "structured-error-responses",
    },
    {
        "id": "013", "phase": "02-backend", "title": "Add photo upload to S3",
        "priority": "medium", "estimated_minutes": 90, "depends_on": ["02-006"],
        "spec_refs": ["docs/user_profile_schema.md#3"],
        "goal": "Store profile photos in object storage.",
        "context": "Encrypted at rest per security_spec.",
        "steps": ["S3 client", "Presigned upload URL", "Save photo_url in profile"],
        "acceptance_criteria": ["Upload works", "URL in profile"],
        "notes": "CV analysis Phase 2.", "verification": "Manual upload test",
        "slug": "photo-upload-s3",
    },
    {
        "id": "014", "phase": "03-frontend", "title": "Set up Telegram Mini App React shell",
        "priority": "high", "estimated_minutes": 60, "depends_on": ["01-001"],
        "spec_refs": ["docs/webapp_telegram_design.md"],
        "goal": "Mini App with Telegram WebApp SDK.",
        "context": "initData passed to API.",
        "steps": ["Vite + React", "Telegram SDK init", "Theme from Telegram"],
        "acceptance_criteria": ["Opens in Telegram", "initData available"],
        "notes": "", "verification": "Test in Telegram",
        "slug": "mini-app-react-shell",
    },
    {
        "id": "015", "phase": "03-frontend", "title": "Build profile onboarding wizard",
        "priority": "high", "estimated_minutes": 120, "depends_on": ["03-014", "02-006"],
        "spec_refs": ["docs/user_flow_match_conversation.md#3.1"],
        "goal": "Multi-step profile form in Mini App.",
        "context": "Calls PUT /users/me.",
        "steps": ["Age step", "Location step", "Interests step", "Submit"],
        "acceptance_criteria": ["Validation inline", "Profile saved"],
        "notes": "", "verification": "E2E manual",
        "slug": "profile-onboarding-wizard",
    },
    {
        "id": "016", "phase": "03-frontend", "title": "Build match card list UI",
        "priority": "high", "estimated_minutes": 90, "depends_on": ["03-014", "02-008"],
        "spec_refs": ["docs/user_flow_match_conversation.md#3.2"],
        "goal": "Display suggestions with accept/decline.",
        "context": "No swipe animations — list + buttons.",
        "steps": ["Fetch suggest", "Match card component", "Accept/decline actions"],
        "acceptance_criteria": ["Shows score and distance", "Actions call API"],
        "notes": "Accept/decline buttons, not swipe.", "verification": "Manual E2E",
        "slug": "match-card-list-ui",
    },
    {
        "id": "017", "phase": "03-frontend", "title": "Build username reveal screen",
        "priority": "high", "estimated_minutes": 60, "depends_on": ["03-016", "02-010"],
        "spec_refs": ["docs/user_flow_match_conversation.md#3.3"],
        "goal": "Show peer @username after mutual match.",
        "context": "Link to open Telegram chat.",
        "steps": ["Poll/receive mutual status", "Reveal screen", "Open chat deeplink"],
        "acceptance_criteria": ["Username shown only when mutual"],
        "notes": "", "verification": "Two-account test",
        "slug": "username-reveal-screen",
    },
    {
        "id": "018", "phase": "03-frontend", "title": "Implement aiogram bot /start and profile fallback",
        "priority": "high", "estimated_minutes": 90, "depends_on": ["01-004", "02-006"],
        "spec_refs": ["docs/user_flow_match_conversation.md"],
        "goal": "Bot commands mirror Mini App flow.",
        "context": "Users can use bot without WebApp.",
        "steps": ["/start handler", "Inline keyboard to open Mini App", "Notify on mutual match"],
        "acceptance_criteria": ["/start works", "Notifications sent"],
        "notes": "", "verification": "Bot manual test",
        "slug": "aiogram-bot-start",
    },
    {
        "id": "019", "phase": "03-frontend", "title": "Add error and empty states in UI",
        "priority": "medium", "estimated_minutes": 45, "depends_on": ["03-016"],
        "spec_refs": ["docs/user_flow_match_conversation.md#4"],
        "goal": "Handle no matches, network errors.",
        "context": "UX resilience.",
        "steps": ["Empty state component", "Error toast", "Retry button"],
        "acceptance_criteria": ["No matches message shown", "Retry works"],
        "notes": "", "verification": "Manual",
        "slug": "ui-error-empty-states",
    },
    {
        "id": "020", "phase": "04-integration", "title": "Wire bot notifications for match events",
        "priority": "high", "estimated_minutes": 60, "depends_on": ["02-009", "03-018"],
        "spec_refs": ["docs/user_flow_match_conversation.md#3.3"],
        "goal": "Bot sends accept/reveal notifications.",
        "context": "Bridge API events to Telegram messages.",
        "steps": ["Event handler", "Notification templates", "Deep link to Mini App"],
        "acceptance_criteria": ["Peer notified on accept", "Both notified on mutual"],
        "notes": "", "verification": "Two-user test",
        "slug": "bot-match-notifications",
    },
    {
        "id": "021", "phase": "04-integration", "title": "E2E test mutual match flow",
        "priority": "high", "estimated_minutes": 90, "depends_on": ["03-017", "04-020"],
        "spec_refs": ["docs/SPEC_CANON.md#6"],
        "goal": "Automated or scripted E2E for full flow.",
        "context": "Regression gate before deploy.",
        "steps": ["Script two test users", "Profile → suggest → accept → reveal"],
        "acceptance_criteria": ["Full flow passes"],
        "notes": "", "verification": "CI E2E job",
        "slug": "e2e-mutual-match-flow",
    },
    {
        "id": "022", "phase": "04-integration", "title": "k6 load test 3000 RPS",
        "priority": "high", "estimated_minutes": 120, "depends_on": ["02-008", "02-011"],
        "spec_refs": ["docs/performance_spec.md#4"],
        "goal": "Verify NFR under load.",
        "context": "Must pass before production.",
        "steps": ["k6 scripts", "Run against staging", "Report p95"],
        "acceptance_criteria": ["p95 suggest ≤ 200ms", "error rate < 0.1%"],
        "notes": "", "verification": "k6 report",
        "slug": "k6-load-test",
    },
    {
        "id": "023", "phase": "04-integration", "title": "Deploy staging environment",
        "priority": "medium", "estimated_minutes": 120, "depends_on": ["04-021"],
        "spec_refs": ["docs/deployment_spec.md"],
        "goal": "Staging on cloud with CI deploy.",
        "context": "Mirror production topology.",
        "steps": ["Terraform/k8s manifests", "Secrets config", "Deploy pipeline"],
        "acceptance_criteria": ["Staging URL accessible", "Bot connected"],
        "notes": "", "verification": "Smoke test staging",
        "slug": "deploy-staging",
    },
    {
        "id": "024", "phase": "04-integration", "title": "Set up Prometheus metrics and alerts",
        "priority": "medium", "estimated_minutes": 90, "depends_on": ["02-008"],
        "spec_refs": ["docs/observability_spec.md"],
        "goal": "Metrics and alert rules.",
        "context": "Production readiness.",
        "steps": ["/metrics endpoint", "Prometheus scrape", "Grafana dashboards"],
        "acceptance_criteria": ["Dashboards show latency", "Alerts configured"],
        "notes": "", "verification": "Trigger test alert",
        "slug": "prometheus-metrics-alerts",
    },
    {
        "id": "025", "phase": "05-ml-stub", "title": "Design photo analysis Phase 2 interface",
        "priority": "low", "estimated_minutes": 60, "depends_on": ["02-013"],
        "spec_refs": ["docs/matching_algorithm_spec.md#6"],
        "goal": "Stub interface for future CV worker.",
        "context": "No ML in MVP — interface only.",
        "steps": ["Define PhotoAnalysisJob schema", "Queue message format", "Feature flag"],
        "acceptance_criteria": ["Interface documented", "Flag defaults off"],
        "notes": "Phase 2.", "verification": "Design review",
        "slug": "photo-analysis-phase2-stub",
    },
    {
        "id": "026", "phase": "05-ml-stub", "title": "Implement implicit feedback weight adjustment",
        "priority": "medium", "estimated_minutes": 90, "depends_on": ["02-009"],
        "spec_refs": ["docs/personalization_spec.md#3"],
        "goal": "Accept/decline signals adjust ranking.",
        "context": "Warm personalization MVP.",
        "steps": ["Store feedback events", "Adjust interest weights", "Invalidate cache on signal"],
        "acceptance_criteria": ["Decline lowers similar profiles", "Accept boosts overlap"],
        "notes": "", "verification": "Unit tests",
        "slug": "implicit-feedback-weights",
    },
    {
        "id": "027", "phase": "05-ml-stub", "title": "Add A/B testing feature flag for weights",
        "priority": "low", "estimated_minutes": 60, "depends_on": ["02-007"],
        "spec_refs": ["docs/matching_algorithm_spec.md#2.2"],
        "goal": "matching_weights_variant flag.",
        "context": "Safe experimentation.",
        "steps": ["Flag in config", "Assign variant on register", "Log variant in metrics"],
        "acceptance_criteria": ["Users split by variant", "Metrics tagged"],
        "notes": "", "verification": "Config test",
        "slug": "ab-testing-weights-flag",
    },
    {
        "id": "028", "phase": "06-docs", "title": "Write README and local dev guide",
        "priority": "medium", "estimated_minutes": 45, "depends_on": ["01-001"],
        "spec_refs": ["docs/SPEC_CANON.md"],
        "goal": "Developer onboarding doc.",
        "context": "Replace broken TASK_ROADMAP links.",
        "steps": ["README with make targets", "Env vars list", "Telegram bot setup"],
        "acceptance_criteria": ["New dev can run locally in <30min"],
        "notes": "", "verification": "Fresh clone test",
        "slug": "readme-dev-guide",
    },
    {
        "id": "029", "phase": "06-docs", "title": "Document block and report flow",
        "priority": "medium", "estimated_minutes": 45, "depends_on": ["02-009"],
        "spec_refs": ["docs/risk_register.md#R3"],
        "goal": "User safety: block/report API + bot command.",
        "context": "Mitigate fake profiles.",
        "steps": ["POST /users/{id}/block", "POST /users/{id}/report", "Bot /report command"],
        "acceptance_criteria": ["Blocked user hidden", "Report stored"],
        "notes": "", "verification": "API tests",
        "slug": "block-report-flow",
    },
    {
        "id": "030", "phase": "06-docs", "title": "GDPR account deletion job",
        "priority": "medium", "estimated_minutes": 60, "depends_on": ["02-006"],
        "spec_refs": ["docs/security_spec.md#5"],
        "goal": "Async hard delete within 30 days.",
        "context": "DELETE /users/me triggers job.",
        "steps": ["Deletion queue", "Cascade matches", "Remove S3 photos"],
        "acceptance_criteria": ["PII removed", "Audit retained anonymized"],
        "notes": "", "verification": "Integration test",
        "slug": "gdpr-deletion-job",
    },
]


def rebuild_tasks() -> None:
    if TASKS_DIR.exists():
        shutil.rmtree(TASKS_DIR)
    TASKS_DIR.mkdir(parents=True)

    for task in TASK_DEFINITIONS:
        phase = task["phase"]
        task_id = task["id"]
        slug = task["slug"]
        path = TASKS_DIR / f"phase-{phase}" / f"{task_id}-{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        depends = ", ".join(f'"{d}"' for d in task.get("depends_on", []))
        spec_refs = "\n".join(f'  - "{r}"' for r in task.get("spec_refs", []))
        steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(task.get("steps", [])))
        criteria = "\n".join(f"- [ ] {c}" for c in task.get("acceptance_criteria", []))
        content = f"""---
id: "{task_id}"
phase: "{phase}"
title: "{task['title']}"
priority: {task.get('priority', 'medium')}
estimated_minutes: {task.get('estimated_minutes', 30)}
depends_on: [{depends}]
spec_refs:
{spec_refs}
status: todo
---

## Goal

{task.get('goal', '')}

## Context

{task.get('context', '')}

## Steps

{steps}

## Acceptance Criteria

{criteria}

## Notes / Pitfalls

{task.get('notes', 'N/A')}

## Verification

{task.get('verification', 'Manual review.')}
"""
        path.write_text(content, encoding="utf-8")

    # TASK_INDEX
    lines = ["# Task Index\n", f"Total tasks: {len(TASK_DEFINITIONS)}\n\n"]
    phases: dict[str, list] = {}
    for t in TASK_DEFINITIONS:
        phases.setdefault(t["phase"], []).append(t)
    for phase in sorted(phases):
        lines.append(f"## Phase {phase}\n\n")
        for t in phases[phase]:
            rel = f"phase-{phase}/{t['id']}-{t['slug']}.md"
            lines.append(f"- [{t['id']} {t['title']}](../tasks/{rel})\n")
        lines.append("\n")
    (TASKS_DIR / "TASK_INDEX.md").write_text("".join(lines), encoding="utf-8")

    # _tasks.json
    json_tasks = []
    for t in TASK_DEFINITIONS:
        json_tasks.append({k: v for k, v in t.items() if k != "slug"})
    (TASKS_DIR / "_tasks.json").write_text(
        json.dumps(json_tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"rebuilt {len(TASK_DEFINITIONS)} tasks")


def task_roadmap() -> str:
    lines = [
        "# Implementation Roadmap\n\n",
        "Сжатый roadmap после repair. Канон: `docs/SPEC_CANON.md`.\n\n",
    ]
    phases = {
        "01-foundation": "Foundation",
        "02-backend": "Backend",
        "03-frontend": "Bot + Mini App",
        "04-integration": "Integration & Deploy",
        "05-ml-stub": "Personalization / ML stub",
        "06-docs": "Safety & Compliance",
    }
    by_phase: dict[str, list] = {}
    for t in TASK_DEFINITIONS:
        by_phase.setdefault(t["phase"], []).append(t)
    for phase, title in phases.items():
        items = by_phase.get(phase, [])
        if not items:
            continue
        lines.append(f"## {title}\n\n")
        for t in items:
            rel = f"../tasks/phase-{phase}/{t['id']}-{t['slug']}.md"
            lines.append(f"- [{t['title']}]({rel})\n")
        lines.append("\n")
    return "".join(lines)


def main() -> None:
    write("docs/SPEC_CANON.md", SPEC_CANON)
    write("docs/matching_algorithm_spec.md", MATCHING_SPEC)
    write("docs/user_profile_schema.md", USER_PROFILE)
    write("docs/api_endpoint_design.md", API_SPEC)
    write("docs/user_flow_match_conversation.md", USER_FLOW)
    write("docs/security_spec.md", SECURITY_SPEC)
    write("docs/performance_spec.md", PERFORMANCE_SPEC)
    write("docs/personalization_spec.md", PERSONALIZATION_SPEC)
    write("docs/deployment_spec.md", DEPLOYMENT_SPEC)
    write("docs/observability_spec.md", OBSERVABILITY_SPEC)
    write("docs/risk_register.md", RISK_REGISTER)
    write("docs/project_summary.md", PROJECT_SUMMARY)
    write("docs/generic_spec.md", GENERIC_SPEC)
    write("gaps.md", GAPS_MD)
    write("docs/TASK_ROADMAP.md", task_roadmap())

    # Minimal webapp/ui wireframes pointers
    write(
        "docs/webapp_telegram_design.md",
        """# WebApp Telegram Design

**Artifact Key:** webapp_telegram_design
**Version:** 1.1 (repair)
**Canonical reference:** `SPEC_CANON.md`

## Screens

1. **Onboarding** — age, location, interests, goal (tasks 015)
2. **Matches** — list of cards, accept/decline (task 016)
3. **Reveal** — peer @username + open chat (task 017)

## Tech

React + Telegram WebApp SDK. Auth via initData header on all API calls.

## Out of scope

Swipe gestures, in-app chat, admin panel.
""",
    )
    write(
        "docs/ui_wireframes_telegram.md",
        """# UI Wireframes — Telegram Bot & Mini App

**Artifact Key:** ui_wireframes_telegram
**Version:** 1.1 (repair)

## Bot

- `/start` → welcome + button «Открыть приложение»
- Push: «У вас новый match!» → deep link
- Push: «Взаимный match! @username»

## Mini App

```
[Profile wizard] → [Match list] → [Match detail] → [Username reveal]
```

Match card: photo, name, age, distance, 3 interests, score %, [Принять] [Пропустить]

No swipe UI in MVP.
""",
    )

    rebuild_tasks()

    manifest_path = ROOT / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assumptions"] = [
            "MVP: photo analysis disabled (Phase 2)",
            "No third-party geo APIs — Haversine only",
            "Conversation = mutual Telegram username exchange only",
        ]
        manifest["decisions"] = [
            "D1: UUID + telegram_id",
            "D2: PostgreSQL + Redis",
            "D3: FastAPI + aiogram + React Mini App",
            "D4: MVP matching weights 35/45/20",
        ]
        manifest["gaps_file"] = "gaps.md"
        manifest["tasks"] = {"count": len(TASK_DEFINITIONS), "phases": 6}
        manifest["repair"] = {
            "version": "1.1",
            "tasks_before": 113,
            "tasks_after": len(TASK_DEFINITIONS),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print("updated manifest.json")

    print("repair complete")


if __name__ == "__main__":
    main()
