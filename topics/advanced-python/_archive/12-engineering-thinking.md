# Модуль 12: Инженерное мышление в Python

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 12 из 12 (финальный) |
| Предварительные знания | Модули 9–11; опыт написания скриптов и функций; базовое знакомство с `pytest` или `unittest` |
| Следующий модуль | — (интеграционный проект / capstone по желанию курса) |
| Ориентировочное время | 5–7 часов |
| Версия Python | 3.11+ |
| Ключевые темы | декомпозиция, цикл TDD, читаемость vs производительность, design checklist |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Декомпозировать** задачу на тестируемые, слабо связанные компоненты с явными контрактами.
2. **Применять** цикл TDD (Test-Driven Development) на практике: red → green → refactor.
3. **Балансировать** читаемость и производительность, опираясь на измерения (модуль 9), а не интуицию.
4. **Использовать** design checklist перед написанием и при code review.
5. **Формулировать** trade-offs и документировать архитектурные решения для команды.
6. **Интегрировать** знания курса (Big O, stdlib, структуры данных) в целостный инженерный процесс.

---

## Теория

### 12.1 Что такое инженерное мышление

**Инженерное мышление** — это не «писать больше кода», а **систематически** принимать решения под ограничения:

- **Корректность** — программа делает то, что нужно, включая edge cases.
- **Поддерживаемость** — другой разработчик поймёт код через 6 месяцев.
- **Изменяемость** — новые требования не ломают всё приложение.
- **Наблюдаемость** — можно понять, что происходит в production.
- **Эффективность** — достаточная производительность без преждевременной оптимизации.

Python благодаря выразительности провоцирует быстрые прототипы. Задача инженера — **не застрять в прототипе**, а довести решение до уровня, пригодного для команды и production.

### 12.2 Декомпозиция (decomposition)

#### Принцип единственной ответственности (SRP)

Каждый модуль/функция/класс должен иметь **одну причину для изменения**.

Плохо:
```python
def process_order(order: dict) -> None:
    # валидация + расчёт скидки + запись в БД + отправка email + логирование
    ...
```

Лучше:
```python
def validate_order(order: Order) -> None: ...
def calculate_total(order: Order, rules: PricingRules) -> Money: ...
def persist_order(repo: OrderRepository, order: Order) -> None: ...
def notify_customer(mail: Mailer, order: Order) -> None: ...
```

#### Уровни декомпозиции

```text
Задача бизнеса
  └── Use cases / сервисы (оркестрация)
        └── Доменная логика (чистые функции, модели)
              └── Инфраструктура (I/O, БД, HTTP, subprocess)
```

**Чистая доменная логика** не импортирует `requests`, `sqlalchemy`, `pathlib` — только типы и стандартные структуры. Это упрощает тесты.

#### Критерии хорошей декомпозиции

1. **Имя отражает намерение**, не реализацию (`parse_iso_date`, не `step3`).
2. **Функция помещается на экран** (~20–40 строк как ориентир, не догма).
3. **Входы и выходы явные** — минимум скрытого состояния и global mutable state.
4. **Зависимости инжектируются** (параметры, протоколы), а не создаются внутри.
5. **Границы ошибок ясны** — что бросает исключение, что возвращает `Result`.

#### Пример: декомпозиция CLI-пайплайна (связь с модулем 10)

```text
main()
  ├── parse_args()          # argparse
  ├── setup_logging()       # logging
  ├── load_config()         # env / file
  ├── run_pipeline(cfg)     # бизнес-оркестрация
  │     ├── read_input()
  │     ├── transform()
  │     └── write_output()
  └── sys.exit(code)
```

Каждый уровень тестируется отдельно: `transform` — unit tests без файловой системы.

#### Антипаттерны декомпозиции

- **Shotgun surgery** — одно изменение требует правок в 15 файлах (слишком дробно или неправильные границы).
- **God object** — один класс «знает всё».
- **Primitive obsession** — везде `dict[str, Any]` вместо типизированных моделей (модуль 11: `dataclass`).

### 12.3 TDD — Test-Driven Development

#### Цикл Red → Green → Refactor

1. **Red:** напишите **падающий** тест, описывающий желаемое поведение.
2. **Green:** минимальный код, чтобы тест прошёл.
3. **Refactor:** улучшите структуру без изменения поведения (тесты зелёные).

