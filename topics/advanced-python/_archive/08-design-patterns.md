# Модуль 8: Паттерны проектирования в Python

## Метаданные

| Параметр | Значение |
|----------|----------|
| Предварительные знания | [Модуль 4: ООП](04-oop.md), [Модуль 6: TypeVar](06-mutations-typevar.md), [Модуль 7: Protocols](07-protocols.md); базовое понимание [asyncio](03-asyncio.md) для Observer/async вариантов |
| Следующий модуль | Big O и алгоритмы (следующий блок курса) |
| Ориентировочное время | 4 ч |

## Цели обучения

1. **Реализовывать** Singleton, Factory, Strategy, Observer и Dependency Injection **идиоматично** для Python — без лишней Java-церемонии, с опорой на модули, callable и `Protocol`.
2. **Выбирать** между паттерном и простой функцией/модулем, заполняя таблицу trade-offs для конкретной задачи.
3. **Связывать** DI с тестируемостью и избеганием глобального mutable state из [Модуля 5](05-object-vulnerabilities.md).
4. **Применять** Strategy через функции первого класса и через `Protocol` из [Модуля 7](07-protocols.md).
5. **Проектировать** расширяемый код (новые стратегии, наблюдатели, фабрики) без изменения существующих классов (Open/Closed).

## Теория

### 8.1 Паттерны — не цель, а словарь

**Паттерн проектирования** — проверенное решение повторяющейся задачи в контексте ООП-системы. В Python многие «классические» паттерны **упрощаются**:

- Функции — first-class → Strategy без иерархии классов.
- Модули — синглтоны по умолчанию (`import config`).
- Duck typing → интерфейсы через `Protocol` ([Модуль 7](07-protocols.md)).

Цель модуля — не заучить 23 паттерна GoF, а **узнавать проблему** и **применять Pythonic ответ**.

### 8.2 Singleton — один экземпляр на процесс

**Проблема:** нужен ровно один объект (пул соединений, конфиг, счётчик).

**Анти-паттерн в Python:** сложный double-checked locking как в Java.

**Идиоматичные варианты:**

| Подход | Суть |
|--------|------|
| Модуль | `settings.py` с глобальными константами — импорт один раз |
| `__new__` | Контроль создания экземпляра |
| Декоратор / метакласс | Редко; усложняет тесты |
| DI-контейнер | «Синглтон» — scope в контейнере, не глобальная переменная |

**Минусы Singleton:**

- Скрытая глобальная зависимость — сложные тесты.
- Shared mutable state ([Модуль 5](05-object-vulnerabilities.md)).
- В многопоточности ([Модуль 1: GIL](01-gil.md)) — нужна синхронизация при ленивой инициализации.

**Рекомендация курса:** предпочитайте **явный** объект, передаваемый в конструктор (DI), а не `get_instance()`.

### 8.3 Factory — создание объектов без привязки к классу

**Проблема:** клиент не должен знать, какой конкретный класс создаётся (`JSONParser` vs `XMLParser`).

**Виды:**

- **Simple factory:** функция `create_parser(fmt: str) -> Parser`.
- **Factory Method:** подкласс переопределяет `create_connection()`.
- **Abstract Factory:** семейство связанных продуктов (UI widgets для OS).

**Pythonic factory:**

```python
PARSERS = {"json": JsonParser, "xml": XmlParser}

def create_parser(name: str) -> Parser:
  try:
    return PARSERS[name]()
  except KeyError:
    raise ValueError(name)
```

Регистрация через декоратор — расширяемость без правки `if/elif`.

Связь с [Модулем 7](07-protocols.md): фабрика возвращает `Protocol Parser`, не конкретный класс.

### 8.4 Strategy — взаимозаменяемые алгоритмы

**Проблема:** поведение меняется (скидка, маршрут доставки, сжатие) без раздувания одного класса `if/elif`.

**Классический ООП:** интерфейс `Strategy` + `Context`.

**Pythonic:**

1. **Функции:** `def strategy_a(data): ...` передать в `process(data, strategy)`.
2. **Callable объект:** класс с `__call__`.
3. **Protocol:** структурный контракт ([Модуль 7](07-protocols.md)).

