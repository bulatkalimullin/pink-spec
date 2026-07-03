# Модуль 11: Обработка исключений

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 11 |
| Предварительные знания | [Модуль 4: ООП](04-oop.md), [Модуль 10: Дата классы](10-dataclasses.md) — валидация в `__post_init__` |
| Предыдущий модуль | [10-dataclasses.md](10-dataclasses.md) |
| Следующий модуль | [12-concurrent-processes.md](12-concurrent-processes.md) |
| Ориентировочное время | 5–6 часов |
| Версия Python | 3.11+ |
| Ключевые темы | `try/except/else/finally`, `raise`, цепочки исключений, иерархия, пользовательские исключения, EAFP vs LBYL, best practices |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Использовать** полную форму `try/except/else/finally` осознанно, понимая порядок выполнения.
2. **Поднимать** исключения через `raise` с сохранением контекста (`raise ... from e`, `raise` без аргументов).
3. **Проектировать** иерархию пользовательских исключений для домена и библиотек.
4. **Различать** EAFP («проще попросить прощения») и LBYL («лучше разрешение») в идиоматичном Python.
5. **Обрабатывать** несколько типов исключений без опасного голого `except:`.
6. **Применять** best practices: узкие `except`, логирование с `exc_info`, не глотать ошибки, `ExceptionGroup` (3.11+).

---

## Теория

### 11.1 Исключение как механизм управления потоком

В Python ошибки времени выполнения передаются через **исключения** (exceptions) — объекты, наследующие `BaseException`. Когда исключение не перехвачено, интерпретатор завершает трассировку stack trace.

**Исключения — не только для «фатальных» сбоев.** Они сигнализируют о нарушении контракта: файл не найден, неверный аргумент, сеть недоступна. В отличие от кодов возврата (C, Go), исключения несут тип и сообщение и **прерывают** нормальный поток до ближайшего подходящего `except`.

**Философия Python (EAFP):** «проще попросить прощения, чем разрешения» — пробуйте операцию и ловите ожидаемое исключение, вместо длинных предварительных проверок.

### 11.2 Базовый синтаксис try/except

```python
try:
    value = int(user_input)
except ValueError:
    print("Введите целое число")
```

- Выполняется блок `try`.
- При исключении типа `ValueError` (или подкласса) выполняется `except`.
- Другие типы **пробрасываются** выше.

**Перехват нескольких типов:**

```python
try:
    process(data)
except (ValueError, TypeError) as exc:
    log.warning("Invalid data: %s", exc)
```

**Порядок `except` важен:** от более специфичных к более общим. `except Exception` перед `except ValueError` сделает вторую ветку недостижимой.

### 11.3 else и finally — полная картина

```python
def read_config(path: str) -> dict:
    handle = None
    try:
        handle = open(path, encoding="utf-8")
        data = handle.read()
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}") from exc
    else:
        # выполняется ТОЛЬКО если try завершился без исключения
        return parse_json(data)
    finally:
        # выполняется ВСЕГДА — при успехе, except, return
        if handle is not None:
            handle.close()
```

| Блок | Когда выполняется |
|------|-------------------|
| `try` | Основная логика |
| `except` | При matching исключении |
| `else` | Если `try` без исключения |
| `finally` | Всегда (cleanup) |

**`else` полезен**, чтобы отделить код, который **не должен** выполняться, если `try` упал (например, парсинг только после успешного чтения).

**`finally`** — освобождение ресурсов. Предпочтительнее **context manager** (`with open(...)`) — он сам вызывает `__exit__` с информацией об исключении.

### 11.4 raise — поднятие исключений

```python
def withdraw(balance: float, amount: float) -> float:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if amount > balance:
        raise InsufficientFundsError(balance, amount)
    return balance - amount
```

**Повторный throw** внутри `except`:

```python
try:
    risky()
except LowLevelError:
    log.exception("failed")
    raise  # тот же экземпляр, сохраняется traceback
```

### 11.5 Цепочки исключений: from и cause

**Явная причина** — `raise NewError("...") from original`:

```python
try:
    raw = open(path).read()
except OSError as exc:
    raise ConfigError("load failed") from exc
```

В traceback: `ConfigError` ← `OSError` (показана **причина**).

