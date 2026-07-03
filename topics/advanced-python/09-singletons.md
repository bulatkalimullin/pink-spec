# Модуль 9: Синглтоны

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 9 |
| Предварительные знания | [Модуль 8: Магические методы](08-oop-magic-methods.md), базовое ООП (модули 01–08) |
| Предыдущий модуль | [08-oop-magic-methods.md](08-oop-magic-methods.md) |
| Следующий модуль | [10-dataclasses.md](10-dataclasses.md) |
| Ориентировочное время | 4–5 часов |
| Версия Python | 3.11+ |
| Ключевые темы | Singleton, модуль как синглтон, `__new__`, метакласс, Borg, thread-safety, DI vs глобальное состояние |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Объяснить** проблему «ровно один экземпляр» и отличить её от обычного глобального состояния.
2. **Реализовать** Singleton идиоматичными для Python способами: модуль, `__new__`, декоратор, метакласс, Borg.
3. **Оценить** trade-offs Singleton: тестируемость, скрытые зависимости, thread-safety, pickle/multiprocessing.
4. **Выбрать** между Singleton, Dependency Injection и явной передачей объекта в конструктор.
5. **Применять** frozen `@dataclass` и модульный подход вместо «тяжёлого» Singleton-класса там, где это уместно.
6. **Писать** тесты для кода, который исторически использует Singleton, без глобального загрязнения состояния.

---

## Теория

### 9.1 Что такое Singleton и зачем он нужен

**Singleton (одиночка)** — паттерн, гарантирующий, что у класса существует **не более одного экземпляра** в заданной области видимости (обычно — один процесс Python).

Типичные сценарии:

- конфигурация приложения (DSN, feature flags);
- пул соединений к БД (один пул на процесс);
- логгер с общими handlers (часто решается иначе — `logging.getLogger`);
- счётчик или кэш «на всё приложение».

**Важно:** Singleton решает проблему **координации доступа к единственному ресурсу**, а не проблему «мне лень передавать аргументы». Если объект не обязан быть единственным — паттерн не нужен.

### 9.2 Python ≠ Java: модуль уже синглтон

В CPython при `import config` модуль загружается **один раз** на процесс и кэшируется в `sys.modules`. Любой последующий `import config` возвращает тот же объект модуля.

```python
# app/config.py
DATABASE_URL = "postgresql://localhost/app"
DEBUG = False
```

Это **де-факто Singleton** без класса, метакласса и `get_instance()`. Сообщество Python считает такой подход **предпочтительным** для конфигурации и простого глобального состояния.

**Плюсы модуля:**

- идиоматично, читаемо;
- легко monkeypatch в тестах (`monkeypatch.setattr("app.config.DATABASE_URL", ...)`);
- нет магии в `__new__`.

**Минусы:**

- всё ещё глобальное состояние ([Модуль 5](05-object-vulnerabilities.md));
- импорт может иметь побочные эффекты при загрузке модуля.

### 9.3 Анти-паттерны Singleton в Python

| Анти-паттерн | Почему плохо |
|--------------|--------------|
| `get_instance()` по всему коду | Скрытая зависимость, сложные тесты |
| Double-checked locking «как в Java» | Избыточно; в Python есть GIL, но это не отменяет гонок на уровне логики |
| Singleton «на всякий случай» | YAGNI; усложняет архитектуру без выгоды |
| Mutable singleton без синхронизации | Гонки в `threading` ([Модуль 12](12-concurrent-processes.md)) |
| Singleton в multiprocessing | **Каждый процесс** — свой экземпляр; иллюзия «глобальности» на весь кластер |

### 9.4 Singleton через `__new__`

Переопределение `__new__` позволяет контролировать **создание** экземпляра до вызова `__init__`.

