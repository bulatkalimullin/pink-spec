# Модуль 10: Дата классы

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 10 |
| Предварительные знания | [Модуль 4: ООП](04-oop.md), [Модуль 5: Уязвимости объектов](05-object-vulnerabilities.md), [Модуль 9: Синглтоны](09-singletons.md) |
| Предыдущий модуль | [09-singletons.md](09-singletons.md) |
| Следующий модуль | [11-exceptions.md](11-exceptions.md) |
| Ориентировочное время | 5–6 часов |
| Версия Python | 3.11+ |
| Ключевые темы | `@dataclass`, `field`, `frozen`, `slots`, `order`, `__post_init__`, `kw_only`, сравнение с `namedtuple` |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Создавать** data-классы с `@dataclass` вместо ручного boilerplate `__init__`, `__repr__`, `__eq__`.
2. **Настраивать** поля через `field()`: `default_factory`, `repr=False`, `compare=False`, `init=False`.
3. **Применять** `frozen=True` для неизменяемых DTO и `slots=True` для экономии памяти.
4. **Избегать** классической ошибки mutable default (`field(default_factory=list)`).
5. **Валидировать** данные в `__post_init__` и понимать ограничения dataclass vs Pydantic.
6. **Выбирать** между `@dataclass`, `typing.NamedTuple`, обычным классом и `dict` для конкретной задачи.

---

## Теория

### 10.1 Зачем нужны dataclass

До Python 3.7 классы «только для данных» писали вручную:

```python
class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"Point(x={self.x!r}, y={self.y!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Point):
            return NotImplemented
        return self.x == other.x and self.y == other.y
```

**PEP 557** ввёл `@dataclass` — декоратор генерирует эти методы из аннотаций полей. Меньше кода, меньше ошибок, лучше поддержка в IDE и mypy.

Dataclass **не заменяет** богатую доменную модель с инвариантами и поведением — он для **структурированных записей** (DTO, events, config, rows).

### 10.2 Базовый синтаксис

```python
from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    email: str = ""
```

Декоратор добавляет:

- `__init__(self, id: int, name: str, email: str = "")`
- `__repr__`
- `__eq__` (по умолчанию сравнивает все поля)

Поля **без значения по умолчанию** должны идти **перед** полями с default — как в обычной функции.

### 10.3 Параметры декоратора `@dataclass`

| Параметр | По умолчанию | Назначение |
|----------|--------------|------------|
| `init` | `True` | Генерировать `__init__` |
| `repr` | `True` | Генерировать `__repr__` |
| `eq` | `True` | Генерировать `__eq__` |
| `order` | `False` | Генерировать `__lt__`, `__le__`, `__gt__`, `__ge__` |
| `frozen` | `False` | Запрет присваивания полям после создания |
| `slots` | `False` (3.10+) | `__slots__` вместо `__dict__` |
| `kw_only` | `False` (3.10+) | Все поля только keyword-only в `__init__` |
| `match_args` | `True` | Поддержка structural pattern matching |

```python
@dataclass(frozen=True, slots=True, order=False)
class Event:
    name: str
    payload: dict
```

### 10.4 `field()` — тонкая настройка полей

```python
from dataclasses import dataclass, field


@dataclass
class Task:
    title: str
    tags: list[str] = field(default_factory=list)
    _id: int = field(default=0, init=False, repr=False)
    priority: int = field(default=5, compare=True)
    notes: str = field(default="", compare=False, hash=False)
```

**Ключевые аргументы `field()`:**

- `default` — только для **immutable** значений (`0`, `""`, `None`).
- `default_factory` — callable без аргументов для **mutable** (`list`, `dict`, `set`).
- `init=False` — поле не в `__init__` (задаётся в `__post_init__` или как class variable).
- `repr=False` — скрыть из repr (секреты, большие blob).
- `compare=False` — исключить из `__eq__` / ordering.
- `hash` — участие в `__hash__` (при `frozen=True`).

### 10.5 Опасность mutable default — связь с модулем 5