**Неявный контекст** при ошибке в `except`:

```python
except ParseError as exc:
    raise ValidationError("bad config")  # implicit __context__
```

**Подавление контекста:** `raise NewError() from None` — скрыть исходное исключение от пользователя (осторожно, теряется диагностика).

### 11.6 Иерархия встроенных исключений (обзор)

```
BaseException
 ├── SystemExit
 ├── KeyboardInterrupt
 ├── GeneratorExit
 └── Exception
      ├── ArithmeticError
      │    ├── ZeroDivisionError
      │    └── ...
      ├── LookupError
      │    ├── KeyError
      │    └── IndexError
      ├── OSError
      │    ├── FileNotFoundError
      │    ├── PermissionError
      │    └── ...
      ├── ValueError
      ├── TypeError
      ├── RuntimeError
      │    └── RecursionError
      └── ...
```

**Правило:** ловите **конкретные** типы. `except Exception` — на границе приложения (middleware, main), не в глубине бизнес-логики.

**Не ловите** `BaseException` (включая `KeyboardInterrupt`, `SystemExit`) без крайней необходимости.

### 11.7 Пользовательские исключения

```python
class AppError(Exception):
    """Базовое исключение приложения."""


class ValidationError(AppError):
    """Невалидные входные данные."""


class NotFoundError(AppError):
    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id!r} not found")
```

**Рекомендации:**

1. Наследуйте от `Exception`, не от `BaseException`.
2. Корень домена — один базовый класс (`AppError`, `ServiceError`).
3. Группируйте по **смыслу**, не по HTTP-коду (код — деталь transport layer).
4. Добавляйте атрибуты для программной обработки (`entity_id`, `field`, `code`).
5. Документируйте в docstring класса и публичных функций, что может быть поднято.

**Анти-паттерн:** 50 пустых классов `class UserNotFound(Exception): pass` без общего предка — трудно ловить `except AppError`.

### 11.8 EAFP vs LBYL

| Подход | Стиль | Пример |
|--------|-------|--------|
| **EAFP** | try/except | `try: d[key]` / `except KeyError` |
| **LBYL** | Look Before You Leap | `if key in d: ...` |

**Python предпочитает EAFP**, когда проверка дорога или гонка возможна:

```python
# EAFP — идиоматично для dict
try:
    return users[user_id]
except KeyError:
    return create_default_user(user_id)

# LBYL — когда KeyError слишком общий или ветка success чаще
if user_id in users:
    return users[user_id]
```

Для **файлов** EAFP естественен (`FileNotFoundError`). Для **валидации API** часто явные проверки читаемее, чем ловить `ValueError` от парсера.

### 11.9 else — зачем не писать код в try

Плохо (парсинг в try смешан с I/O):

```python
try:
    data = json.loads(text)
    validate(data)  # ValidationError маскируется?
except json.JSONDecodeError:
    ...
```

Лучше:

```python
try:
    data = json.loads(text)
except json.JSONDecodeError as exc:
    raise ConfigError("invalid json") from exc
else:
    validate(data)  # ValidationError не перехватывается JSON handler
```

### 11.10 finally, return и подавление исключений

`return` в `try` или `finally` влияет на результат функции. **`return` в `finally` перекрывает** исключение из `try` — анти-паттерн:

```python
def bad():
    try:
        raise ValueError()
    finally:
        return 42  # исключение потеряно!
```

Избегайте `return` в `finally`. Используйте `try/finally` только для cleanup.

### 11.11 Context managers и исключения

```python
with open("data.txt") as f:
    process(f.read())
```

`__exit__(exc_type, exc_val, exc_tb)`:

- возврат `True` — **подавить** исключение (редко нужно);
- `False` / `None` — пробросить дальше.

`contextlib.suppress`:

```python
from contextlib import suppress

with suppress(FileNotFoundError):
    os.remove(temp_path)
```

### 11.12 Логирование исключений

```python
import logging

logger = logging.getLogger(__name__)

try:
    run_job()
except ServiceError:
    logger.exception("Job failed")  # traceback в лог
    raise
```

- `logger.error("msg", exc_info=True)` — эквивалент traceback.
- Не делайте `except Exception: print(e)` без traceback в продакшене.