```text
        ┌──────────┐
        │   RED    │  тест падает — поведение не реализовано
        └────┬─────┘
             ▼
        ┌──────────┐
        │  GREEN   │  минимальная реализация
        └────┬─────┘
             ▼
        ┌──────────┐
        │ REFACTOR │  декомпозиция, имена, удаление дублирования
        └────┬─────┘
             │
             └────► следующий тест
```

#### Что тестировать в Python-проекте

| Слой | Инструмент | Примеры |
|------|------------|---------|
| Чистые функции | `pytest` unit | парсинг, расчёты, валидация |
| Классы/сервисы | unit + mocks | repository с fake in-memory |
| CLI | `subprocess` / `pytest` capsys | exit codes, --help |
| I/O интеграция | integration tests | tmp_path, testcontainers |

#### Структура теста (Arrange – Act – Assert)

```python
def test_calculate_discount_premium_user():
    # Arrange
    user = User(tier="premium")
    order = Order(amount=1000)

    # Act
    total = calculate_total(order, user)

    # Assert
    assert total == 900  # 10% скидка
```

#### TDD в Python 3.11+ с pytest

```python
# test_pricing.py
import pytest
from pricing import calculate_discount


def test_no_discount_for_standard():
    assert calculate_discount(amount=100, tier="standard") == 100


def test_premium_ten_percent():
    assert calculate_discount(amount=100, tier="premium") == 90


@pytest.mark.parametrize("amount,tier,expected", [
    (0, "premium", 0),
    (50, "unknown", 50),
])
def test_edge_cases(amount, tier, expected):
    assert calculate_discount(amount=amount, tier=tier) == expected
```

Запуск: `python -m pytest test_pricing.py -v`

#### Когда TDD особенно полезен

- Алгоритмы с edge cases (модуль 11: booking, sliding window).
- Регрессии в legacy-коде.
- API контракты между командами.

#### Когда TDD избыточен

- Одноразовые скрипты анализа данных.
- UI-прототипы без стабильных требований.
- Исследование неизвестного API (spike → затем тесты).

**Позиция курса:** TDD — навык, а не религия. Начинайте с тестов на **критическую** логику.

### 12.4 Читаемость vs производительность

#### Закон Дональда Кнута (адаптация)

> «Преждевременная оптимизация — корень всех зол».

Сначала **корректность и ясность**, затем **профилирование** (модуль 9: `cProfile`, `timeit`), затем **точечная** оптимизация.

#### Спектр решений

```text
Читаемость ◄────────────────────────────► Производительность
   чистый Python          NumPy/Cython          C/Rust extension
   dict/list              deque/heapq            custom memory layout
```

#### Практические правила

1. **Измеряйте hot path** — 90% времени часто в 10% кода.
2. **Оптимизируйте алгоритм раньше микрохаков** — O(n²) → O(n) важнее, чем замена `for` на `while`.
3. **Сохраняйте читаемую версию** в комментарии или git history — не «умный» однострочник без контекста.
4. **Документируйте «почему»** если жертвуете читаемостью:

```python
# bisect + sorted intervals: O(log n) book lookup при 100k броней (см. модуль 11)
```

5. **Type hints и dataclass** улучшают читаемость почти бесплатно в 3.11+.

#### Пример trade-off

```python
# Читаемо: O(n*m)
def count_common_naive(a: list[str], b: list[str]) -> int:
    return sum(1 for x in a if x in b)


# Быстрее на больших n: O(n+m)
def count_common_fast(a: list[str], b: list[str]) -> int:
    bs = set(b)
    return sum(1 for x in a if x in bs)
```

Для `len(a) < 50` разница незаметна — **не усложняйте** без данных.

#### Readability checklist

- Имена переменных отражают домен (`booking`, не `b`).
- Функции — глаголы (`parse_config`), классы — существительные (`BookingSystem`).
- Магические числа вынесены в константы.
- Вложенность ≤ 3 уровней — ранний return / extract function.
- Docstring на публичном API — **что** и **исключения**, не пересказ кода.

### 12.5 Design checklist — чеклист проектирования

Используйте перед реализацией нетривиальной фичи и при code review.

#### A. Понимание задачи