```python
# ОШИБКА — все экземпляры разделяют один список!
@dataclass
class Broken:
    items: list = []

# ПРАВИЛЬНО
@dataclass
class Fixed:
    items: list = field(default_factory=list)
```

Это тот же анти-паттерн, что `def f(x=[])` ([Модуль 5](05-object-vulnerabilities.md)). `default_factory` вызывается **для каждого нового экземпляра**.

### 10.6 `frozen=True` — неизменяемые объекты

`frozen=True` делает dataclass **hashable** (если все поля hashable) и безопасным для использования в `set` и как ключ `dict`.

```python
@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str = "RUB"
```

Присваивание `money.amount = 100` → `FrozenInstanceError`.

**Паттерн:** domain events, config, value objects. Используется в [Модуле 9](09-singletons.md) для `Settings`.

**Ограничение:** `frozen` не делает глубоко immutable вложенные `list`/`dict` — только запрет переприсвоения полей. Для глубокой immutability — `tuple`, `frozenset`, или отдельные frozen-типы.

### 10.7 `slots=True` — память и скорость

С Python 3.10 `@dataclass(slots=True)` генерирует `__slots__`:

- нет `__dict__` на экземпляре — меньше памяти;
- быстрее доступ к атрибутам;
- **нельзя** добавить произвольный атрибут `obj.extra = 1` → `AttributeError`.

С 3.11+ `slots=True` совместим с `weakref` и наследованием (с ограничениями). Для миллионов мелких объектов (события, точки, ячейки) — заметная экономия.

Связь с [Модулем 15](15-slots.md) — углублённое изучение `__slots__`.

### 10.8 `order=True` — сравнение и heapq

`order=True` генерирует порядковые методы по полям **слева направо**:

```python
@dataclass(order=True)
class PrioritizedJob:
    priority: int
    name: str = field(compare=False)
```

`job1 < job2` сравнивает сначала `priority`, затем `name` (если не `compare=False`).

Для `heapq` часто нужно только одно поле для сравнения — остальные помечайте `compare=False`, иначе tie-break по строке может быть неожиданным.

### 10.9 `__post_init__` — валидация и вычисляемые поля

```python
@dataclass
class Rectangle:
    width: float
    height: float
    area: float = field(init=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        self.area = self.width * self.height
```

`__post_init__` вызывается **после** сгенерированного `__init__`. Здесь — инварианты, нормализация, присвоение `init=False` полей.

Для `frozen=True` используйте `object.__setattr__(self, 'area', value)` внутри `__post_init__`.

### 10.10 `kw_only` — явные keyword-аргументы

```python
@dataclass(kw_only=True)
class Connection:
    host: str
    port: int = 5432
    ssl: bool = True

# Connection("localhost")  # TypeError
conn = Connection(host="localhost")
```

Полезно при большом числе полей с defaults — вызов `User(1, "Ann", "", True, False, ...)` нечитаем.

### 10.11 Наследование dataclass

Подкласс добавляет поля; правила default те же:

```python
@dataclass
class Animal:
    name: str

@dataclass
class Dog(Animal):
    breed: str = "mixed"
```

Если родитель не frozen, а ребёнок `frozen=True` — ограничения наследования (см. документацию). В практике: **не смешивайте** frozen и mutable в иерархии без необходимости.

### 10.12 `dataclass` vs `namedtuple` vs `TypedDict`

| | `@dataclass` | `namedtuple` | `TypedDict` |
|---|--------------|--------------|-------------|
| Mutability | настраивается | immutable | dict — mutable |
| Методы | да | ограничено | нет |
| `isinstance` | да | да | нет (dict) |
| Память | slots помогает | компактно | обычный dict |
| Валидация | `__post_init__` | вручную | вручную |
| JSON | через `asdict` | `_asdict()` | нативно dict |

**`typing.NamedTuple`** — компромисс: immutability + типы + методы:

```python
from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float

    def distance_sq(self) -> float:
        return self.x ** 2 + self.y ** 2
```

### 10.13 Сериализация: `asdict`, `astuple`, `replace`

