# Модуль 16. Магические методы (Dunder Methods)

> Протоколы объектной модели Python: `__init__`, `__repr__`, `__eq__`, контекстные менеджеры (`__enter__`/`__exit__`), итераторы (`__iter__`/`__next__`) и интеграция с синтаксисом языка.

## Метаданные

| Параметр | Значение |
|----------|----------|
| Номер модуля | 16 |
| Название | Магические методы |
| Предварительные знания | Модуль 04 (ООП), модуль 07 (протоколы), модуль 15 (`__slots__`) |
| Следующий модуль | [17-capstone-tasks.md](17-capstone-tasks.md) — Итоговый проект |
| Ориентировочное время | 5–6 часов |
| Версия Python | 3.11+ |
| Сложность | Средняя → продвинутая |

## Цели обучения

После прохождения модуля студент сможет:

1. Объяснить роль dunder-методов как реализации **протоколов** Python.
2. Корректно реализовать `__init__`, `__repr__`, `__str__`, `__eq__` и `__hash__`.
3. Создавать **контекстные менеджеры** через класс и `contextlib`.
4. Реализовать **итератор** и **итерируемый** объект.
5. Избегать типичных ошибок: мутабельные объекты в `set`, нарушение контракта `__eq__`/`__hash__`.
6. Комбинировать магические методы с `@dataclass` и `__slots__`.

## Теория

### 16.1. Что такое магические методы

**Магические (dunder) методы** — методы с именами `__имя__`, вызываемые интерпретатором при операциях с объектом. Они не предназначены для прямого вызова пользователем (хотя технически это возможно).

```python
class Vector:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def __add__(self, other: "Vector") -> "Vector":
        return Vector(self.x + other.x, self.y + other.y)

v1 = Vector(1, 2)
v2 = Vector(3, 4)
v3 = v1 + v2  # вызывает v1.__add__(v2)
```

Dunder-методы — механизм **duck typing** на уровне интерпретатора: если объект поддерживает протокол, он «ведёт себя как» встроенный тип.

### 16.2. `__init__` и `__new__`

**`__init__(self, ...)`** — инициализация уже созданного экземпляра. Не создаёт объект, а настраивает его.

**`__new__(cls, ...)`** — создание экземпляра (вызывается **до** `__init__`). Используется редко: синглтоны, immutable типы, подклассы `tuple`/`str`.

```python
class Temperature:
    def __init__(self, celsius: float) -> None:
        if celsius < -273.15:
            raise ValueError("below absolute zero")
        self.celsius = celsius

class Singleton:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Рекомендации для `__init__`:**

- Не возвращайте значение (не `return self`).
- Валидируйте входные данные.
- При наследовании используйте `super().__init__(...)`.

### 16.3. `__repr__` и `__str__`

| Метод | Аудитория | Цель | Пример вызова |
|-------|-----------|------|---------------|
| `__repr__` | Разработчик | Однозначное, отлаживаемое представление | `repr(obj)`, интерактивная консоль |
| `__str__` | Пользователь | Читаемый вывод | `str(obj)`, `print(obj)` |

**Контракт `__repr__`:** желательно `eval(repr(obj)) == obj` (не всегда достижимо).

```python
class User:
    def __init__(self, user_id: int, name: str) -> None:
        self.user_id = user_id
        self.name = name

    def __repr__(self) -> str:
        return f"User(user_id={self.user_id!r}, name={self.name!r})"

    def __str__(self) -> str:
        return f"{self.name} (#{self.user_id})"
```

Если `__str__` не определён, используется `__repr__`.

**f-строки и `!r`:** `!r` вызывает `repr()` для аргумента.

### 16.4. `__eq__`, `__ne__`, `__hash__`

**`__eq__(self, other)`** — равенство по значению. Должен возвращать `NotImplemented` для несовместимых типов (не `False`!).

```python
class Money:
    def __init__(self, amount: float, currency: str) -> None:
        self.amount = amount
        self.currency = currency

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount == other.amount and self.currency == other.currency
```

**`__hash__(self)`** — хеш для `dict`/`set`. Контракт:

- Если `a == b`, то `hash(a) == hash(b)`.
- Если объект мутабелен и участвует в `__eq__`, **не переопределяйте `__hash__`** (Python 3 делает его `None` при кастомном `__eq__`).

```python
@dataclass(frozen=True)
class Point:
    x: int
    y: int
