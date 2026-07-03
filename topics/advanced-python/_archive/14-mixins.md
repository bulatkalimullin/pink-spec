# Модуль 14. Миксины (Mixin Classes)

> Паттерн композиции поведения через множественное наследование: проектирование миксин-классов, кооперативный `super()`, пример `LoggerMixin` и критерии «когда использовать / когда избегать».

## Метаданные

| Параметр | Значение |
|----------|----------|
| Номер модуля | 14 |
| Название | Миксины (Mixin Classes) |
| Предварительные знания | Модуль 13 (MRO и super()), модуль 04 (ООП) |
| Следующий модуль | [15-slots.md](15-slots.md) — `__slots__` |
| Ориентировочное время | 4–5 часов |
| Версия Python | 3.11+ |
| Сложность | Средняя |

## Цели обучения

После прохождения модуля студент сможет:

1. Определить, что такое миксин и чем он отличается от обычного базового класса.
2. Спроектировать миксин с кооперативным `super()` для встраивания в цепочку MRO.
3. Реализовать `LoggerMixin` и подключить его к доменным классам без нарушения иерархии.
4. Распознать антипаттерны: «God mixin», миксины с состоянием, нарушение LSP.
5. Выбрать между миксином, композицией и декоратором в конкретной задаче.
6. Проверить корректность MRO при добавлении миксинов к существующей иерархии.

## Теория

### 14.1. Что такое миксин

**Миксин (mixin)** — класс, который предоставляет **дополнительное поведение** другим классам через наследование, но **не предназначен** для самостоятельного инстанцирования. Миксин — это «ингредиент», а не «блюдо».

Признаки миксина:

- Не имеет полноценной доменной идентичности (`User`, `Order` — не миксины).
- Добавляет узкую функциональность: логирование, сериализация, сравнение, кэширование.
- Обычно стоит **левее** (раньше в списке баз) основного класса в объявлении.
- Часто абстрактен или «пуст» без других баз: `class LoggerMixin:` без `__init__`, если не участвует в кооперативной цепочке.

```python
class JsonSerializableMixin:
    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

class Product:
    def __init__(self, name: str, price: float) -> None:
        self.name = name
        self.price = price

class ExportableProduct(JsonSerializableMixin, Product):
    pass
```

### 14.2. Миксин vs базовый класс vs интерфейс

| Понятие | Роль | Инстанцирование | Пример |
|---------|------|-----------------|--------|
| Базовый класс | Общая доменная логика | Да (иногда ABC) | `Animal`, `BaseModel` |
| Миксин | Переиспользуемое поведение | Нет (конвенция) | `LoggerMixin` |
| ABC / Protocol | Контракт | Нет | `Iterable`, `Protocol` |

В Python нет ключевого слова `mixin` — это **соглашение об именовании** (`*Mixin`) и дисциплина проектирования.

### 14.3. Порядок наследования и MRO

Миксины размещают **слева** от основного класса:

```python
class Service(LoggerMixin, MetricsMixin, BaseService):
    pass
```

MRO: `Service → LoggerMixin → MetricsMixin → BaseService → ...`

При вызове `super()` в `LoggerMixin` управление передаётся `MetricsMixin`, затем `BaseService`. Это требует **кооперативного стиля** из модуля 13.

### 14.4. LoggerMixin: канонический пример

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