```python
class DatabasePool:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Подводные камни:**

- `__init__` вызывается при **каждом** «конструировании» — даже когда возвращается существующий экземпляр. Часто оставляют `__init__` пустым или с guard-флагом `_initialized`.
- Разные аргументы в «втором» вызове конструктора игнорируются — источник багов.
- Наследование ломает простую схему с одним `_instance` на класс — нужна отдельная логика для подклассов.
- `pickle` и `copy` могут создать второй экземпляр, если не переопределить протокол.

### 9.5 Thread-safe ленивая инициализация

При ленивом создании Singleton из нескольких потоков без синхронизации два потока могут одновременно пройти проверку `if _instance is None` и создать два объекта (до того как один запишет в `_instance`).

**Решение в Python:**

```python
import threading

_lock = threading.Lock()

def __new__(cls):
    if cls._instance is None:
        with _lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
    return cls._instance
```

GIL не заменяет `Lock` для **логики приложения**: между проверкой и присваиванием другой поток может выполнить свой код.

Для **простой** инициализации на старте приложения (до потоков) lock часто не нужен — создайте экземпляр при импорте модуля.

### 9.6 Декоратор `@singleton`

Декоратор оборачивает класс и возвращает функцию-фабрику, которая всегда отдаёт один экземпляр:

```python
def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance
```

Удобно для учебных примеров; в продакшене чаще модуль или явный DI.

### 9.7 Метакласс Singleton

Метакласс перехватывает вызов `Class()` на уровне создания класса:

```python
class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
```

**Плюс:** несколько классов-Singleton без копирования `__new__`.  
**Минус:** «магия», сложнее для новичков и статического анализа.

### 9.8 Паттерн Borg (Monostate)

**Borg** — не один объект, а **общее состояние** между экземплярами:

```python
class Borg:
    _shared_state = {}

    def __init__(self):
        self.__dict__ = self._shared_state
```

Все экземпляры разделяют один `__dict__`. Снаружи выглядит как несколько объектов, внутри — одно состояние.

Иногда Borg предпочтительнее классического Singleton: можно наследовать, не ломая `__new__`. Минус — неочевидная семантика для читателя кода.

### 9.9 Singleton и `@dataclass`

Для **неизменяемой** конфигурации комбинируйте модуль + frozen dataclass ([Модуль 10](10-dataclasses.md)):

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    debug: bool = False

settings = Settings(database_url="postgresql://localhost/app")
```

Один объект `settings` на модуль — по сути Singleton без паттерна. `frozen=True` снижает риск случайной мутации ([Модуль 5](05-object-vulnerabilities.md)).

### 9.10 Dependency Injection вместо Singleton

**Рекомендация курса:** если объект нужен многим компонентам, **передавайте его явно** (constructor injection), а не вызывайте `DatabasePool.get_instance()`.

```python
class OrderService:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool
```

В тестах подставляете `FakePool`. В приложении собираете граф зависимостей в `main()` или DI-контейнере (см. [Модуль 21](21-design-patterns.md)).

Singleton оправдан, когда:

- сторонняя библиотека требует единственный контекст;
- legacy-код уже построен вокруг `get_instance()`;
- объект действительно привязан к ресурсу ОС «один на процесс» и скрывать это бессмысленно.

### 9.11 Singleton и multiprocessing

`multiprocessing` порождает **отдельные процессы** с отдельной памятью. Singleton в родительском процессе **не разделяется** с дочерними после `fork`/`spawn` так, как вы ожидаете: у каждого процесса свой `_instance`.

Для общего состояния между процессами используйте `multiprocessing.Manager`, Redis, БД — не Singleton-класс в памяти.

### 9.12 Тестирование Singleton

Стратегии:

1. **Не использовать Singleton** — лучшая стратегия для нового кода.
2. **`reset_for_tests()`** — `@classmethod`, обнуляющий `_instance` (осторожно с порядком тестов).
3. **Monkeypatch** модуля или атрибута `_instance`.
4. **Фикстура pytest** с autouse, сбрасывающая состояние после каждого теста.
5. **Подмена фабрики** в DI — предпочтительно.

Изоляция тестов важнее «красоты» паттерна.

---

## Примеры кода

### Пример 1: Модуль-синглтон (предпочтительный способ)

```python
# app/settings.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    debug: bool = False
    max_connections: int = 10


settings = Settings(
    database_url="postgresql://localhost/app",
    debug=False,
)
```