```python
from typing import Protocol

class Discount(Protocol):
  def apply(self, total: float) -> float: ...

def checkout(total: float, discount: Discount) -> float:
  return discount.apply(total)
```

**Плюс:** легко подставить lambda или mock в тесте.  
**Минус:** нет единого реестра стратегий — документируйте контракт.

### 8.5 Observer — уведомление подписчиков

**Проблема:** при изменении состояния (модель, кнопка, цена акции) нужно уведомить N заинтересованных сторон.

**Роли:**

- **Subject** — хранит состояние, список observers.
- **Observer** — `update(event)` или callback.

**Pythonic варианты:**

- Список `Callable[[Event], None]`.
- `weakref.WeakSet` для observers — избежать циклических ссылок.
- Для UI/async: `asyncio` queues ([Модуль 3](03-asyncio.md)) вместо синхронного оповещения.

**Отличие от pub/sub (Kafka, NATS):** Observer — in-process; message bus — межсервисный, с durability.

### 8.6 Dependency Injection (DI)

**Проблема:** класс `OrderService` не должен сам делать `psycopg.connect(...)` — иначе тесты требуют БД.

**DI:** зависимости **передаются извне** (конструктор, фабрика, framework).

```python
class OrderService:
  def __init__(self, repo: OrderRepo, notifier: Notifier) -> None:
    self._repo = repo
    self._notifier = notifier
```

**Способы в Python:**

| Способ | Пример |
|--------|--------|
| Constructor injection | `__init__(self, repo)` |
| Функциональный | `def handle(req, repo=default_repo)` |
| `dependency-injector`, FastAPI `Depends` | Контейнер / framework |
| Protocol + fake | Тест без БД |

**Связь с [Модулем 5](05-object-vulnerabilities.md):** глобальный `db = connect()` — анти-паттерн; DI делает зависимости явными.

**Не путать с Service Locator:** `get_service("db")` скрывает зависимости — хуже для чтения и тестов.

### 8.7 Когда паттерн не нужен

- Один алгоритм — одна функция.
- Одна реализация — не стройте Abstract Factory «на вырост».
- YAGNI: [Модуль 4](04-oop.md) учил ООП; не превращайте каждый скрипт в иерархию из 5 классов.

### 8.8 SOLID в контексте паттернов (кратко)

- **S** — Strategy выносит ветвление.
- **O** — Factory + регистрация: новые типы без правки клиента.
- **L** — подтипы Strategy взаимозаменяемы.
- **I** — мелкие Protocol вместо «God interface».
- **D** — DI: зависимость от абстракций (`Protocol`), не от `PostgresRepo`.

### 8.9 Паттерны и типизация

[Модуль 6](06-mutations-typevar.md): `GenericFactory[T]`, `TypeVar` для продуктов фабрики.  
[Модуль 7](07-protocols.md): Strategy и Repo как Protocol.

### 8.10 Тестирование с паттернами

- **Strategy:** подставить `lambda` или `FakeDiscount`.
- **Observer:** spy-callback, проверить вызовы.
- **DI:** передать `InMemoryRepo` из [Модуля 6](06-mutations-typevar.md).
- **Singleton:** в тестах сбрасывать состояние или не использовать Singleton вовсе.

## Примеры кода

### Пример 1: Singleton через модуль (предпочтительно)

```python
# app/config.py — модуль импортируется один раз
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
  database_url: str
  debug: bool = False

settings = Settings(database_url="postgresql://localhost/app")
```

```python
# app/service.py
from app.config import settings

def connect():
  return f"connecting to {settings.database_url}"
```

Тесты: `monkeypatch` атрибутов или отдельный модуль `test_settings`.

### Пример 2: Singleton через __new__ (когда действительно нужен класс)

```python
import threading


class DatabasePool:
  _instance = None
  _lock = threading.Lock()

  def __new__(cls, dsn: str):
    if cls._instance is None:
      with cls._lock:
        if cls._instance is None:
          inst = super().__new__(cls)
          inst._dsn = dsn
          inst._connections = []
          cls._instance = inst
    return cls._instance

  def __init__(self, dsn: str):
    pass  # инициализация только в __new__


pool_a = DatabasePool("postgres://x")
pool_b = DatabasePool("postgres://y")
assert pool_a is pool_b  # один пул — осторожно с разными DSN в тестах!
```