class LoggerMixin:
    """Миксин для структурированного логирования операций объекта."""

    _log_namespace: str = "app"

    @property
    def logger(self) -> logging.Logger:
        name = f"{self._log_namespace}.{self.__class__.__name__}"
        return logging.getLogger(name)

    def log_info(self, message: str, **extra: Any) -> None:
        self.logger.info(message, extra=self._log_extra(**extra))

    def log_error(self, message: str, **extra: Any) -> None:
        self.logger.error(message, extra=self._log_extra(**extra))

    def _log_extra(self, **fields: Any) -> dict[str, Any]:
        return {
            "object_id": id(self),
            "class": self.__class__.__name__,
            "ts": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
```

**Использование:**

```python
class OrderService(LoggerMixin):
    _log_namespace = "commerce"

    def create_order(self, user_id: int, items: list[str]) -> dict:
        self.log_info("creating order", user_id=user_id, item_count=len(items))
        order = {"id": 1, "user_id": user_id, "items": items}
        self.log_info("order created", order_id=order["id"])
        return order
```

### 14.5. Миксин с кооперативным __init__

Если миксин должен участвовать в инициализации:

```python
class InitLoggerMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log_info("instance initialized")

class TimestampedMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.created_at = datetime.now(timezone.utc)

class Entity:
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

class Document(InitLoggerMixin, TimestampedMixin, Entity):
    pass
```

**Важно:** `Entity.__init__` тоже должен вызывать `super().__init__()`, иначе цепочка оборвётся.

### 14.6. Миксины и ABC

Миксины часто комбинируют с абстрактными базовыми классами:

```python
from abc import ABC, abstractmethod

class RepositoryMixin:
    def find_by_id(self, id: int):
        self.log_info("find_by_id", id=id)
        return self._fetch(id)

    def _fetch(self, id: int):
        raise NotImplementedError

class UserRepository(LoggerMixin, RepositoryMixin, ABC):
    @abstractmethod
    def _fetch(self, id: int) -> dict | None:
        ...
```

### 14.7. Когда использовать миксины

**Подходящие сценарии:**

- Одинаковое **сквозное** поведение в несвязанных классах (логирование, метрики, repr).
- Django: `LoginRequiredMixin`, `ListView` — классический пример из фреймворка.
- Небольшие, **stateless** или почти stateless миксины.
- Когда нужна интеграция на уровне **методов экземпляра**, а не отдельного сервиса.

**Примеры из экосистемы:**

- `django.contrib.auth.mixins.LoginRequiredMixin`
- `rest_framework mixins`: `ListModelMixin`, `CreateModelMixin`
- Пользовательские: `CacheableMixin`, `AuditableMixin`

### 14.8. Когда избегать миксинов

**Антипаттерны и риски:**

| Проблема | Описание | Альтернатива |
|----------|----------|--------------|
| God mixin | Один миксин на 500+ строк, «всё обо всём» | Разбить; композиция |
| Скрытое состояние | Миксин пишет в `self._cache` без документации | Явный атрибут или композиция |
| Конфликт имён методов | Два миксина с `save()` | Переименование; делегирование |
| Нарушение LSP | Миксин предполагает атрибут, которого нет у потомка | ABC с `@abstractmethod` |
| Сложный MRO | 5+ миксинов у одного класса | Facade, dependency injection |
| Тестирование | Трудно изолировать поведение миксина | Отдельный класс-helper |

**Правило большого пальца:** если миксин требует знать **более трёх** атрибутов хост-класса — рассмотрите композицию.

### 14.9. Миксин vs композиция vs декоратор

```python
# Миксин
class Service(LoggerMixin):
    def run(self): self.log_info("run")

# Композиция
class Service:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

# Декоратор
def logged(fn):
    def wrapper(self, *a, **kw):
        self.logger.info(f"call {fn.__name__}")
        return fn(self, *a, **kw)
    return wrapper
```

| Критерий | Миксин | Композиция | Декоратор |
|----------|--------|------------|-----------|
| Явность зависимостей | Низкая | Высокая | Средняя |
| Переиспользование | Через наследование | Через DI | На функции/методы |
| MRO-сложность | Есть | Нет | Нет |
| Подходит для | Шаблоны фреймворка | Сервисный слой | Точечное обогащение |

### 14.10. Проектирование стабильного API миксина

Рекомендации:

1. **Префикс имён:** `_log_extra`, не `extra` — меньше коллизий.
2. **Документируйте требования:** «хост должен иметь атрибут `id`».
3. **Один миксин — одна ответственность** (SRP).
4. **Тестируйте миксин** на минимальном хост-классе-заглушке.
5. **Не создавайте циклических зависимостей** между миксинами.

```python
class MinimalHost(LoggerMixin):
    pass

def test_logger_mixin():
    host = MinimalHost()
    assert hasattr(host, "log_info")
```

## Примеры кода

### Пример 1. ReprMixin для отладки

```python
class ReprMixin:
  def __repr__(self) -> str:
      attrs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
      return f"{self.__class__.__name__}({attrs})"

class Point(ReprMixin):
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

print(Point(1, 2))  # Point(x=1, y=2)
```

### Пример 2. EqualityMixin

```python
class EqualityMixin:
    _eq_fields: tuple[str, ...] = ()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return all(getattr(self, f) == getattr(other, f) for f in self._eq_fields)

class Money(EqualityMixin):
    _eq_fields = ("amount", "currency")

    def __init__(self, amount: float, currency: str) -> None:
        self.amount = amount
        self.currency = currency
```

### Пример 3. Комбинирование трёх миксинов

```python
class App(
    LoggerMixin,
    ReprMixin,
    EqualityMixin,
):
    _eq_fields = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name
        self.log_info("app created", name=name)

a1 = App("api")
a2 = App("api")
assert a1 == a2
```

### Пример 4. Миксин с opt-in конфигурацией

```python
class VerboseMixin:
    verbose: bool = False

    def _vlog(self, msg: str) -> None:
        if self.verbose:
            print(f"[{self.__class__.__name__}] {msg}")

class Worker(VerboseMixin):
    verbose = True

    def work(self) -> None:
        self._vlog("working...")
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Миксин | DRY, привычен во фреймворках | Скрытые зависимости, MRO | Django/DRF-стиль CBV |
| Композиция (has-a) | Явные зависимости, проще тесты | Больше кода | Микросервисы, чистая архитектура |
| Декоратор | Минимальное вмешательство | Не для всего состояния | Логирование вызовов методов |
| Наследование от одной базы | Простой MRO | Жёсткая иерархия | Единый домен |
| Protocol + функции | Гибкость без наследования | Нет готовых реализаций | Duck typing, typing |

## Практические задания

### Задание 1 (базовое). ReprMixin

Создайте миксин `ReprMixin`, который формирует `__repr__` из публичных атрибутов экземпляра (не начинающихся с `_`).

Подключите к классам `User(id, name)` и `Config(debug, host)`.

**Критерии:** корректный repr, миксин не ломает наследование от других классов.

### Задание 2 (среднее). LoggerMixin + кооперативный init

Реализуйте полный `LoggerMixin` (как в теории) и класс `PaymentProcessor(LoggerMixin, BaseProcessor)`:

```python
class BaseProcessor:
    def __init__(self, processor_id: str) -> None:
        super().__init__()
        self.processor_id = processor_id
```

`LoggerMixin` должен логировать `"processor ready"` после полной инициализации.

**Критерии:** один вызов `BaseProcessor.__init__`, лог после установки `processor_id`.

### Задание 3 (продвинутое). Auditable CRUD

Спроектируйте:

- `AuditableMixin` — методы `_audit(action, **data)` пишут в список `self._audit_log`.
- `CrudMixin` — `create(data)`, `read(id)`, `update(id, data)`, `delete(id)` с вызовом `_audit`.
- `InMemoryStore(CrudMixin, AuditableMixin)` — хранение в `dict`.

Требования: кооперативный MRO, тест на порядок записей в audit log при `create` → `update` → `delete`.

## Эталонные решения

<details>
<summary>Задание 1 — решение</summary>

```python
class ReprMixin:
    def __repr__(self) -> str:
        public = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        inner = ", ".join(f"{k}={v!r}" for k, v in public.items())
        return f"{self.__class__.__name__}({inner})"

class User(ReprMixin):
    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name

class Config(ReprMixin):
    def __init__(self, debug: bool, host: str) -> None:
        self.debug = debug
        self.host = host

assert repr(User(1, "Ann")) == "User(id=1, name='Ann')"
```

</details>

<details>
<summary>Задание 2 — решение</summary>

```python
import logging
from datetime import datetime, timezone
from typing import Any

class LoggerMixin:
    _log_namespace = "app"

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"{self._log_namespace}.{self.__class__.__name__}")

    def log_info(self, message: str, **extra: Any) -> None:
        self.logger.info(message, extra={"ts": datetime.now(timezone.utc).isoformat(), **extra})

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log_info("processor ready", processor_id=getattr(self, "processor_id", None))

class BaseProcessor:
    def __init__(self, processor_id: str) -> None:
        super().__init__()
        self.processor_id = processor_id

class PaymentProcessor(LoggerMixin, BaseProcessor):
    pass

p = PaymentProcessor("pay-1")
assert p.processor_id == "pay-1"
```

</details>

<details>
<summary>Задание 3 — решение</summary>

```python
from __future__ import annotations

class AuditableMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._audit_log: list[dict] = []

    def _audit(self, action: str, **data) -> None:
        self._audit_log.append({"action": action, **data})

class CrudMixin:
    def create(self, data: dict) -> int:
        new_id = self._next_id()
        self._storage[new_id] = data
        self._audit("create", id=new_id, data=data)
        return new_id

    def read(self, id: int) -> dict | None:
        item = self._storage.get(id)
        self._audit("read", id=id, found=item is not None)
        return item

    def update(self, id: int, data: dict) -> bool:
        if id not in self._storage:
            self._audit("update", id=id, success=False)
            return False
        self._storage[id] = data
        self._audit("update", id=id, success=True)
        return True

    def delete(self, id: int) -> bool:
        if id not in self._storage:
            self._audit("delete", id=id, success=False)
            return False
        del self._storage[id]
        self._audit("delete", id=id, success=True)
        return True

class InMemoryStore(CrudMixin, AuditableMixin):
    def __init__(self) -> None:
        self._storage: dict[int, dict] = {}
        self._counter = 0
        super().__init__()

    def _next_id(self) -> int:
        self._counter += 1
        return self._counter

store = InMemoryStore()
uid = store.create({"name": "test"})
store.update(uid, {"name": "updated"})
store.delete(uid)
actions = [e["action"] for e in store._audit_log]
assert actions == ["create", "update", "delete"]
```

</details>

## Вопросы для самопроверки

1. Чем миксин отличается от обычного базового класса?
2. Почему миксины размещают слева в объявлении класса?
3. Зачем `LoggerMixin.__init__` вызывает `super().__init__()`?
4. Назовите три ситуации, когда миксин уместен, и три — когда лучше композиция.
5. Что такое «God mixin» и как его избежать?
6. Как протестировать миксин изолированно?
7. Может ли миксин быть без суффикса `Mixin`? Должен ли?
8. Как конфликт имён методов в двух миксинах разрешается MRO?

<details>
<summary>Ответы</summary>

1. Миксин не предназначен для самостоятельного использования, добавляет узкое поведение.
2. Чтобы его методы имели приоритет и MRO шёл: Mixin → ... → Base.
3. Для кооперативной цепочки инициализации с другими базами.
4. Уместен: логирование, repr, фреймворк CBV. Композиция: сервисы, сложные зависимости, тестируемость.
5. Миксин с чрезмерной ответственностью — разбить на несколько или вынести в сервис.
6. Минимальный host-класс `class Host(MyMixin): pass` + unit-тесты.
7. Может быть без суффикса (конвенция); суффикс улучшает читаемость.
8. Побеждает метод класса, который раньше в MRO.

</details>

## Методические указания для преподавателя

### Структура занятия

1. Повторение MRO/super() (15 мин) — без этого миксины непонятны.
2. Live-coding `LoggerMixin` (30 мин).
3. Разбор Django `LoginRequiredMixin` как реального примера (20 мин).
4. Дискуссия «миксин vs композиция» (25 мин).
5. Практика (остальное время).

### Демонстрация антипаттерна

Покажите класс с 4 миксинами и конфликтующими `save()` — студенты увидят хрупкость MRO.

### Критерии оценки заданий

| Задание | Баллы | Ключевые точки |
|---------|-------|----------------|
| 1 | 20 | Рабочий repr, фильтрация `_` |
| 2 | 35 | Кооперативный init, один Base init |
| 3 | 45 | Audit log, CRUD, MRO |

## Дополнительные материалы

- Django docs: [Class-based views mixins](https://docs.djangoproject.com/en/stable/topics/class-based-views/mixins/)
- DRF: [Generic views mixins](https://www.django-rest-framework.org/api-guide/generic-views/)
- *Fluent Python*, 2nd ed. — раздел о миксинах и cooperative inheritance
- Статья: «Mixins considered harmful?» — дискуссионное чтение для семинара