```python
from dataclasses import asdict, astuple, replace

@dataclass(frozen=True)
class Config:
    host: str
    port: int = 8080

cfg = Config("localhost")
asdict(cfg)           # {'host': 'localhost', 'port': 8080}
astuple(cfg)          # ('localhost', 8080)
replace(cfg, port=9000)  # новый Config, host тот же
```

`asdict` рекурсивно обходит вложенные dataclass. Для JSON — `json.dumps(asdict(cfg))`. Осторожно с `datetime`, `Decimal` — нужны custom encoders.

### 10.14 Когда dataclass недостаточен

- Сложная валидация схемы → **Pydantic** `BaseModel`.
- ORM entity с lazy loading → SQLAlchemy model.
- Богатая доменная логика с инвариантами → обычный класс или aggregate root.

Dataclass — **тонкий слой данных**, не серебряная пуля.

---

## Примеры кода

### Пример 1: Базовый User

```python
from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    email: str = ""

    def display_name(self) -> str:
        return self.name or f"user-{self.id}"


u = User(1, "Alice", "alice@example.com")
print(u)  # User(id=1, name='Alice', email='alice@example.com')
assert u.display_name() == "Alice"
```

### Пример 2: `field(default_factory)` и теги

```python
from dataclasses import dataclass, field


@dataclass
class Article:
    title: str
    body: str
    tags: list[str] = field(default_factory=list)

    def add_tag(self, tag: str) -> None:
        self.tags.append(tag)


a1 = Article("Hello", "World")
a2 = Article("Other", "Text")
a1.add_tag("python")
assert a2.tags == []  # независимые списки
```

### Пример 3: frozen config + slots

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    host: str
    port: int = 5432
    name: str = "app"

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.host}:{self.port}/{self.name}"


cfg = DatabaseConfig("db.local")
assert cfg.dsn == "postgresql://db.local:5432/app"
# cfg.host = "x"  # FrozenInstanceError
```

### Пример 4: `__post_init__` валидация

```python
from dataclasses import dataclass


@dataclass
class EmailMessage:
    sender: str
    recipient: str
    subject: str
    body: str = ""

    def __post_init__(self) -> None:
        if "@" not in self.sender:
            raise ValueError(f"Invalid sender: {self.sender}")
        if "@" not in self.recipient:
            raise ValueError(f"Invalid recipient: {self.recipient}")
        if not self.subject.strip():
            raise ValueError("Subject cannot be empty")


msg = EmailMessage("alice@ex.com", "bob@ex.com", "Hi")
```

### Пример 5: Приоритетная очередь с `order=True`

```python
from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass(order=True)
class Job:
    priority: int
    seq: int
    name: str = field(compare=False)


class Scheduler:
    def __init__(self) -> None:
        self._heap: list[Job] = []
        self._seq = 0

    def submit(self, name: str, priority: int) -> None:
        heapq.heappush(self._heap, Job(priority, self._seq, name))
        self._seq += 1

    def pop(self) -> str:
        return heapq.heappop(self._heap).name


sched = Scheduler()
sched.submit("low", 10)
sched.submit("high", 1)
assert sched.pop() == "high"
```

### Пример 6: Domain event (immutable)

```python
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class OrderCreated:
    order_id: int
    customer_id: int
    total: float


Listener = Callable[[OrderCreated], None]


class OrderBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def publish(self, event: OrderCreated) -> None:
        for fn in self._listeners:
            fn(event)


received: list[OrderCreated] = []
bus = OrderBus()
bus.subscribe(lambda e: received.append(e))
bus.publish(OrderCreated(1, 42, 99.5))
assert received[0].order_id == 1
```

### Пример 7: `init=False` и фабричный метод

```python
from dataclasses import dataclass, field
import uuid


@dataclass
class Session:
    user_id: int
    token: str = field(init=False)
    created_at: float = field(init=False)

    def __post_init__(self) -> None:
        import time
        object.__setattr__(self, "token", uuid.uuid4().hex)
        object.__setattr__(self, "created_at", time.time())


@dataclass(frozen=True)
class FrozenSession:
    user_id: int
    token: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "token", uuid.uuid4().hex)