Для тестов добавьте `@classmethod reset_for_tests` или избегайте Singleton.

### Пример 3: Factory с регистрацией

```python
from typing import Callable, Protocol

class Serializer(Protocol):
  def dumps(self, obj: object) -> bytes: ...
  def loads(self, data: bytes) -> object: ...

_REGISTRY: dict[str, Callable[[], Serializer]] = {}


def register(name: str):
  def deco(cls):
    _REGISTRY[name] = cls
    return cls
  return deco


@register("json")
class JsonSerializer:
  def dumps(self, obj: object) -> bytes:
    import json
    return json.dumps(obj).encode()

  def loads(self, data: bytes) -> object:
    import json
    return json.loads(data.decode())


def create_serializer(name: str) -> Serializer:
  try:
    factory = _REGISTRY[name]
  except KeyError:
    raise ValueError(f"Unknown serializer: {name}")
  return factory()
```

### Пример 4: Strategy — функции vs классы

```python
from typing import Protocol


class PricingStrategy(Protocol):
  def price(self, base: float) -> float: ...


class Regular:
  def price(self, base: float) -> float:
    return base


class BlackFriday:
  def price(self, base: float) -> float:
    return base * 0.5


# Функциональная стратегия — тоже валидна
def student_discount(base: float) -> float:
  return base * 0.8


def final_price(base: float, strategy: PricingStrategy) -> float:
  return strategy.price(base)


assert final_price(100, BlackFriday()) == 50
```

### Пример 5: Observer с weakref

```python
import weakref
from typing import Callable


class EventBus:
  def __init__(self) -> None:
    self._listeners: list[Callable[[str, dict], None]] = []

  def subscribe(self, callback: Callable[[str, dict], None]) -> None:
    self._listeners.append(callback)

  def publish(self, event: str, payload: dict) -> None:
    for cb in list(self._listeners):
      cb(event, payload)


bus = EventBus()

def on_order(event: str, data: dict) -> None:
  if event == "order.created":
    print("notify:", data)


bus.subscribe(on_order)
bus.publish("order.created", {"id": 1})
```

### Пример 6: DI в сервисе

```python
from typing import Protocol


class Mailer(Protocol):
  def send(self, to: str, subject: str) -> None: ...


class UserRepository(Protocol):
  def get_email(self, user_id: int) -> str | None: ...


class WelcomeService:
  def __init__(self, users: UserRepository, mailer: Mailer) -> None:
    self._users = users
    self._mailer = mailer

  def welcome(self, user_id: int) -> bool:
    email = self._users.get_email(user_id)
    if not email:
      return False
    self._mailer.send(email, "Welcome!")
    return True


# Тестовые double
class FakeUsers:
  def get_email(self, user_id: int) -> str | None:
    return "u@example.com" if user_id == 1 else None


class FakeMailer:
  sent: list[tuple[str, str]] = []

  def send(self, to: str, subject: str) -> None:
    FakeMailer.sent.append((to, subject))


svc = WelcomeService(FakeUsers(), FakeMailer())
assert svc.welcome(1) is True
```

### Пример 7: Observer + dataclass events (immutable)

```python
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class PriceChanged:
  symbol: str
  old: float
  new: float


Listener = Callable[[PriceChanged], None]


class Stock:
  def __init__(self, symbol: str, price: float) -> None:
    self.symbol = symbol
    self._price = price
    self._listeners: list[Listener] = []

  def subscribe(self, fn: Listener) -> None:
    self._listeners.append(fn)

  def set_price(self, new: float) -> None:
    old = self._price
    self._price = new
    event = PriceChanged(self.symbol, old, new)
    for fn in self._listeners:
      fn(event)
```

Immutable event — безопаснее при async/threads ([Модули 1, 3](01-gil.md)).

### Пример 8: FastAPI-style Depends (концепт)

```python
from typing import Annotated

# Упрощённая имитация — в реальном FastAPI используйте Depends(get_db)

def get_db():
  db = connect()
  try:
    yield db
  finally:
    db.close()


def create_app(get_db_dep=get_db):
  def route_handler(db=Depends(get_db_dep)):
    ...
```