### 11.13 ExceptionGroup и except* (Python 3.11+, кратко)

При параллельном выполнении может накопиться несколько ошибок. `ExceptionGroup` объединяет их; `except*` сопоставляет подгруппы по типу. Подробнее — в [Модуле 3](03-asyncio.md) (`TaskGroup`).

### 11.14 Исключения в публичном API библиотеки

Документируйте стабильный набор исключений; оборачивайте низкоуровневые ошибки в доменные типы.

### 11.15 Анти-паттерны (best practices «наоборот»)

| Анти-паттерн | Проблема |
|--------------|----------|
| Голый `except:` | Ловит `KeyboardInterrupt`, скрывает баги |
| `except Exception: pass` | Тихое проглатывание |
| Слишком широкий except в середине стека | Невозможно отладить |
| Исключения для control flow в цикле | Медленно; используйте итераторы |
| Сообщения без контекста | `raise ValueError("invalid")` — какое поле? |
| Иерархия глубже 3 уровней без нужды | Сложно запомнить |

### 11.16 Исключения и типизация

mypy понимает `raise` в ветках:

```python
def parse_age(s: str) -> int:
    try:
        n = int(s)
    except ValueError:
        raise ValidationError(f"not an integer: {s!r}")
    if n < 0:
        raise ValidationError("age must be non-negative")
    return n
```

Для «ожидаемых» отсутствий иногда `Optional` или `Result[T, E]` явнее исключения — обсуждайте в команде единый стиль.

### 11.17 Связь с concurrent code

В [Модуле 12](12-concurrent-processes.md) исключения из worker-процессов **не пробрасываются** автоматически в родительский поток — их нужно получать через `Future.result()` или callbacks. Игнорирование `future.exception()` — типичный баг.

---

## Примеры кода

### Пример 1: try/except/else/finally

```python
def load_lines(path: str) -> list[str]:
    lines: list[str] = []
    f = None
    try:
        f = open(path, encoding="utf-8")
        for line in f:
            lines.append(line.rstrip("\n"))
    except OSError as exc:
        raise FileLoadError(path) from exc
    else:
        return lines
    finally:
        if f is not None:
            f.close()


class FileLoadError(OSError):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"cannot load {path}")
```

### Пример 2: Иерархия доменных исключений

```python
class PaymentError(Exception):
    """Базовая ошибка платёжного домена."""


class CardDeclined(PaymentError):
    def __init__(self, reason: str, code: str) -> None:
        self.reason = reason
        self.code = code
        super().__init__(f"Card declined: {reason} ({code})")


class InsufficientFunds(PaymentError):
    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Need {required}, have {available}"
        )


def charge(amount: int, balance: int) -> int:
    if amount > balance:
        raise InsufficientFunds(amount, balance)
    return balance - amount
```

### Пример 3: EAFP для dict

```python
CACHE: dict[str, str] = {}


def get_or_fetch(key: str, fetcher) -> str:
    try:
        return CACHE[key]
    except KeyError:
        value = fetcher(key)
        CACHE[key] = value
        return value
```

### Пример 4: Цепочка from

```python
import json


class ConfigError(Exception):
    pass


def load_json_config(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("Malformed configuration file") from exc
```

### Пример 5: contextlib.suppress и context manager

```python
from contextlib import contextmanager, suppress
import os


@contextmanager
def temp_env(key: str, value: str):
    old = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            with suppress(KeyError):
                del os.environ[key]
        else:
            os.environ[key] = old


with temp_env("APP_MODE", "test"):
    assert os.environ["APP_MODE"] == "test"
```

### Пример 6: Валидация dataclass + исключения

```python
from dataclasses import dataclass


class ValidationError(Exception):
    pass


@dataclass
class Age:
    years: int

    def __post_init__(self) -> None:
        if self.years < 0 or self.years > 150:
            raise ValidationError(f"unrealistic age: {self.years}")


try:
    Age(-1)
except ValidationError as exc:
    print(exc)
```

### Пример 7: Обработка нескольких исключений с приоритетом