```python
# app/db.py
from app.settings import settings


def connection_string() -> str:
    return settings.database_url
```

### Пример 2: Singleton через `__new__` с lock

```python
import threading


class DatabasePool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, dsn: str, max_size: int = 5):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._dsn = dsn
                    inst._max_size = max_size
                    inst._connections: list = []
                    cls._instance = inst
        return cls._instance

    def __init__(self, dsn: str, max_size: int = 5):
        pass  # инициализация только в __new__

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._instance = None


pool_a = DatabasePool("postgres://primary", max_size=10)
pool_b = DatabasePool("postgres://ignored")
assert pool_a is pool_b
assert pool_a._dsn == "postgres://primary"
```

### Пример 3: Декоратор singleton

```python
from functools import wraps


def singleton(cls):
    instances: dict[type, object] = {}
    lock = __import__("threading").Lock()

    @wraps(cls)
    def get_instance(*args, **kwargs):
        with lock:
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    get_instance.reset = lambda: instances.pop(cls, None)
    return get_instance


@singleton
class AppContext:
    def __init__(self, app_name: str) -> None:
        self.app_name = app_name


ctx = AppContext("myapp")
ctx2 = AppContext("other")
assert ctx is ctx2
assert ctx.app_name == "myapp"
```

### Пример 4: Метакласс SingletonMeta

```python
class SingletonMeta(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class Logger(metaclass=SingletonMeta):
    def __init__(self, name: str = "app") -> None:
        self.name = name
        self.messages: list[str] = []

    def info(self, msg: str) -> None:
        self.messages.append(msg)


log1 = Logger("first")
log2 = Logger("second")
assert log1 is log2
assert log1.name == "first"
```

### Пример 5: Borg (общее состояние)

```python
class Configuration:
    _shared_state: dict = {}

    def __init__(self) -> None:
        self.__dict__ = self._shared_state
        if not self._shared_state:
            self.theme = "light"
            self.locale = "ru"


cfg_a = Configuration()
cfg_b = Configuration()
cfg_a.theme = "dark"
assert cfg_b.theme == "dark"
assert cfg_a is not cfg_b  # разные объекты, общий state
```

### Пример 6: DI вместо Singleton

```python
from typing import Protocol


class ConnectionPool(Protocol):
    def acquire(self) -> object: ...


class PostgresPool:
    def __init__(self, dsn: str, size: int = 5) -> None:
        self._dsn = dsn
        self._size = size

    def acquire(self) -> object:
        return f"conn:{self._dsn}"


class UserRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_user(self, user_id: int) -> str:
        conn = self._pool.acquire()
        return f"user_{user_id} via {conn}"


def build_app(dsn: str) -> UserRepository:
    pool = PostgresPool(dsn)
    return UserRepository(pool)


# Тест
class FakePool:
    def acquire(self) -> object:
        return "fake"


repo = UserRepository(FakePool())
assert "fake" in repo.get_user(1)
```

---

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Модуль + константы | Идиоматично, просто | Глобальное состояние | Конфиг, флаги |
| Модуль + frozen dataclass | Immutable, типизация | Всё ещё глобальный импорт | Настройки приложения |
| `__new__` Singleton | Один экземпляр класса | `__init__` на каждый вызов, тесты | Legacy, пулы (редко) |
| Декоратор / метакласс | DRY для нескольких классов | Магия, сложнее отладка | Учебные проекты, фреймворки |
| Borg | Гибче наследование | Неочевидная семантика | Shared config object |
| DI (constructor) | Тестируемость, явные deps | Длинные конструкторы | Сервисный слой, новый код |
| `enum.Enum` | Единственность констант | Не для mutable state | Режимы, статусы |
| Процессный singleton | Один пул на процесс | Не работает между процессами | Локальный ресурс ОС |

---

## Практические задания

### Задание 1 (базовое): Конфигурация через модуль

