# Модуль 29: Итоговый проект (Capstone)

> Комплексный практический модуль: асинхронный сервис на FastAPI, интегрирующий темы курса (asyncio, ООП, миксины, slots, магические методы, типизация, тестирование). Чек-лист сдачи и рубрика оценивания.

## Метаданные

| Параметр | Значение |
|----------|----------|
| Номер модуля | 17 |
| Название | Итоговый проект (Capstone) |
| Предварительные знания | Все модули 01–16 |
| Следующий модуль | — (завершение курса) |
| Ориентировочное время | 12–20 часов |
| Версия Python | 3.11+ |
| Сложность | Продвинутая |

## Цели обучения

После прохождения модуля студент сможет:

1. Спроектировать и реализовать **асинхронный REST API** на FastAPI.
2. Интегрировать в одном проекте: **async I/O**, **ООП**, **миксины**, **`__slots__`**, **магические методы**, **typing**.
3. Написать **unit- и integration-тесты** с `pytest` и `httpx.AsyncClient`.
4. Применить **паттерны** курса (Repository, dependency injection) на практике.
5. Оценить **trade-offs** (память vs гибкость, sync vs async) в реальном коде.
6. Сдать проект по **чек-листу** и **рубрике** самостоятельной проверки.

## Теория

### 17.1. Описание capstone-проекта: TaskTracker API

Вы создаёте **TaskTracker** — микросервис учёта задач с REST API.

**Функциональные требования:**

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Проверка живости сервиса |
| `/tasks` | GET | Список задач (фильтр `?status=`) |
| `/tasks` | POST | Создание задачи |
| `/tasks/{id}` | GET | Получение задачи по ID |
| `/tasks/{id}` | PATCH | Обновление статуса/заголовка |
| `/tasks/{id}` | DELETE | Удаление задачи |

**Нефункциональные требования:**

- Python 3.11+, FastAPI, uvicorn
- Асинхронное хранилище in-memory (с имитацией I/O через `asyncio.sleep`)
- Структурированное логирование через `LoggerMixin`
- Модель `Task` со `__slots__` (или `@dataclass(slots=True)`)
- Корректные `__repr__`, `__eq__` у доменных типов
- Типизация: `TypeVar`, `Protocol` для репозитория
- Тесты: минимум 80% покрытия `app/` (опционально, но рекомендуется)

### 17.2. Архитектура проекта

```
tasktracker/
├── pyproject.toml
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan
│   ├── config.py            # Settings (pydantic-settings)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py        # Task, TaskStatus
│   │   └── exceptions.py    # TaskNotFoundError
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── protocol.py      # TaskRepository Protocol
│   │   └── memory.py        # InMemoryTaskRepository
│   ├── services/
│   │   ├── __init__.py
│   │   └── task_service.py  # TaskService + LoggerMixin
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py            # DI: get_repository, get_service
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   └── tasks.py
│   │   └── schemas.py         # Pydantic request/response
│   └── middleware/
│       └── logging.py
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_repository.py
    ├── test_service.py
    └── test_api.py
```

### 17.3. Интеграция тем курса

| Модуль курса | Где применяется в проекте |
|--------------|---------------------------|
| 01 GIL | Понимание: CPU-bound не в async handler |
| 02–03 asyncio | `async def` routes, `await repo.save()` |
| 04 ООП | `Task`, `TaskService`, инкапсуляция |
| 05 Уязвимости | Валидация входа, не доверять `id` клиента |
| 06 TypeVar | `Repository[T]`, generic helpers |
| 07 Protocols | `TaskRepository` Protocol |
| 08 Паттерны | Repository, DI через FastAPI Depends |
| 09 Big O | O(1) lookup по id в dict-репозитории |
| 10–11 stdlib / структуры | `datetime`, `enum`, `uuid` |
| 12 Инженерное мышление | Trade-offs, чек-лист, rubric |
| 13 MRO / super | Кооперативные миксины в сервисе |
| 14 Mixins | `LoggerMixin` в `TaskService` |
| 15 slots | `Task` — экономия при большом числе задач |
| 16 Magic methods | `__repr__`, `__eq__`, context manager для тестов |

### 17.4. Доменная модель Task

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