s = Session(1)
assert len(s.token) == 32
```

---

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| `@dataclass` mutable | Гибкость, методы | Не hashable по умолчанию | Внутренние модели, builders |
| `frozen=True` | Hashable, thread-safer reads | Нужен `replace` для «изменений» | Events, config, value objects |
| `slots=True` | Меньше RAM, быстрее | Нет произвольных атрибутов | Много мелких объектов |
| `order=True` | heapq, сортировка | Сложнее контроль сравнения | Priority queue |
| `namedtuple` | Компактный, immutable | Слабее наследование | Legacy, tuple unpacking |
| `TypedDict` | JSON-like, typing | Нет методов, mutable | API boundaries |
| Обычный class | Полный контроль | Boilerplate | Сложные инварианты |
| Pydantic | Валидация, coercion | Зависимость | HTTP API, settings |
| `dict` | Простейший | Нет типов, опечатки в ключах | Прототип, JSON blob |

---

## Практические задания

### Задание 1 (базовое): DTO для API ответа

**Условие:** создайте `@dataclass(slots=True)` `ProductDTO` с полями `sku: str`, `name: str`, `price: float`, `in_stock: bool = True`. Реализуйте метод `to_dict() -> dict` через `dataclasses.asdict`. Напишите функцию `from_row(row: tuple)` — `(sku, name, price)` → `ProductDTO`.

**Критерии:**

- `repr` читаемый, `eq` работает по полям.
- `from_row(("A1", "Widget", 9.99))` → корректный объект.
- Два независимых `ProductDTO` с `in_stock=True` по умолчанию.

---

### Задание 2 (среднее): Валидируемый интервал времени

**Условие:** `@dataclass(frozen=True, slots=True)` `TimeSlot` с `start: int`, `end: int` (минуты от полуночи). В `__post_init__`: `start < end`, оба в `[0, 24*60)`. Метод `duration() -> int`. Функция `overlaps(a: TimeSlot, b: TimeSlot) -> bool` для полуинтервалов `[start, end)`.

**Критерии:**

- `TimeSlot(600, 300)` → `ValueError`.
- Смежные слоты `[0,60)` и `[60,120)` не пересекаются.
- `overlaps(TimeSlot(0, 100), TimeSlot(50, 150))` → `True`.

---

### Задание 3 (продвинутое): Мини-реестр событий

**Условие:** базовый `@dataclass(frozen=True)` `Event` с `name: str` и `payload: dict`. Подклассы через наследование: `UserRegistered(user_id: int)`, `OrderPlaced(order_id: int, amount: float)` — поля в подклассе, `name` фиксирован через `default` или `__post_init__`. Класс `EventLog` хранит `list[Event]`, методы `append(event)`, `filter_by_name(name)`.

**Критерии:**

- События immutable; попытка изменить `payload` через переприсвоение поля — ошибка.
- `filter_by_name("user.registered")` возвращает только нужный тип.
- Используйте `field(default_factory=dict)` для `payload` осознанно (или `Mapping` в frozen — пустой dict по умолчанию через factory).

**Подсказка:** пример 6; pattern matching `match event:` (Python 3.10+).

---

## Эталонные решения

<details>
<summary>Задание 1 — ProductDTO</summary>

```python
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ProductDTO:
    sku: str
    name: str
    price: float
    in_stock: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def from_row(row: tuple[str, str, float]) -> ProductDTO:
    sku, name, price = row
    return ProductDTO(sku=sku, name=name, price=price)


if __name__ == "__main__":
    p = from_row(("A1", "Widget", 9.99))
    assert p.in_stock is True
    assert p.to_dict()["sku"] == "A1"
    p2 = ProductDTO("B2", "Bolt", 1.0)
    assert p2.in_stock is True
```

</details>

<details>
<summary>Задание 2 — TimeSlot</summary>

```python
from dataclasses import dataclass

DAY = 24 * 60


@dataclass(frozen=True, slots=True)
class TimeSlot:
    start: int
    end: int

    def __post_init__(self) -> None:
        if not (0 <= self.start < DAY and 0 < self.end <= DAY):
            raise ValueError("start/end out of day range")
        if self.start >= self.end:
            raise ValueError("start must be < end")

    def duration(self) -> int:
        return self.end - self.start