```python
def divide(a: float, b: float) -> float:
    try:
        return a / b
    except ZeroDivisionError:
        raise
    except TypeError as exc:
        raise TypeError("arguments must be numbers") from exc
```

---

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Исключения | Явный сбой, stack trace | Накладные расходы на throw | Ошибочные редкие ветки |
| Коды возврата / Optional | Предсказуемый поток | Легко игнорировать ошибку | Ожидаемое отсутствие (get) |
| EAFP | Чистый success path | Непонятно без знания API | dict, файлы, протоколы |
| LBYL | Явные условия | Гонки, дублирование проверок | Частый success, простые инварианты |
| Широкий `except Exception` | Единая точка логирования | Маскирует баги | Top-level handler |
| Узкий `except` | Точная реакция | Больше веток | Бизнес-логика |
| Custom hierarchy | `except AppError` | Поддержка иерархии | Средние и крупные проекты |
| `raise from` | Диагностика | Verbose | Обёртка низкоуровневых ошибок |
| `suppress()` | Краткий cleanup | Скрывает все ошибки типа | Идempotent delete |
| Result/Either (библиотека) | Явность в типах | Не идиоматично для Python | FP-стиль, публичные SDK |

---

## Практические задания

### Задание 1 (базовое): Парсер возраста

**Условие:** функция `parse_age(raw: str) -> int`:

- пустая строка → `ValidationError("empty input")`;
- не целое → `ValidationError` с текстом `not an integer: ...`;
- отрицательное → `ValidationError`;
- иначе возвращает int.

Определите `class ValidationError(ValueError)` — наследник для узкого перехвата. Напишите `main`, читающий из `sys.argv`.

**Критерии:**

- Используется `try/except` для `int()` (EAFP).
- Не голый `except`.
- Тесты на `""`, `"abc"`, `"-5"`, `"25"`.

---

### Задание 2 (среднее): Мини-репозиторий с NotFound

**Условие:** классы `RepositoryError`, `NotFoundError(entity, id)`. `InMemoryRepo` с `get(id) -> Item` и `add(item)`. `get` поднимает `NotFoundError`, если id отсутствует. Функция `find_user_email(repo, user_id) -> str` ловит **только** `NotFoundError` и возвращает `""`, остальные пробрасывает.

**Критерии:**

- `NotFoundError` хранит `entity` и `entity_id`.
- `find_user_email` не ловит `Exception` целиком.
- Демонстрация `raise ... from` при обёртке `KeyError` (опционально внутри repo).

---

### Задание 3 (продвинутое): Загрузчик конфигурации

**Условие:** `load_config(path: str) -> AppConfig` где `AppConfig` — dataclass из [Модуля 10](10-dataclasses.md). Этапы:

1. Чтение файла → `ConfigError` при `OSError` с `from`.
2. `json.loads` → `ConfigError` при `JSONDecodeError` с `from`.
3. Валидация полей (`host` не пустой, `port` 1–65535) → `ConfigValidationError` (подкласс `ConfigError`).

Используйте `try/except/else`: парсинг JSON в `try`, валидация в `else`. Ресурс — `with open(...)`.

**Критерии:**

- Три уровня иерархии: `ConfigError` → `ConfigValidationError`.
- Traceback показывает цепочку при обёртке файловой ошибки.
- Unit-тест с несуществующим файлом, битым JSON, невалидным port.

---

## Эталонные решения

<details>
<summary>Задание 1 — parse_age</summary>

```python
import sys


class ValidationError(ValueError):
    pass


def parse_age(raw: str) -> int:
    raw = raw.strip()
    if not raw:
        raise ValidationError("empty input")
    try:
        age = int(raw)
    except ValueError:
        raise ValidationError(f"not an integer: {raw!r}")
    if age < 0:
        raise ValidationError(f"negative age: {age}")
    return age


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        try:
            print(parse_age(arg))
        except ValidationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
```

</details>

<details>
<summary>Задание 2 — InMemoryRepo</summary>