- [ ] Какова **формулировка проблемы** одним предложением?
- [ ] Кто **потребитель** результата (пользователь, другой сервис, batch job)?
- [ ] Какие **ограничения**: время отклика, объём данных, память, offline/online?
- [ ] Что **вне scope** явно исключено?

#### B. Данные и контракты

- [ ] Какие **входы/выходы** (типы, форматы, коды ошибок)?
- [ ] Какие **инварианты** (например, `start < end`)?
- [ ] Какие **edge cases**: пустой ввод, дубликаты, None, граничные значения?
- [ ] Нужны ли **immutable** модели (`frozen dataclass`)?

#### C. Архитектура и декомпозиция

- [ ] Где **чистая логика** vs **I/O**?
- [ ] Можно ли протестировать ядро **без сети и диска**?
- [ ] Какие **зависимости** инжектируются?
- [ ] Есть ли **дублирование**, которое стоит обобщить (но не раньше времени — Rule of Three)?

#### D. Алгоритмы и структуры (модули 9, 11)

- [ ] Какая **асимптотика** критичных операций?
- [ ] Выбрана ли правильная структура (`set` vs `list`, `heapq`, `deque`)?
- [ ] Нужен ли **кэш** (`lru_cache`, dict)?

#### E. Надёжность и эксплуатация (модуль 10)

- [ ] **Логирование** на границах (старт/ошибка/результат)?
- [ ] **Exit codes** для CLI?
- [ ] Таймауты на **subprocess** и внешние API?
- [ ] Секреты только из **env**, не из кода?

#### F. Тестирование

- [ ] Есть ли тест на **happy path**?
- [ ] Покрыты ли **граничные** случаи?
- [ ] Регрессионный тест на **найденный баг**?
- [ ] CI запускает `pytest` на каждый push?

#### G. Документация и передача

- [ ] README или docstring объясняет **как запустить**?
- [ ] Зафиксированы **trade-offs** в PR description?
- [ ] Для нетривиальных решений — **ADR** (Architecture Decision Record) в 5–10 строк?

### 12.6 Code review как часть инженерной культуры

**Reviewer смотрит на:**
1. Корректность и тесты
2. Дизайн и границы модулей
3. Безопасность (injection, secrets)
4. Производительность «первого порядка» (очевидный O(n²))
5. Стиль проекта (consistency)

**Автор PR:**
- Маленькие PR (< 400 строк) reviewятся быстрее
- Описание: **что**, **зачем**, **как проверить**
- Self-review diff перед отправкой

### 12.7 Рефакторинг без страха

Условия безопасного рефакторинга:
1. Тесты зелёные до и после
2. Маленькие коммиты
3. Не смешивать рефакторинг и новую фичу в одном PR (по возможности)

**Техники:**
- Extract function / Extract class
- Replace magic number with named constant
- Introduce dataclass вместо tuple из 7 полей
- Replace conditional with polymorphism (когда паттернов станет много)

### 12.8 Интеграция курса: capstone mindset

Финальный мини-проект (рекомендация): **CLI-утилита обработки логов**

| Компонент | Модуль курса |
|-----------|--------------|
| Парсинг, агрегация O(n) | 9, 11 |
| `pathlib`, `argparse`, `logging` | 10 |
| `Counter`, `dataclass` | 11 |
| Декомпозиция, pytest, checklist | 12 |

Это проверяет не синтаксис, а **инженерную зрелость**.

---

## Примеры кода

### Пример 1: Декомпозиция — до и после

```python
# --- До: монолит ---
def handle_user_registration(data: dict) -> dict:
    if "email" not in data or "@" not in data["email"]:
        return {"ok": False, "error": "bad email"}
    email = data["email"].lower().strip()
    if len(data.get("password", "")) < 8:
        return {"ok": False, "error": "weak password"}
    # ... запись в "БД", отправка письма ...
    return {"ok": True, "user_id": 42}


# --- После: слои ---
from dataclasses import dataclass


@dataclass(frozen=True)
class RegistrationRequest:
    email: str
    password: str


@dataclass(frozen=True)
class RegistrationResult:
    ok: bool
    user_id: int | None = None
    error: str | None = None


def validate_request(req: RegistrationRequest) -> str | None:
    if "@" not in req.email:
        return "bad email"
    if len(req.password) < 8:
        return "weak password"
    return None


def normalize_email(email: str) -> str:
    return email.lower().strip()


def register_user(req: RegistrationRequest, repo) -> RegistrationResult:
    err = validate_request(req)
    if err:
        return RegistrationResult(ok=False, error=err)
    user_id = repo.create_user(normalize_email(req.email), req.password)
    return RegistrationResult(ok=True, user_id=user_id)
```