def overlaps(a: TimeSlot, b: TimeSlot) -> bool:
    return a.start < b.end and b.start < a.end


if __name__ == "__main__":
    try:
        TimeSlot(600, 300)
        assert False
    except ValueError:
        pass
    assert not overlaps(TimeSlot(0, 60), TimeSlot(60, 120))
    assert overlaps(TimeSlot(0, 100), TimeSlot(50, 150))
```

</details>

<details>
<summary>Задание 3 — EventLog</summary>

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    name: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UserRegistered(Event):
    user_id: int
    name: str = field(default="user.registered", init=False)
    payload: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "user.registered")
        object.__setattr__(self, "payload", {"user_id": self.user_id})


@dataclass(frozen=True)
class OrderPlaced(Event):
    order_id: int
    amount: float
    name: str = field(default="order.placed", init=False)
    payload: dict = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", "order.placed")
        object.__setattr__(
            self, "payload", {"order_id": self.order_id, "amount": self.amount}
        )


class EventLog:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    def filter_by_name(self, name: str) -> list[Event]:
        return [e for e in self._events if e.name == name]


if __name__ == "__main__":
    log = EventLog()
    log.append(UserRegistered(42))
    log.append(OrderPlaced(1, 99.0))
    users = log.filter_by_name("user.registered")
    assert len(users) == 1
    assert users[0].payload["user_id"] == 42
```

</details>

---

## Вопросы для самопроверки

1. Почему `tags: list = []` в dataclass опасно?
2. Что добавляет `frozen=True` к поведению экземпляра?
3. Когда нужен `field(compare=False)`?
4. Чем `replace()` отличается от мутации поля?
5. Зачем `slots=True` на hot path?
6. Вызывается ли `__post_init__` до или после присвоения полей в `__init__`?
7. Можно ли использовать mutable dataclass как ключ `dict`?
8. Когда `NamedTuple` предпочтительнее `@dataclass`?
9. Как скрыть секретное поле из `repr`?
10. Делает ли `frozen=True` вложенный `list` неизменяемым?

---

## Методические указания

### Для студента

1. Всегда используйте `default_factory` для `list`, `dict`, `set`.
2. Для событий и конфигурации по умолчанию начинайте с `frozen=True, slots=True`.
3. Валидацию держите в `__post_init__` — не размазывайте по коду.
4. Сравните размер в памяти: `slots=True` vs без — `sys.getsizeof` на серии объектов.
5. Перед Pydantic спросите: достаточно ли `__post_init__`?

### Для преподавателя

- **Live bug:** покажите shared mutable default без `default_factory` — два объекта, один список.
- Свяжите с [Модулем 9](09-singletons.md): `Settings` как frozen dataclass в модуле.
- Обсудите PEP 557 и эволюцию `kw_only` / `slots` в 3.10+.
- Типичная ошибка на собеседовании: путать `dataclass` с `attrs` / Pydantic.

### Лабораторная (опционально)

Сериализатор: список frozen dataclass → JSON Lines.

---

## Дополнительные материалы

### Документация

- [dataclasses — Data Classes](https://docs.python.org/3/library/dataclasses.html)
- [PEP 557 – Data Classes](https://peps.python.org/pep-0557/)
- [PEP 681 – Data Class Transforms](https://peps.python.org/pep-0681/) (typing ecosystem)

### Библиотеки

- [attrs](https://www.attrs.org/) — вдохновитель и альтернатива с большим числом hooks
- [Pydantic](https://docs.pydantic.dev/) — валидация для API

### Связь с модулями курса

| Модуль | Связь |
|--------|-------|
| [05 Уязвимости](05-object-vulnerabilities.md) | mutable defaults |
| [09 Синглтоны](09-singletons.md) | frozen Settings |
| [15 __slots__](15-slots.md) | углубление slots |
| [08 Паттерны](08-design-patterns.md) | Observer events |
| [11 Исключения](11-exceptions.md) | ValueError в `__post_init__` |