**Условие:** создайте пакет `app` с модулем `config.py`. Класс `AppConfig` — `@dataclass(frozen=True, slots=True)` с полями `host: str`, `port: int`, `debug: bool = False`. Экспортируйте единственный объект `config`. Модуль `main.py` импортирует `config` и печатает `f"{config.host}:{config.port}"`.

**Критерии:**

- Повторный `import config` не создаёт новый объект (проверка `is`).
- `frozen=True` — попытка `config.port = 9000` вызывает ошибку.
- Нет класса с `get_instance()`.

**Подсказка:** пример 1; [Модуль 10](10-dataclasses.md) для dataclass.

---

### Задание 2 (среднее): Thread-safe счётчик-одиночка

**Условие:** класс `MetricsRegistry` — Singleton через `__new__` + `threading.Lock`. Методы: `increment(name: str, value: int = 1) -> None`, `get(name: str) -> int`, `snapshot() -> dict[str, int]`. Запустите 8 потоков, каждый делает 10_000 `increment("requests")`, итог должен быть ровно 80_000.

**Критерии:**

- `MetricsRegistry()` в разных потоках возвращает один объект.
- Метод `reset_for_tests()` для изоляции тестов.
- Без гонок на итоговом счётчике.

**Подсказка:** пример 2; `Lock` при изменении внутреннего `dict`.

---

### Задание 3 (продвинутое): Рефакторинг Singleton → DI

**Условие:** дан legacy-код:

```python
class CacheSingleton:
    _inst = None
    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
            cls._inst._data = {}
        return cls._inst
    def get(self, key): return self._data.get(key)
    def set(self, key, val): self._data[key] = val

class ProductService:
    def price(self, sku: str) -> float:
        cache = CacheSingleton()
        if cache.get(sku) is not None:
            return cache.get(sku)
        price = ...  # «загрузка из БД»
        cache.set(sku, price)
        return price
```

Рефакторите: интерфейс `Cache` (Protocol), `ProductService(cache: Cache)`, фабрика `build_product_service(cache=None)`. Тест с `FakeCache` без Singleton.

**Критерии:**

- Нет вызова `CacheSingleton()` в `ProductService`.
- Unit-тест проверяет, что БД «не вызывается» при попадании в кэш.
- Сохраните опциональный `InMemoryCache` как реализацию по умолчанию в `build_product_service`.

**Подсказка:** [Модуль 7](07-protocols.md), пример 6.

---

## Эталонные решения

<details>
<summary>Задание 1 — config module</summary>

```python
# app/config.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppConfig:
    host: str
    port: int
    debug: bool = False


config = AppConfig(host="127.0.0.1", port=8000)
```

```python
# app/main.py
from app.config import config

if __name__ == "__main__":
    print(f"{config.host}:{config.port}")
```

```python
# test_config.py
import app.config as cfg1
import app.config as cfg2

assert cfg1.config is cfg2.config
```

</details>

<details>
<summary>Задание 2 — MetricsRegistry</summary>

```python
import threading
from threading import Thread


class MetricsRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._counters: dict[str, int] = {}
                    inst._data_lock = threading.Lock()
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        pass

    def increment(self, name: str, value: int = 1) -> None:
        with self._data_lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def get(self, name: str) -> int:
        with self._data_lock:
            return self._counters.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        with self._data_lock:
            return dict(self._counters)

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            cls._instance = None


if __name__ == "__main__":
    def worker():
        reg = MetricsRegistry()
        for _ in range(10_000):
            reg.increment("requests")

    threads = [Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert MetricsRegistry().get("requests") == 80_000
    print("OK")
```

</details>

<details>
<summary>Задание 3 — DI refactor</summary>