Framework DI снимает бойлерplate, но зависимости остаются явными в сигнатуре.

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Модуль-singleton | Просто, идиоматично | Глобальное состояние | Конфиг, логгер |
| `__new__` Singleton | Один экземпляр класса | Тесты, threading | Редко: пулы, legacy |
| Simple factory (dict) | Расширяемость | Нет типов без Protocol | Парсеры, плагины |
| Strategy как функция | Минимум кода | Нет состояния у стратегии | Чистые преобразования |
| Strategy как класс | Состояние, DI | Больше файлов | Сложные правила |
| Observer in-process | Низкая латентность | Связность, отладка | UI, доменные события |
| Message bus (Kafka) | Масштаб, durability | Сложность | Микросервисы |
| Constructor DI | Явные зависимости | Длинные `__init__` | Сервисный слой |
| Service Locator | Короткий вызов | Скрытые deps | Избегать в новом коде |
| DI-фреймворк | Wiring из коробки | Магия, learning curve | FastAPI, крупные apps |

## Практические задания

### Задание 1 (базовое): Factory форматов экспорта

**Условие:** реализуйте `export(data: dict, fmt: str) -> bytes` с фабрикой `CSV` и `JSON` через регистр. Новый формат `YAML` добавляется декоратором без изменения `export`.

**Критерии:**

- `export({"a": 1}, "json")` → `b'{"a": 1}'` (порядок ключей может отличаться).
- Неизвестный `fmt` → `ValueError`.
- Каждый exporter — класс с методом `serialize(self, data: dict) -> bytes`.

**Подсказка:** пример 3; Protocol `Exporter`.

---

### Задание 2 (среднее): Strategy доставки

**Условие:** класс `Shipment` с методом `cost(weight_kg: float, strategy: DeliveryStrategy) -> float`. Стратегии: `Standard` (10 + 2*kg), `Express` (25 + 5*kg). Добавьте функциональную стратегию `economy` как callable.

**Критерии:**

- Type checker принимает и классы, и функцию с сигнатурой `(float) -> float` при использовании `Protocol` или `Callable`.
- Unit-тест без сети.

**Подсказка:** [Модуль 7](07-protocols.md) — `Protocol` с `def quote(self, weight_kg: float) -> float`.

---

### Задание 3 (продвинутое): Мини-приложение с DI и Observer

**Условие:** `TaskBoard` хранит задачи; при `add_task` публикует событие. `EmailNotifier` и `MetricsCollector` подписаны. Все зависимости собираются в `build_app()` с явным DI (без глобальных синглтонов).

**Критерии:**

- `build_app(notifier=..., metrics=...)` для тестов.
- События — frozen dataclass.
- Нет mutable default ([Модуль 5](05-object-vulnerabilities.md)).

**Подсказка:** EventBus или список listeners в `TaskBoard`; fake notifier в тесте.

## Эталонные решения

<details>
<summary>Задание 1 — Factory export</summary>

```python
from typing import Callable, Protocol

class Exporter(Protocol):
  def serialize(self, data: dict) -> bytes: ...

_REGISTRY: dict[str, Callable[[], Exporter]] = {}


def register(name: str):
  def wrap(cls):
    _REGISTRY[name] = cls
    return cls
  return wrap


@register("json")
class JsonExporter:
  def serialize(self, data: dict) -> bytes:
    import json
    return json.dumps(data).encode()


@register("csv")
class CsvExporter:
  def serialize(self, data: dict) -> bytes:
    lines = ["key,value"] + [f"{k},{v}" for k, v in data.items()]
    return "\n".join(lines).encode()


def export(data: dict, fmt: str) -> bytes:
  try:
    return _REGISTRY[fmt]().serialize(data)
  except KeyError:
    raise ValueError(fmt) from None
```

</details>

<details>
<summary>Задание 2 — Delivery Strategy</summary>

```python
from typing import Protocol


class DeliveryStrategy(Protocol):
  def quote(self, weight_kg: float) -> float: ...


class Standard:
  def quote(self, weight_kg: float) -> float:
    return 10 + 2 * weight_kg


class Express:
  def quote(self, weight_kg: float) -> float:
    return 25 + 5 * weight_kg


def economy(weight_kg: float) -> float:
  return 5 + weight_kg


class Shipment:
  def cost(self, weight_kg: float, strategy: DeliveryStrategy) -> float:
  # economy не Protocol-совместим по имени метода — обёртка:
    if hasattr(strategy, "quote"):
      return strategy.quote(weight_kg)
    return strategy(weight_kg)  # callable


# Или: отдельный Protocol / overload; для учебника — класс Economy с quote
class Economy:
  def quote(self, weight_kg: float) -> float:
    return economy(weight_kg)
```