### Пример 2: TDD — пошаговая разработка FizzBuzz

```python
# fizzbuzz.py
def fizzbuzz(n: int) -> str:
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)
```

```python
# test_fizzbuzz.py
import pytest
from fizzbuzz import fizzbuzz


@pytest.mark.parametrize("n,expected", [
    (1, "1"),
    (3, "Fizz"),
    (5, "Buzz"),
    (15, "FizzBuzz"),
])
def test_fizzbuzz(n, expected):
    assert fizzbuzz(n) == expected
```

Демонстрация цикла: сначала тест `(3, "Fizz")` → red → green → refactor (упорядочить проверки).

### Пример 3: Fake repository для unit tests

```python
from dataclasses import dataclass, field


@dataclass
class FakeUserRepo:
    _users: dict[str, int] = field(default_factory=dict)
    _next_id: int = 1

    def create_user(self, email: str, password: str) -> int:
        if email in self._users:
            raise ValueError("exists")
        uid = self._next_id
        self._next_id += 1
        self._users[email] = uid
        return uid


def test_register_success():
    from registration import RegistrationRequest, register_user

    repo = FakeUserRepo()
    result = register_user(
        RegistrationRequest("a@b.com", "password1"),
        repo,
    )
    assert result.ok
    assert result.user_id == 1
```

### Пример 4: Readability vs performance — documented choice

```python
from functools import lru_cache


# Читаемая рекурсия — O(2^n), только для малых n (обучение / n < 30)
def fib_readable(n: int) -> int:
    if n < 2:
        return n
    return fib_readable(n - 1) + fib_readable(n - 2)


# Production: O(n) время, O(1) память
def fib_fast(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# Компромисс: читаемо + кэш для повторных вызовов
@lru_cache(maxsize=None)
def fib_cached(n: int) -> int:
    if n < 2:
        return n
    return fib_cached(n - 1) + fib_cached(n - 2)
```

### Пример 5: Design checklist в действии — rate limiter

```python
"""Простой sliding window rate limiter — демонстрация design decisions."""
from collections import deque
from dataclasses import dataclass, field
from time import monotonic


@dataclass
class RateLimiter:
    max_calls: int
    window_seconds: float
    _timestamps: deque[float] = field(default_factory=deque)

    def allow(self) -> bool:
        now = monotonic()
        while self._timestamps and now - self._timestamps[0] > self.window_seconds:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_calls:
            return False
        self._timestamps.append(now)
        return True
```

**Checklist ответы (кратко):**
- Данные: deque of monotonic timestamps — O(амортизированно) на вызов
- Edge: `max_calls=0` всегда False (можно добавить в `__post_init__`)
- Тест: fake time через injectable `clock` в расширенной версии

### Пример 6: pytest для CLI (capsys)

```python
import backup_cli  # модуль из модуля 10


def test_main_dry_run(capsys, tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "file.txt").write_text("hi", encoding="utf-8")

    code = backup_cli.main([str(src), "--dry-run", "-v"])
    captured = capsys.readouterr()
    assert code == 0
    assert "DRY RUN" in captured.err or "DRY RUN" in captured.out
```

---

## Trade-off: компромиссы

| Подход | Плюсы | Минусы | Когда выбирать |
|--------|-------|--------|----------------|
| Монолитная функция | Быстро написать | Нетестируемо, растёт | Spike, notebook |
| Слоистая декомпозиция | Тесты, ясные границы | Больше файлов | Production, команда |
| Strict TDD | Регрессии, спецификация | Медленнее старт | Критичная логика |
| Тесты после кода | Быстрее прототип | Пропуск edge cases | Прототипы с последующим hardening |
| Читаемый O(n²) | Простота | Не масштабируется | Малые n, редкие вызовы |
| Оптимизированный O(n) | Масштаб | Сложнее, нужны тесты | Hot path, большие данные |
| dataclass DTO | Типы, IDE | Boilerplate | API границы |
| dict[str, Any] | Гибкость | Ошибки в runtime | JSON glue, dynamic config |
| Большой PR | «Всё сразу» | Плохой review | Избегать |
| Малые PR | Быстрый review, откат | Больше координации | Основной режим команды |
| ADR документ | Память решений | Время на запись | Архитектурные развилки |