```python
from typing import Protocol


class Cache(Protocol):
    def get(self, key: str) -> float | None: ...
    def set(self, key: str, value: float) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, float] = {}

    def get(self, key: str) -> float | None:
        return self._data.get(key)

    def set(self, key: str, value: float) -> None:
        self._data[key] = value


class ProductService:
    def __init__(self, cache: Cache, loader=None) -> None:
        self._cache = cache
        self._loader = loader or self._default_load

    def _default_load(self, sku: str) -> float:
        return 99.99

    def price(self, sku: str) -> float:
        cached = self._cache.get(sku)
        if cached is not None:
            return cached
        value = self._loader(sku)
        self._cache.set(sku, value)
        return value


def build_product_service(cache: Cache | None = None) -> ProductService:
    return ProductService(cache or InMemoryCache())


# Тест
class FakeCache:
    def __init__(self):
        self._data = {"SKU1": 10.0}
        self.loads = 0

    def get(self, key: str) -> float | None:
        return self._data.get(key)

    def set(self, key: str, value: float) -> None:
        self._data[key] = value


def fake_loader(sku: str) -> float:
    raise AssertionError("DB should not be called")

svc = ProductService(FakeCache(), loader=fake_loader)
assert svc.price("SKU1") == 10.0
```

</details>

---

## Вопросы для самопроверки

1. Почему в Python модуль часто лучше класса-Singleton?
2. Что произойдёт, если вызвать `DatabasePool("a")` и затем `DatabasePool("b")` при Singleton через `__new__`?
3. Зачем `threading.Lock` при ленивой инициализации, если есть GIL?
4. Чем Borg отличается от классического Singleton?
5. Почему Singleton в одном процессе не разделяется между worker-процессами `multiprocessing`?
6. Как протестировать код с `get_instance()` без загрязнения глобального состояния?
7. Когда DI предпочтительнее Singleton?
8. Почему `frozen=True` полезен для объекта конфигурации?
9. Вызывается ли `__init__` при повторном «создании» Singleton?
10. В чём риск mutable Singleton в многопоточном коде?

---

## Методические указания

### Для преподавателя

- Начните с вопроса: «Нужен ли вообще один экземпляр или нужен просто общий доступ?»
- Покажите рефакторинг задания 3 live — студенты видят ценность DI на тестах.
- Сравните с Go (`sync.Once`) и Rust (обычно `lazy_static` / `OnceLock`) — идея та же, идиомы разные.
- Предупредите: на собеседованиях Singleton спрашивают часто, в Python-коде применяют реже.
- Свяжите с [Модулем 5](05-object-vulnerabilities.md): глобальный mutable state — источник багов.

### Для студента

- Перед реализацией Singleton спросите: «Могу ли я передать объект в `__init__`?»
- Рисуйте граф зависимостей: Singleton часто создаёт скрытые стрелки на диаграмме.
- Пишите `reset_for_tests`, если legacy оставляет Singleton — иначе flaky tests.
- Изучите, как ваш фреймворк (Django settings, FastAPI `app.state`) решает «единственность».

### Тайминг: ~4 ч (теория + практика заданий 1–2).

1. Инициализация в `__init__` без guard — перезапись состояния при каждом вызове конструктора.
2. Игнорирование разных аргументов во втором вызове — «тихий» баг с DSN.
3. Singleton для всего подряд — тесты превращаются в интеграционные.
4. Забытый reset между тестами — порядок выполнения влияет на результат.
5. Ожидание «глобального» кэша между процессами без внешнего хранилища.

---

## Дополнительные материалы

### Документация

- [Python import system](https://docs.python.org/3/reference/import.html)
- [dataclasses](https://docs.python.org/3/library/dataclasses.html) — связь с модулем 10
- [threading — Lock objects](https://docs.python.org/3/library/threading.html#lock-objects)

### Статьи

- *The Singleton Pattern in Python* — Real Python
- *Python Patterns: Singleton* — wiki.python.org
- Martin Fowler — «Patterns of Enterprise Application Architecture» (Service Locator vs DI)

### Связь с модулями курса

| Модуль | Связь |
|--------|-------|
| [21 Паттерны](21-design-patterns.md) | Singleton в контексте Factory, DI |
| [05 Уязвимости](05-object-vulnerabilities.md) | Mutable global state |
| [10 Dataclasses](10-dataclasses.md) | frozen config object |
| [12 Процессы](12-concurrent-processes.md) | Singleton не межпроцессный |
| [07 Protocols](07-protocols.md) | Cache, Pool как Protocol для DI |