# frozen=True → auto __hash__

{Point(1, 2), Point(1, 2)}  # один элемент
```

**Мутабельный объект:**

```python
class MutableBag:
    def __init__(self, items: list) -> None:
        self.items = list(items)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MutableBag):
            return NotImplemented
        return self.items == other.items

    # __hash__ не определён → нельзя класть в set
```

### 16.5. Сравнение: полный набор ordering

`@dataclass(order=True)` или `functools.total_ordering`:

```python
from functools import total_ordering

@total_ordering
class Version:
    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor) == (other.major, other.minor)

    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor) < (other.major, other.minor)
```

Нужны: `__lt__` + `__eq__` (остальное генерирует `total_ordering`).

### 16.6. Контекстные менеджеры

Протокол контекстного менеджера:

- `__enter__(self)` — вход в `with`, возвращаемое значение → `as variable`
- `__exit__(self, exc_type, exc_val, exc_tb)` — выход, подавление исключения если вернуть `True`

```python
class DatabaseTransaction:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._active = False

    def __enter__(self) -> "DatabaseTransaction":
        self._conn.execute("BEGIN")
        self._active = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            self._conn.execute("COMMIT")
        else:
            self._conn.execute("ROLLBACK")
        self._active = False
        return False  # не подавлять исключение

with DatabaseTransaction(conn) as tx:
    conn.execute("INSERT ...")
```

**`contextlib.contextmanager`** — генераторный стиль:

```python
from contextlib import contextmanager

@contextmanager
def timer(label: str):
    import time
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{label}: {elapsed:.3f}s")

with timer("load"):
    ...
```

**`contextlib.ExitStack`** — динамическое управление несколькими контекстами.

### 16.7. Итераторы и итерируемые объекты

**Протокол итерируемого (Iterable):** `__iter__()` возвращает итератор.

**Протокол итератора (Iterator):** `__iter__()` + `__next__()`; при исчерпании — `StopIteration`.

```python
class Countdown:
    def __init__(self, start: int) -> None:
        self.current = start

    def __iter__(self) -> "Countdown":
        return self

    def __next__(self) -> int:
        if self.current <= 0:
            raise StopIteration
        value = self.current
        self.current -= 1
        return value

for n in Countdown(3):
    print(n)  # 3, 2, 1
```

**Разделение Iterable и Iterator:**

```python
class Range:
    """Итерируемый — каждый __iter__ создаёт новый итератор."""
    def __init__(self, n: int) -> None:
        self.n = n

    def __iter__(self):
        return _RangeIterator(self.n)

class _RangeIterator:
    def __init__(self, n: int) -> None:
        self.n = n
        self.i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.i >= self.n:
            raise StopIteration
        self.i += 1
        return self.i - 1
```

**Генераторы** — синтаксический сахар:

```python
def countdown(start: int):
    current = start
    while current > 0:
        yield current
        current -= 1
```

`yield` автоматически создаёт объект с `__iter__` и `__next__`.

### 16.8. Другие важные dunder-методы (обзор)

| Метод | Операция |
|-------|----------|
| `__len__` | `len(obj)` |
| `__getitem__`, `__setitem__` | `obj[key]` |
| `__call__` | `obj()` |
| `__enter__`, `__exit__` | `with obj` |
| `__bool__` | `bool(obj)`, условия |
| `__contains__` | `item in obj` |
| `__getattr__`, `__getattribute__` | доступ к атрибутам |
| `__copy__`, `__deepcopy__` | копирование |

### 16.9. `__getattr__` vs `__getattribute__`

```python
class LazyLoader:
    def __init__(self) -> None:
        object.__setattr__(self, "_cache", {})

    def __getattr__(self, name: str):
        if name.startswith("load_"):
            key = name[5:]
            if key not in self._cache:
                self._cache[key] = f"data for {key}"
            return self._cache[key]
        raise AttributeError(name)
```

`__getattribute__` вызывается **всегда**; осторожно с рекурсией — используйте `object.__getattribute__(self, name)`.

### 16.10. Магические методы и dataclass

```python
from dataclasses import dataclass, field