</details>

<details>
<summary>Задание 3 — TaskBoard DI</summary>

```python
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TaskAdded:
  task_id: int
  title: str


class EmailNotifier:
  def __init__(self) -> None:
    self.messages: list[str] = []

  def on_event(self, event: TaskAdded) -> None:
    self.messages.append(f"email: {event.title}")


class MetricsCollector:
  def __init__(self) -> None:
    self.count = 0

  def on_event(self, event: TaskAdded) -> None:
    self.count += 1


class TaskBoard:
  def __init__(self, listeners: list) -> None:
    self._tasks: list[str] = []
    self._listeners = listeners
    self._seq = 0

  def add_task(self, title: str) -> int:
    self._seq += 1
    self._tasks.append(title)
    event = TaskAdded(self._seq, title)
    for fn in self._listeners:
      fn(event)
    return self._seq


def build_app(
  notifier: EmailNotifier | None = None,
  metrics: MetricsCollector | None = None,
) -> tuple[TaskBoard, EmailNotifier, MetricsCollector]:
  notifier = notifier or EmailNotifier()
  metrics = metrics or MetricsCollector()
  board = TaskBoard([notifier.on_event, metrics.on_event])
  return board, notifier, metrics
```

</details>

## Вопросы для самопроверки

1. **Почему модуль часто лучше Singleton-класса?**  
   *Ответ:* импорт уже даёт один объект на процесс; проще и привычнее для Python.

2. **Чем Factory отличается от простого `if fmt == "json"`?**  
   *Ответ:* открыт для расширения (регистрация) без изменения клиентского кода.

3. **Strategy как функция — когда недостаточно?**  
   *Ответ:* когда стратегии хранят состояние или нужны несколько связанных методов.

4. **Риск Observer без weakref?**  
   *Ответ:* утечки памяти, если subject держит ссылки на умершие observers.

5. **Зачем DI, если можно `import db`?**  
   *Ответ:* тестируемость, явные зависимости, нет скрытого global state ([Модуль 5](05-object-vulnerabilities.md)).

6. **Связь Strategy и Protocol?**  
   *Ответ:* Protocol формализует контракт стратегии без наследования ([Модуль 7](07-protocols.md)).

7. **Когда паттерн вреден?**  
   *Ответ:* преждевременная абстракция, один сценарий — YAGNI.

## Методические указания

### Для преподавателя

- Начните с рефакторинга «God class» с `if type ==` → Strategy + Factory.
- Покажите тест `WelcomeService` с fake — мгновенная ценность DI.
- Обсудите: Django уже использует многие идеи (signals ≈ Observer).
- Предупредите: Singleton в интервью ≠ Singleton в продакшене Python.

### Для студента

- Перед классом спросите: «Можно ли функцией?»
- Рисуйте граф зависимостей при DI — циклы видны сразу.
- Сопоставьте с Go (interface + struct) и Rust (trait) — переносимые идеи.

### Интеграция с курсом

| Модуль | Связь |
|--------|-------|
| [04 ООП](04-oop.md) | Наследование vs композиция |
| [05 Уязвимости](05-object-vulnerabilities.md) | Глобальный mutable state |
| [06 TypeVar](06-mutations-typevar.md) | Generic Repository |
| [07 Protocols](07-protocols.md) | Strategy, Repo, Mailer |
| [03 asyncio](03-asyncio.md) | Async Observer, очереди |

## Дополнительные материалы

- *Gang of Four* — оригинальный каталог (читать с фильтром «Python is not Java»).
- *Architecture Patterns with Python* (Percival & Gregory) — DI, Repository, Unit of Work.
- [dependency-injector](https://python-dependency-injector.ets-labs.org/) — контейнер DI.
- FastAPI: [Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/).
- Статья: *Python Patterns* (wiki.python.org) — краткий справочник.