---

## Практические задания

### Задание 1 (базовое): Декомпозиция монолита

Дан модуль `report_monolith.py` (ниже). Разбейте на минимум 3 функции + 1 dataclass. Сохраните поведение.

```python
def build_report(rows: list[dict]) -> str:
    if not rows:
        return "EMPTY"
    total = 0
    lines = []
    for r in rows:
        if "amount" not in r:
            continue
        try:
            amt = int(r["amount"])
        except (TypeError, ValueError):
            continue
        if amt < 0:
            continue
        total += amt
        lines.append(f"{r.get('name', '?')}: {amt}")
    header = f"TOTAL={total}\n"
    return header + "\n".join(lines)
```

Напишите `test_report.py` с 4 тестами (empty, valid, skip negative, skip bad amount).

---

### Задание 2 (среднее): TDD мини-библиотека

Реализуйте модуль `url_join` функцию `join_url(base: str, *parts: str) -> str` **через TDD**:

Правила:
- Убирает лишние слеши: `join_url("http://a.com/", "/api/", "v1")` → `"http://a.com/api/v1"`
- Пустые `parts` игнорируются
- `base` без завершающего слеша сохраняется как есть до первого part

**Порядок сдачи:** git log или список из 5+ коммитов/шагов red-green-refactor (можно в одном файле с комментариями `# STEP 1 RED`).

Минимум 6 тестов в `test_url_join.py`.

---

### Задание 3 (продвинутое): Design doc + реализация

Спроектируйте и реализуйте **in-memory key-value store с TTL**:

**Требования:**
- `set(key, value, ttl_seconds=None)`
- `get(key) -> value | None` (None если нет или истёк TTL)
- `delete(key) -> bool`
- Декомпозиция: `Clock` protocol, `TTLStore` class, optional CLI (`argparse`) для demo
- Заполните **design checklist** (раздел 12.5) в `DESIGN.md` (1–2 страницы)
- pytest: happy path, expiry, overwrite key
- В `DESIGN.md` — параграф **readability vs performance** (как храните expiry: linear scan vs heap)

---

## Эталонные решения

<details>
<summary>Задание 1 — декомпозиция report</summary>

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SaleRow:
    name: str
    amount: int


def parse_row(raw: dict) -> SaleRow | None:
    if "amount" not in raw:
        return None
    try:
        amt = int(raw["amount"])
    except (TypeError, ValueError):
        return None
    if amt < 0:
        return None
    return SaleRow(name=str(raw.get("name", "?")), amount=amt)


def format_report(rows: list[SaleRow]) -> str:
    total = sum(r.amount for r in rows)
    lines = [f"{r.name}: {r.amount}" for r in rows]
    return f"TOTAL={total}\n" + "\n".join(lines)


def build_report(rows: list[dict]) -> str:
    if not rows:
        return "EMPTY"
    parsed = [r for raw in rows if (r := parse_row(raw)) is not None]
    return format_report(parsed)
```

```python
# test_report.py
from report import build_report


def test_empty():
    assert build_report([]) == "EMPTY"


def test_valid():
    data = [{"name": "A", "amount": 10}, {"name": "B", "amount": 5}]
    out = build_report(data)
    assert "TOTAL=15" in out
    assert "A: 10" in out


def test_skip_negative():
    assert "TOTAL=0" in build_report([{"name": "X", "amount": -1}])


def test_skip_bad():
    assert build_report([{"amount": "x"}]) == "TOTAL=0\n"
```

</details>

<details>
<summary>Задание 2 — join_url (эталон)</summary>

```python
# url_join.py
def join_url(base: str, *parts: str) -> str:
    segments = [base.rstrip("/")]
    for part in parts:
        if not part:
            continue
        segments.append(part.strip("/"))
    return "/".join(segments)
```

```python
# test_url_join.py
import pytest
from url_join import join_url