@dataclass
class Product:
    sku: str
    price: float
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("price must be non-negative")
```

`__post_init__` — хук после автогенерированного `__init__`.

### 16.11. Антипаттерны

1. **`__eq__` без `isinstance`** — сравнение с любым типом ломает симметрию.
2. **Мутабельный `__hash__`** — объекты «теряются» в `set`.
3. **`__repr__` без атрибутов** — бесполезен при отладке.
4. **Итератор с общим состоянием** — один итератор на всех потребителей без `__iter__` → нового итератора.
5. **`__exit__` глотает все исключения** без логирования.

## Примеры кода

### Пример 1. Полноценный класс Order

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

@dataclass
class Order:
    customer_id: int
    items: list[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        return (
            f"Order(id={self.id!s}, customer_id={self.customer_id}, "
            f"items={self.items!r}, created_at={self.created_at!r})"
        )

    def __str__(self) -> str:
        return f"Order {self.id} for customer {self.customer_id} ({len(self.items)} items)"
```

### Пример 2. Контекстный менеджер файла с метриками

```python
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def open_and_count(path: Path):
    lines = 0
    f = path.open("r", encoding="utf-8")
    try:
        yield f, lambda: lines
    finally:
        f.close()

# Упрощённый вариант — класс
class LineCounter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.line_count = 0
        self._file = None

    def __enter__(self):
        self._file = self.path.open("r", encoding="utf-8")
        return self

    def __exit__(self, *args):
        self._file.close()
        return False

    def read_lines(self) -> list[str]:
        lines = self._file.readlines()
        self.line_count = len(lines)
        return lines
```

### Пример 3. Итератор по батчам

```python
from collections.abc import Iterator, Iterable

class BatchIterator(Iterator[list]):
    def __init__(self, data: list, batch_size: int) -> None:
        self._data = data
        self._batch_size = batch_size
        self._index = 0

    def __iter__(self) -> "BatchIterator":
        return self

    def __next__(self) -> list:
        if self._index >= len(self._data):
            raise StopIteration
        batch = self._data[self._index : self._index + self._batch_size]
        self._index += self._batch_size
        return batch

def batched(data: list, size: int) -> Iterable[list]:
    return BatchIterator(data, size)

list(batched([1, 2, 3, 4, 5], 2))  # [[1, 2], [3, 4], [5]]
```

### Пример 4. Python 3.11+ Self и typing

```python
from typing import Self

class Builder:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, part: str) -> Self:
        self.parts.append(part)
        return self

    def build(self) -> str:
        return "".join(self.parts)
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Ручные dunder | Полный контроль | Boilerplate | Кастомная семантика |
| `@dataclass` | Авто `__init__`, `__repr__`, `__eq__` | Меньше гибкости | DTO, record types |
| `contextmanager` | Компактность | Сложная логика в generator | Простые `with` |
| Класс CM | Явный `__enter__`/`__exit__` | Больше кода | Ресурсы, транзакции |
| Генератор (`yield`) | Простой итератор | Состояние в closure | Ленивые последовательности |
| Класс Iterator | Переиспользование, тесты | Больше классов | Сложная итерация |

## Практические задания

### Задание 1 (базовое). Класс `Book`

Реализуйте `Book(title, author, year)` с:

- `__repr__` — однозначное представление
- `__str__` — «Title by Author (Year)»
- `__eq__` — по `(title, author, year)`
- Книги можно класть в `set` (реализуйте `__hash__` или используйте frozen dataclass)

### Задание 2 (среднее). `TempFile` context manager

Класс `TempFile(path)`:

- `__enter__` создаёт пустой файл по `path`
- `__exit__` удаляет файл (даже при исключении)
- Поддержка `with TempFile("/tmp/x.txt") as f:` для записи

Напишите тест: исключение внутри `with` всё равно удаляет файл.

### Задание 3 (продвинутое). `PagedQuery` iterator

Реализуйте итерируемый `PagedQuery(fetch_page, page_size)` где `fetch_page(page: int) -> list[T]` — callback.

Итератор лениво запрашивает страницы 0, 1, 2, ... пока не вернётся пустой список.

```python
def fake_fetch(page: int) -> list[int]:
    data = list(range(25))
    start = page * 10
    return data[start : start + 10]