```python
from dataclasses import dataclass


class RepositoryError(Exception):
    pass


class NotFoundError(RepositoryError):
    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id!r} not found")


@dataclass
class Item:
    id: int
    email: str


class InMemoryRepo:
    def __init__(self) -> None:
        self._store: dict[int, Item] = {}

    def add(self, item: Item) -> None:
        self._store[item.id] = item

    def get(self, item_id: int) -> Item:
        try:
            return self._store[item_id]
        except KeyError as exc:
            raise NotFoundError("Item", item_id) from exc


def find_user_email(repo: InMemoryRepo, user_id: int) -> str:
    try:
        return repo.get(user_id).email
    except NotFoundError:
        return ""


if __name__ == "__main__":
    repo = InMemoryRepo()
    repo.add(Item(1, "a@ex.com"))
    assert find_user_email(repo, 1) == "a@ex.com"
    assert find_user_email(repo, 99) == ""
```

</details>

<details>
<summary>Задание 3 — load_config</summary>

```python
import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


class ConfigValidationError(ConfigError):
    pass


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int = 8080


def _validate(data: dict) -> AppConfig:
    host = data.get("host", "")
    port = data.get("port", 8080)
    if not isinstance(host, str) or not host.strip():
        raise ConfigValidationError("host must be non-empty string")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigValidationError("port must be int in 1..65535")
    return AppConfig(host=host.strip(), port=port)


def load_config(path: str) -> AppConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {path}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError("invalid JSON in config") from exc
    else:
        if not isinstance(data, dict):
            raise ConfigValidationError("root must be object")
        return _validate(data)


if __name__ == "__main__":
    # тесты вручную с tempfile
    import tempfile
    p = Path(tempfile.mktemp(suffix=".json"))
    p.write_text('{"host": "localhost", "port": 3000}')
    cfg = load_config(str(p))
    assert cfg.host == "localhost"
    p.unlink(missing_ok=True)
```

</details>

---

## Вопросы для самопроверки

1. В каком порядке выполняются `try`, `except`, `else`, `finally`?
2. Когда выполняется блок `else`?
3. Чем `raise A from B` отличается от просто `raise A` внутри `except`?
4. Почему `except:` без типа опасен?
5. Что такое EAFP и приведите пример?
6. Зачем базовый класс `AppError` для доменных исключений?
7. Почему не стоит `return` в `finally`?
8. Как залогировать traceback, не глотая исключение?
9. Что делает `except*` в Python 3.11+?
10. Как получить исключение из `Future` в ProcessPoolExecutor?

---

## Методические указания

### Для преподавателя

- Нарисуйте дерево `Exception` и классифицируйте 10 ситуаций.
- Live demo: `raise ... from` с traceback vs `from None`.
- Свяжите с [Модулем 12](12-concurrent-processes.md): `future.result()` пробрасывает исключение воркера.

### Для студента

- Читайте traceback **снизу вверх** — последняя строка часто ключевая.
- Пишите сообщения исключений с **контекстом** (id, field, path).
- В тестах используйте `pytest.raises(NotFoundError)` с проверкой атрибутов.
- Не используйте исключения для обычного ветвления в tight loop.

### Типичные ошибки

1. `except Exception: log; return None` — скрытый сбой.
2. Ловля `KeyError` там, где нужен собственный `NotFoundError` с контекстом.
3. Забытый `raise` после логирования — ошибка «исчезает».
4. Слишком глубокая иерархия исключений без документации.
5. Игнорирование исключений в concurrent коде.

---

## Дополнительные материалы

### Документация

- [Built-in Exceptions](https://docs.python.org/3/library/exceptions.html)
- [Errors and Exceptions — Tutorial](https://docs.python.org/3/tutorial/errors.html)
- [PEP 654 – Exception Groups](https://peps.python.org/pep-0654/)
- [contextlib.suppress](https://docs.python.org/3/library/contextlib.html#contextlib.suppress)

### Статьи

- *Effective Python* — Item про EAFP и узкие except
- Real Python — *Python Exceptions: An Introduction*

### Связь с модулями курса

| Модуль | Связь |
|--------|-------|
| [10 Dataclasses](10-dataclasses.md) | `__post_init__` + ValidationError |
| [12 Процессы](12-concurrent-processes.md) | Future.exception(), IPC errors |
| [03 asyncio](03-asyncio.md) | TaskGroup, ExceptionGroup |
| [05 Уязвимости](05-object-vulnerabilities.md) | Не глотать security-related errors |