@dataclass(slots=True)
class Task:
    title: str
    status: TaskStatus = TaskStatus.TODO
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")

    def __repr__(self) -> str:
        return f"Task(id={self.id!s}, title={self.title!r}, status={self.status!r})"

    def mark_done(self) -> None:
        self.status = TaskStatus.DONE
        self.updated_at = datetime.now(timezone.utc)
```

### 17.5. Protocol репозитория

```python
from typing import Protocol
from uuid import UUID

class TaskRepository(Protocol):
    async def get(self, task_id: UUID) -> Task | None: ...
    async def list(self, status: TaskStatus | None = None) -> list[Task]: ...
    async def add(self, task: Task) -> Task: ...
    async def update(self, task: Task) -> Task: ...
    async def delete(self, task_id: UUID) -> bool: ...
```

### 17.6. In-memory репозиторий с async I/O

```python
import asyncio
from uuid import UUID

class InMemoryTaskRepository:
    def __init__(self, latency_ms: float = 5.0) -> None:
        self._store: dict[UUID, Task] = {}
        self._latency = latency_ms / 1000

    async def _simulate_io(self) -> None:
        await asyncio.sleep(self._latency)

    async def get(self, task_id: UUID) -> Task | None:
        await self._simulate_io()
        return self._store.get(task_id)

    async def list(self, status: TaskStatus | None = None) -> list[Task]:
        await self._simulate_io()
        tasks = list(self._store.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    async def add(self, task: Task) -> Task:
        await self._simulate_io()
        self._store[task.id] = task
        return task

    async def update(self, task: Task) -> Task:
        await self._simulate_io()
        if task.id not in self._store:
            raise KeyError(task.id)
        self._store[task.id] = task
        return task

    async def delete(self, task_id: UUID) -> bool:
        await self._simulate_io()
        return self._store.pop(task_id, None) is not None
```

### 17.7. Сервис с LoggerMixin

```python
class TaskService(LoggerMixin):
    _log_namespace = "tasktracker"

    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    async def create_task(self, title: str) -> Task:
        task = Task(title=title)
        self.log_info("creating task", title=title)
        return await self._repo.add(task)

    async def get_task(self, task_id: UUID) -> Task:
        task = await self._repo.get(task_id)
        if task is None:
            self.log_error("task not found", task_id=str(task_id))
            raise TaskNotFoundError(task_id)
        return task

    async def complete_task(self, task_id: UUID) -> Task:
        task = await self.get_task(task_id)
        task.mark_done()
        self.log_info("task completed", task_id=str(task_id))
        return await self._repo.update(task)
```

### 17.8. FastAPI routes и DI

```python
from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    task = await service.create_task(body.title)
    return TaskResponse.from_domain(task)

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    try:
        task = await service.get_task(task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_domain(task)
```

### 17.9. Тестирование async API

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_and_get_task(client):
    r = await client.post("/tasks", json={"title": "Learn MRO"})
    assert r.status_code == 201
    task_id = r.json()["id"]

    r2 = await client.get(f"/tasks/{task_id}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Learn MRO"
```

### 17.10. Lifespan и graceful startup

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init repo, logging
    app.state.repo = InMemoryTaskRepository()
    yield
    # shutdown: cleanup
    app.state.repo = None

app = FastAPI(title="TaskTracker", lifespan=lifespan)
```

## Примеры кода

### Пример 1. Pydantic schemas

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

class TaskResponse(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, task: Task) -> "TaskResponse":
        return cls(
            id=task.id,
            title=task.title,
            status=task.status.value,
            created_at=task.created_at,
        )
```

### Пример 2. Middleware логирования запросов

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        # log request.method, request.url.path, elapsed
        return response
```

### Пример 3. Context manager для тестовой БД

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def isolated_repo():
    repo = InMemoryTaskRepository(latency_ms=0)
    yield repo
    # cleanup automatic
```

## Trade-off: компромиссы в capstone

| Решение | Плюсы | Минусы | В проекте |
|---------|-------|--------|-----------|
| In-memory repo | Простота, скорость разработки | Нет персистентности | MVP capstone |
| PostgreSQL + asyncpg | Production-ready | Сложнее setup | Расширение |
| `@dataclass(slots=True)` | Меньше RAM для Task | Жёсткая схема | Рекомендуется |
| LoggerMixin | DRY логирование | Скрытая зависимость | TaskService |
| sync def routes | Проще | Блокирует event loop | Запрещено в capstone |
| Pydantic v2 | Валидация, OpenAPI | Зависимость | Обязательно |

## Практические задания

### Задание 1 (базовое). MVP endpoints

Реализуйте `/health`, `POST /tasks`, `GET /tasks/{id}` с in-memory хранилищем.

**Критерии:** 201 на create, 404 на unknown id, JSON schema валиден.

### Задание 2 (среднее). Полный CRUD + фильтрация

Добавьте `GET /tasks?status=`, `PATCH /tasks/{id}`, `DELETE /tasks/{id}`.

Интегрируйте `LoggerMixin`, `Task` со slots, Protocol репозитория.

**Критерии:** фильтрация работает, логи при create/delete, typing без `Any` в публичном API.

### Задание 3 (продвинутое). Полный capstone

Реализуйте проект по структуре из §17.2:

- Минимум 10 тестов (`pytest-asyncio`)
- `pyproject.toml` с зависимостями
- README с инструкцией запуска
- Обработка ошибок: 422 validation, 404 not found
- Опционально: Docker, CI GitHub Actions

## Чек-лист сдачи проекта

Перед отправкой на проверку убедитесь:

### Структура и запуск

- [ ] Python 3.11+ указан в `pyproject.toml` или `.python-version`
- [ ] `uvicorn app.main:app --reload` запускает сервис без ошибок
- [ ] `/docs` (Swagger UI) открывается и отражает все endpoints
- [ ] Зависимости зафиксированы (`uv lock` / `requirements.txt`)

### Код и архитектура

- [ ] Разделение: `domain` / `repositories` / `services` / `api`
- [ ] `TaskRepository` объявлен как `Protocol`
- [ ] `TaskService` использует `LoggerMixin`
- [ ] `Task` использует `slots` (dataclass или ручной)
- [ ] Реализованы `__repr__` и корректное сравнение там, где нужно
- [ ] Все route handlers — `async def`
- [ ] Нет блокирующих вызовов (`time.sleep`, sync `requests`) в async коде

### API

- [ ] `GET /health` → `{"status": "ok"}`
- [ ] CRUD `/tasks` работает по спецификации
- [ ] Валидация: пустой `title` → 422
- [ ] Несуществующий `task_id` → 404
- [ ] UUID в path корректно парсится

### Тесты

- [ ] `pytest` проходит зелёным
- [ ] Есть тесты API через `httpx.AsyncClient`
- [ ] Есть тесты доменной логики (`Task.mark_done`)
- [ ] Есть тест «not found» и validation error

### Качество

- [ ] `ruff check` / `mypy` без критичных ошибок (если настроены)
- [ ] Нет захардкоженных секретов
- [ ] README: как установить, запустить, протестировать

### Документация

- [ ] Краткое описание архитектуры в README
- [ ] Указано, какие темы курса применены (таблица из §17.3)

## Рубрика оценивания (100 баллов)

| Критерий | Баллы | Описание |
|----------|-------|----------|
| **Функциональность API** | 25 | Все endpoints по спецификации, корректные коды ответов |
| **Архитектура** | 20 | Слои, DI, Protocol, отсутствие god-objects |
| **Интеграция тем курса** | 20 | slots, mixin, magic methods, asyncio, typing |
| **Тесты** | 20 | Покрытие, async tests, edge cases |
| **Качество кода** | 10 | Читаемость, typing, обработка ошибок |
| **Документация** | 5 | README, комментарии где нужно |

### Шкала итоговой оценки

| Баллы | Оценка | Комментарий |
|-------|--------|-------------|
| 90–100 | Отлично | Production-ready prototype |
| 75–89 | Хорошо | Работает, мелкие замечания |
| 60–74 | Удовлетворительно | MVP есть, нужны доработки |
| < 60 | Нужна пересдача | Критичные пробелы |

### Детализация по интеграции тем (20 баллов)

| Тема | Баллы | Как проверить |
|------|-------|---------------|
| asyncio / async repo | 5 | `await` в repo, нет blocking I/O |
| LoggerMixin | 3 | Наследование, логи в service |
| slots / dataclass | 3 | `Task` compact, `__post_init__` validation |
| `__repr__` / `__eq__` | 3 | Тесты models, отладочный вывод |
| Protocol + TypeVar | 3 | `TaskRepository` Protocol, generic typing |
| MRO / super (если есть иерархия) | 3 | Кооперативный init в mixins |

## Эталонные решения

<details>
<summary>Задание 1 — ключевые фрагменты</summary>

```python
# app/main.py
from fastapi import FastAPI
from app.api.routes import health, tasks

app = FastAPI()
app.include_router(health.router)
app.include_router(tasks.router)

# app/api/routes/health.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}
```

</details>

<details>
<summary>Задание 2 — PATCH endpoint</summary>

```python
class TaskPatch(BaseModel):
    title: str | None = None
    status: TaskStatus | None = None

@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: UUID,
    body: TaskPatch,
    service: TaskService = Depends(get_task_service),
):
    task = await service.get_task(task_id)
    if body.title is not None:
        task.title = body.title
    if body.status is not None:
        task.status = body.status
    task.updated_at = datetime.now(timezone.utc)
    updated = await service._repo.update(task)
    return TaskResponse.from_domain(updated)
```

</details>

<details>
<summary>Задание 3 — conftest.py</summary>

```python
import pytest
from app.repositories.memory import InMemoryTaskRepository
from app.services.task_service import TaskService
from app.main import app
from httpx import ASGITransport, AsyncClient

@pytest.fixture
def repo():
    return InMemoryTaskRepository(latency_ms=0)

@pytest.fixture
def service(repo):
    return TaskService(repo)

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

</details>

## Вопросы для самопроверки

1. Почему в capstone все handlers должны быть `async`?
2. Где в проекте применяется Protocol вместо ABC?
3. Зачем `asyncio.sleep` в in-memory репозитории?
4. Как `LoggerMixin` интегрируется без нарушения MRO?
5. Почему `Task` лучше сделать со `slots`?
6. Какой HTTP-код вернуть при пустом `title`?
7. Чем `lifespan` отличается от `@app.on_event("startup")`?
8. Как протестировать 404 без реального сервера?

<details>
<summary>Ответы</summary>

1. Чтобы не блокировать event loop при await repo (имитация I/O).
2. `TaskRepository` Protocol — structural subtyping для repo.
3. Имитация latency реальной БД; учит правильному async-стилю.
4. Кооперативный `super().__init__` если миксин в цепочке init.
5. При большом числе задач экономия памяти; фиксированная схема.
6. 422 Unprocessable Entity (Pydantic validation).
7. `lifespan` — современный способ (FastAPI 0.93+), context manager.
8. `httpx.AsyncClient` + `ASGITransport(app=app)`.

</details>

## Методические указания для преподавателя

### Организация capstone

| Неделя | Фокус |
|--------|-------|
| 1 | Домен, repo, unit-тесты |
| 2 | FastAPI routes, integration tests |
| 3 | Mixins, slots, polish, README |
| 4 | Code review, пересдачи |

### Code review — на что смотреть

1. Блокирующий I/O в async — **критичный дефект**.
2. God service на 500 строк — предложить разбиение.
3. Отсутствие 404 handling — доработать.
4. Копипаста schemas/domain — DRY через `from_domain`.

### Расширения для сильных студентов

- Персистентность: SQLite + `aiosqlite`
- Auth: API key middleware
- Rate limiting middleware
- Метрики Prometheus
- `__aiter__` для streaming `/tasks/stream`

## Дополнительные материалы

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [httpx AsyncClient testing](https://www.python-httpx.org/async/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Starlette lifespan](https://www.starlette.io/lifespan/)
- Пример эталонного repo: поиск `fastapi clean architecture` на GitHub для сравнения

## Завершение курса

Поздравляем с прохождением курса «Продвинутый Python»! Вы изучили:

- Конкурентность: GIL, async, asyncio
- Типизацию и протоколы
- Продвинутое ООП: MRO, миксины, slots, dunder methods
- Инженерные практики: паттерны, Big O, тестирование
- Итоговую интеграцию в реальном async-сервисе

**Следующие шаги:** PostgreSQL + SQLAlchemy 2.0 async, Celery/ARQ для фоновых задач, observability (OpenTelemetry), деплой в Kubernetes.