for item in PagedQuery(fake_fetch, page_size=10):
    print(item)  # 0..24
```

## Эталонные решения

<details>
<summary>Задание 1 — решение</summary>

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Book:
    title: str
    author: str
    year: int

    def __str__(self) -> str:
        return f"{self.title} by {self.author} ({self.year})"

b1 = Book("1984", "Orwell", 1949)
b2 = Book("1984", "Orwell", 1949)
assert repr(b1) == "Book(title='1984', author='Orwell', year=1949)"
assert str(b1) == "1984 by Orwell (1949)"
assert b1 == b2
assert len({b1, b2}) == 1
```

</details>

<details>
<summary>Задание 2 — решение</summary>

```python
from pathlib import Path

class TempFile:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __enter__(self):
        self.path.write_text("", encoding="utf-8")
        return self.path.open("w", encoding="utf-8")

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            pass
        finally:
            if self.path.exists():
                self.path.unlink()
        return False

# Тест
p = Path("/tmp/test_capstone_temp.txt")
try:
    with TempFile(p) as f:
        f.write("hello")
        raise RuntimeError("boom")
except RuntimeError:
    pass
assert not p.exists()
```

</details>

<details>
<summary>Задание 3 — решение</summary>

```python
from collections.abc import Callable, Iterator, Iterable
from typing import TypeVar

T = TypeVar("T")

class PagedQuery(Iterable[T]):
    def __init__(
        self,
        fetch_page: Callable[[int], list[T]],
        page_size: int = 10,
    ) -> None:
        self._fetch_page = fetch_page
        self._page_size = page_size

    def __iter__(self) -> Iterator[T]:
        page = 0
        while True:
            batch = self._fetch_page(page)
            if not batch:
                break
            yield from batch
            page += 1

def fake_fetch(page: int) -> list[int]:
    data = list(range(25))
    start = page * 10
    return data[start : start + 10]

assert list(PagedQuery(fake_fetch)) == list(range(25))
```

</details>

## Вопросы для самопроверки

1. Чем `__repr__` отличается от `__str__`?
2. Почему `__eq__` должен возвращать `NotImplemented`, а не `False`?
3. Можно ли положить мутабельный список с кастомным `__eq__` в `set`? Почему?
4. Что вернёт `__exit__`, если нужно подавить исключение?
5. В чём разница между итерируемым объектом и итератором?
6. Когда предпочтительнее генератор вместо класса с `__next__`?
7. Для чего нужен `__post_init__` в dataclass?
8. Что вызывает Python при выполнении `with obj:`?

<details>
<summary>Ответы</summary>

1. `__repr__` — для разработчиков (отладка); `__str__` — для пользователей (читаемость).
2. Чтобы Python попробовал reflected operation у другого операнда.
3. Нет, если `__eq__` переопределён — `__hash__` становится `None`.
4. `True` — исключение подавляется; `False` или `None` — пробрасывается.
5. Iterable предоставляет `__iter__`; Iterator — ещё и `__next__`, одноразовый проход.
6. Простые ленивые последовательности без сложного состояния.
7. Валидация и дополнительная инициализация после автогенерированного `__init__`.
8. `obj.__enter__()` при входе, `obj.__exit__(...)` при выходе.

</details>

## Методические указания для преподавателя

### Порядок подачи

1. `__repr__` / `__str__` — быстрый win, видно в REPL.
2. `__eq__` / `__hash__` — контракты и ловушки с `set`.
3. Context managers — связь с `try/finally` и ресурсами.
4. Итераторы — связь с `for`, генераторами, asyncio streams (модуль 03).

### Live coding

Реализуйте `PagedQuery` вместе со студентами — хороший мост к async-итераторам (`__aiter__`).

### Оценка

| Компонент | Вес |
|-----------|-----|
| Корректность dunder | 40% |
| Тесты | 30% |
| Читаемость / typing | 20% |
| Документация | 10% |

## Дополнительные материалы

- [Python Data Model](https://docs.python.org/3/reference/datamodel.html) — полный список dunder
- [collections.abc](https://docs.python.org/3/library/collections.abc.html) — формальные протоколы
- [contextlib](https://docs.python.org/3/library/contextlib.html)
- *Fluent Python*, 2nd ed. — главы о протоколах и ABC
- PEP 343 — with statement