@pytest.mark.parametrize("base,parts,expected", [
    ("http://a.com", ("api", "v1"), "http://a.com/api/v1"),
    ("http://a.com/", ("/api/", "/v1"), "http://a.com/api/v1"),
    ("http://a.com", (), "http://a.com"),
    ("http://a.com/", ("", "x"), "http://a.com/x"),
])
def test_join(base, parts, expected):
    assert join_url(base, *parts) == expected
```

</details>

<details>
<summary>Задание 3 — TTL store (скелет)</summary>

```python
# ttl_store.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


@dataclass
class _Entry:
    value: object
    expires_at: float | None


class TTLStore:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._data: dict[str, _Entry] = {}

    def set(self, key: str, value: object, ttl_seconds: float | None = None) -> None:
        exp = None
        if ttl_seconds is not None:
            exp = self._clock.monotonic() + ttl_seconds
        self._data[key] = _Entry(value, exp)

    def get(self, key: str) -> object | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and self._clock.monotonic() >= entry.expires_at:
            del self._data[key]
            return None
        return entry.value

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None
```

В `DESIGN.md` студент описывает: lazy expiry при get vs periodic cleanup; для малых store linear scan при get достаточен; при масштабе — heap по `expires_at`.

</details>

---

## Вопросы для самопроверки

1. Назовите три признака того, что функцию пора разбить на несколько.
2. Что означает «red» в цикле TDD?
3. Почему тесты для чистых функций не требуют mock?
4. Когда `lru_cache` улучшает и читаемость, и производительность?
5. Перечислите 5 пунктов из design checklist, которые вы бы не пропустили перед production deploy.
6. Чем integration test отличается от unit test в контексте модуля 10?
7. Почему смешивать рефакторинг и новую фичу в одном PR нежелательно?
8. Что такое SRP и приведите пример нарушения из своего опыта.
9. Как документировать trade-off «выбрали deque вместо list»?
10. Как модули 9–11 поддерживают решения из checklist пункта D?

---

## Методические указания

### Для студента

1. Пройдите checklist **письменно** для задания 3 до кода — это 30% успеха.
2. Практикуйте **маленькие шаги** TDD: один assert за раз.
3. Сравните время разработки с тестами и без на одинаковой задаче — сформируйте личное мнение.
4. Читайте чужой код как reviewer: найдите одно нарушение SRP в open source.
5. Финальный capstone свяжите с вашим стеком (Kafka consumer, ML pipeline, DevOps script).

### Для преподавателя

- **Семинар 1:** разбор монолита (задание 1) на доске — collective refactor.
- **Семинар 2:** ping-pong TDD в парах на `join_url`.
- **Семинар 3:** peer review `DESIGN.md` по рубрике checklist.
- Оценка задания 3: DESIGN 25%, тесты 25%, код 30%, декомпозиция 20%.
- Обсуждение: «TDD в data science?» — тесты на инварианты данных, не на ML accuracy alone.

### Рубрика code review (упрощённая)

| Критерий | 1 | 3 | 5 |
|----------|---|---|---|
| Декомпозиция | God function | Есть слои | Чёткие границы + DI |
| Тесты | Нет | Happy path | Edge + regressions |
| Читаемость | Магия | OK | Имена + типы + doc |
| Performance | Игнор | Big O учтён | Профиль при необходимости |

---

## Дополнительные материалы

### Книги

- Kent Beck, *Test Driven Development: By Example*
- Robert C. Martin, *Clean Code* — главы о функциях и именах
- Sandy Metz, *POODR* — принципы дизайна (актуально даже вне Ruby)

### Python-специфично

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis](https://hypothesis.readthedocs.io/) — property-based testing
- PEP 20 — The Zen of Python

### Architecture

- [Architecture Decision Records](https://adr.github.io/)
- Martin Fowler — Refactoring catalog

### Практика

- [Exercism Python track](https://exercism.org/tracks/python) — маленькие задачи + mentor review
- Рефакторинг собственного скрипта из модуля 10 с полным test suite

### Итог курса «Продвинутый Python»

| Модуль | Навык |
|--------|-------|
| 9 | Оценка и измерение производительности |
| 10 | Системное программирование на Python |
| 11 | Выбор структур данных |
| 12 | Инженерная дисциплина |

**Следующий шаг:** capstone-проект или интеграция в production codebase с наставником. Поздравляем с завершением теоретической части курса.
