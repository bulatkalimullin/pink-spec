# Модуль 28: `__slots__` — оптимизация памяти и ограничения

> Глубокое изучение механизма `__slots__` в Python 3.11+: экономия памяти, влияние на модель объекта, сравнение с `@dataclass`, наследование и подводные камни.

## Метаданные

| Параметр | Значение |
|----------|----------|
| Номер модуля | 15 |
| Название | `__slots__` |
| Предварительные знания | Модуль 04 (ООП), модуль 06 (типизация), базовое понимание модели объектов CPython |
| Следующий модуль | [16-magic-methods.md](16-magic-methods.md) — Магические методы |
| Ориентировочное время | 4–5 часов |
| Версия Python | 3.11+ |
| Сложность | Средняя → продвинутая |

## Цели обучения

После прохождения модуля студент сможет:

1. Объяснить, как `__slots__` меняет внутреннее представление экземпляра в CPython.
2. Оценить экономию памяти при создании большого числа однотипных объектов.
3. Перечислить ограничения `__slots__` (нет `__dict__`, weakref, наследование).
4. Сравнить `@dataclass` и класс со `__slots__` и выбрать подходящий инструмент.
5. Корректно проектировать иерархии классов со `__slots__` и наследованием.
6. Измерить потребление памяти с помощью `sys.getsizeof` и `pympler`/`tracemalloc`.

## Теория

### 15.1. Как Python хранит атрибуты экземпляра

По умолчанию каждый экземпляр пользовательского класса имеет словарь `__dict__`, в котором хранятся атрибуты:

```python
class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

p = Point(1.0, 2.0)
print(p.__dict__)  # {'x': 1.0, 'y': 2.0}
```

**Накладные расходы `__dict__`:**

- Сам dict — отдельный объект в heap (ключи, хеш-таблица).
- Каждый экземпляр хранит ссылку на dict.
- При миллионах мелких объектов (точки, события, записи лога) память растёт существенно.

### 15.2. Что делает `__slots__`

`__slots__` объявляет **фиксированный набор** атрибутов. CPython вместо `__dict__` выделяет массив указателей (descriptor slots) в структуре объекта:

```python
class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

p = Point(1.0, 2.0)
# p.__dict__  # AttributeError: 'Point' object has no attribute '__dict__'
```

**Эффекты:**

- Запрещено добавлять произвольные атрибуты: `p.z = 3` → `AttributeError`.
- Меньше памяти на экземпляр (нет отдельного dict).
- Немного быстрее доступ к атрибутам (фиксированные смещения).

### 15.3. Измерение экономии памяти

```python
import sys

class PointDict:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

class PointSlots:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

def instance_size(cls: type, n: int = 100_000) -> int:
    objs = [cls(0.0, 0.0) for _ in range(n)]
  return sum(sys.getsizeof(o) for o in objs)

# Типично на 64-bit CPython 3.11:
# PointDict ~ 40-56 байт на объект (зависит от версии)
# PointSlots ~ 24-32 байта на объект
```

**Важно:** `sys.getsizeof` не учитывает вложенные объекты (значения float interned). Для точных замеров используйте `pympler.asizeof` или `tracemalloc`.

```python
# pip install pympler
from pympler import asizeof

print(asizeof.asizeof(PointDict(1, 2)))
print(asizeof.asizeof(PointSlots(1, 2)))
```

### 15.4. Синтаксис и варианты объявления

```python
# Кортеж строк
class A:
    __slots__ = ("a", "b")

# Одна строка — тоже корректно
class B:
    __slots__ = "a"

# Пустой slots — блокирует __dict__ без слотов-атрибутов
class C:
    __slots__ = ()
```

**Аннотации типов (Python 3.11+):**

```python
class Point:
    __slots__ = ("x", "y")
    x: float
    y: float
```

### 15.5. Ограничения `__slots__`

| Ограничение | Описание |
|-------------|----------|
| Нет `__dict__` | Нельзя `obj.new_attr = 1` без слота |
| Weak references | Нужен `"__weakref__"` в slots для `weakref.ref(obj)` |
| Pickle | Работает, но кастомные классы требуют осторожности |
| Множественное наследование | Все родители со slots — дочерний тоже должен объявить slots |
| `@dataclass` | По умолчанию использует `__dict__`; `slots=True` с 3.10+ |
| Дескрипторы | Слоты совместимы с `@property` на уровне класса |

**Weakref:**

```python
import weakref

class Node:
    __slots__ = ("value", "__weakref__")
    def __init__(self, value: int) -> None:
        self.value = value

n = Node(42)
r = weakref.ref(n)  # OK
```

### 15.6. Наследование и `__slots__`

**Правило:** если родитель объявил `__slots__`, потомок **должен** объявить свой `__slots__`, иначе у потомка снова появится `__dict__`.

```python
class Base:
    __slots__ = ("a",)

class Child(Base):
    __slots__ = ("b",)  # только НОВЫЕ слоты; 'a' наследуется

class GrandChild(Child):
    __slots__ = ("c",)
```

**Родитель без slots + потомок со slots:**

```python
class Base:
    pass  # имеет __dict__

class Child(Base):
    __slots__ = ("x",)  # у Child нет __dict__, но у Base — есть путь через Base-часть?
```

На практике: если **любой** предок в MRO не объявляет `__slots__`, потомок **получит `__dict__`**, и оптимизация частично теряется. Для полной экономии вся цепочка должна использовать slots.

### 15.7. `__slots__` vs `@dataclass`

С Python 3.10+ dataclass поддерживает `slots=True`:

```python
from dataclasses import dataclass

@dataclass(slots=True)
class Point:
    x: float
    y: float
```

| Критерий | Ручной `__slots__` | `@dataclass` | `@dataclass(slots=True)` |
|----------|-------------------|--------------|--------------------------|
| Boilerplate | Высокий | Низкий | Низкий |
| `__init__`, `__repr__`, `__eq__` | Вручную | Авто | Авто |
| Гибкость slots | Полная | — | Хорошая |
| Наследование | Сложное | Простое | Ограничения как у slots |
| Динамические атрибуты | Нет | Да (без slots) | Нет |
| IDE / typing | Ручные аннотации | Отлично | Отлично |

**Когда dataclass без slots:** прототипы, конфиги, DTO с редким числом экземпляров.

**Когда slots:** hot path, миллионы объектов, фиксированная схема полей.

### 15.8. `__slots__` и дескрипторы

Слоты работают как дескрипторы на уровне типа. Можно комбинировать с `@property`:

```python
class Circle:
    __slots__ = ("_radius",)

    def __init__(self, radius: float) -> None:
        self._radius = radius

    @property
    def radius(self) -> float:
        return self._radius

    @radius.setter
    def radius(self, value: float) -> None:
        if value < 0:
            raise ValueError("radius must be non-negative")
        self._radius = value
```

### 15.9. Когда НЕ использовать `__slots__`

- Классы с **динамическими** атрибутами (`**kwargs` в `__init__`).
- ORM-модели (SQLAlchemy, Django) — фреймворк ожидает `__dict__`.
- Классы, которые наследуют «обычные» классы без slots в глубокой иерархии.
- Преждевременная оптимизация: сначала профилируйте.

**Правило Knuth:** «Premature optimization is the root of all evil» — применимо и здесь.

### 15.10. Производительность: память и скорость

Помимо памяти, slots дают небольшой выигрыш по скорости доступа к атрибутам (меньше indirection). На CPU-bound коде с миллионами обращений разница заметна; на I/O-bound — нет.

```python
import timeit

setup = """
class D:
    def __init__(self):
        self.x = self.y = 0
class S:
    __slots__ = ('x', 'y')
    def __init__(self):
        self.x = self.y = 0
d = D()
s = S()
"""

print(timeit.timeit("d.x; d.y", setup=setup, number=10_000_000))
print(timeit.timeit("s.x; s.y", setup=setup, number=10_000_000))
```

## Примеры кода

### Пример 1. Event с фиксированной схемой

```python
from datetime import datetime

class Event:
    __slots__ = ("timestamp", "name", "payload", "__weakref__")

    def __init__(self, name: str, payload: dict, ts: datetime | None = None) -> None:
        self.timestamp = ts or datetime.now()
        self.name = name
        self.payload = payload
```

### Пример 2. Named tuple vs slots vs dataclass

```python
from collections import namedtuple
from dataclasses import dataclass

RowNT = namedtuple("RowNT", ["id", "value"])
RowDC = dataclass(slots=True)(type("RowDC", (), {"__annotations__": {"id": int, "value": str}}))

class RowSlots:
    __slots__ = ("id", "value")
    def __init__(self, id: int, value: str) -> None:
        self.id = id
        self.value = value
```

`namedtuple` — неизменяемый, самый компактный для простых записей. `dataclass(slots=True)` — изменяемый с автогенерацией методов.

### Пример 3. Ошибка при динамическом атрибуте

```python
class Strict:
    __slots__ = ("a",)

s = Strict()
s.a = 1
try:
    s.b = 2
except AttributeError as e:
    print(e)  # 'Strict' object has no attribute 'b'
```

### Пример 4. Иерархия со slots

```python
class Animal:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

class Dog(Animal):
    __slots__ = ("breed",)

    def __init__(self, name: str, breed: str) -> None:
        super().__init__(name)
        self.breed = breed
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Обычный класс + `__dict__` | Гибкость, простота | Больше памяти | Большинство бизнес-классов |
| `__slots__` | Меньше RAM, быстрее доступ | Жёсткая схема, сложное наследование | Миллионы мелких объектов |
| `@dataclass` | Меньше boilerplate | `__dict__` по умолчанию | DTO, конфиги |
| `@dataclass(slots=True)` | Dataclass + экономия памяти | Ограничения slots | Типизированные record-типы |
| `namedtuple` | Компактность, hashable | Immutable | Ключи, координаты, строки БД |
| `TypedDict` | Только типизация | Не класс, нет инстансов | JSON-структуры |

## Практические задания

### Задание 1 (базовое). Point со slots

Реализуйте `Point2D` со `__slots__` (`x`, `y`) и функцию `benchmark(n)` которая сравнивает `sys.getsizeof` суммарно для `n` объектов `Point2D` и `Point2DDict` (без slots).

Выведите процент экономии памяти.

### Задание 2 (среднее). Иерархия Sensor

```python
# Базовый Sensor: id, kind
# TemperatureSensor(Sensor): celsius
# HumiditySensor(Sensor): percent
```

Все классы со `__slots__`. Реализуйте `read()` возвращающий dict. Убедитесь, что нельзя добавить произвольный атрибут.

### Задание 3 (продвинутое). Event log

Создайте `EventLog` хранящий до 1_000_000 событий класса `Event` (slots: `ts`, `level`, `message`).

Сравните пиковое потребление памяти (через `tracemalloc`) для версии со slots и без. Напишите вывод: при каком `n` slots окупаются на вашей машине.

## Эталонные решения

<details>
<summary>Задание 1 — решение</summary>

```python
import sys

class Point2D:
    __slots__ = ("x", "y")
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y

class Point2DDict:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y

def benchmark(n: int = 10_000) -> None:
    slots_objs = [Point2D(0, 0) for _ in range(n)]
    dict_objs = [Point2DDict(0, 0) for _ in range(n)]
    slots_size = sum(sys.getsizeof(o) for o in slots_objs)
    dict_size = sum(sys.getsizeof(o) for o in dict_objs)
    saved = (1 - slots_size / dict_size) * 100
    print(f"slots: {slots_size}, dict: {dict_size}, saved: {saved:.1f}%")

benchmark()
```

</details>

<details>
<summary>Задание 2 — решение</summary>

```python
class Sensor:
    __slots__ = ("id", "kind")

    def __init__(self, id: str, kind: str) -> None:
        self.id = id
        self.kind = kind

    def read(self) -> dict:
        return {"id": self.id, "kind": self.kind}

class TemperatureSensor(Sensor):
    __slots__ = ("celsius",)

    def __init__(self, id: str, celsius: float) -> None:
        super().__init__(id, "temperature")
        self.celsius = celsius

    def read(self) -> dict:
        return {**super().read(), "celsius": self.celsius}

class HumiditySensor(Sensor):
    __slots__ = ("percent",)

    def __init__(self, id: str, percent: float) -> None:
        super().__init__(id, "humidity")
        self.percent = percent

    def read(self) -> dict:
        return {**super().read(), "percent": self.percent}

t = TemperatureSensor("t1", 22.5)
assert t.read() == {"id": "t1", "kind": "temperature", "celsius": 22.5}
try:
    t.extra = 1
except AttributeError:
    pass
else:
    raise AssertionError("expected AttributeError")
```

</details>

<details>
<summary>Задание 3 — решение</summary>

```python
import tracemalloc
from dataclasses import dataclass

class Event:
    __slots__ = ("ts", "level", "message")
    def __init__(self, ts: float, level: str, message: str) -> None:
        self.ts, self.level, self.message = ts, level, message

@dataclass
class EventDict:
    ts: float
    level: str
    message: str

def peak_memory(factory, n: int) -> int:
    tracemalloc.start()
    log = [factory(float(i), "INFO", "msg") for i in range(n)]
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del log
    return peak

for n in [10_000, 100_000, 500_000]:
    p_slots = peak_memory(lambda ts, l, m: Event(ts, l, m), n)
    p_dict = peak_memory(lambda ts, l, m: EventDict(ts, l, m), n)
    print(f"n={n}: slots={p_slots/1e6:.1f}MB dict={p_dict/1e6:.1f}MB ratio={p_dict/p_slots:.2f}x")
```

</details>

## Вопросы для самопроверки

1. Почему экземпляр со `__slots__` не имеет `__dict__`?
2. Как включить weak references для slotted-класса?
3. Что произойдёт, если потомок не объявит `__slots__`, а родитель объявил?
4. Чем `@dataclass(slots=True)` отличается от ручного `__slots__`?
5. Когда `namedtuple` предпочтительнее slotted-класса?
6. Можно ли использовать `__slots__` с `@property`?
7. Почему ORM-модели обычно не переводят на slots?
8. Достаточно ли `sys.getsizeof` для оценки памяти миллиона объектов?

<details>
<summary>Ответы</summary>

1. CPython хранит атрибуты в фиксированном массиве указателей вместо dict.
2. Добавить `"__weakref__"` в кортеж `__slots__`.
3. У потомка появится `__dict__`, экономия памяти у потомка теряется.
4. Dataclass генерирует `__init__`, `__repr__`, `__eq__` и slots автоматически.
5. Когда нужна неизменяемость и хешируемость простой записи.
6. Да, property работает с приватным слотом `_attr`.
7. Фреймворки полагаются на динамические атрибуты и дескрипторы полей.
8. Нет, лучше `tracemalloc` или `pympler.asizeof` для полной картины.

</details>

## Методические указания для преподавателя

### Практика в аудитории

- Запустите benchmark на проекторе — визуальный эффект убеждает лучше теории.
- Покажите `AttributeError` при `obj.new = 1` — студенты запомнят ограничение.
- Сравните `@dataclass` и `@dataclass(slots=True)` в одном файле.

### Типичные заблуждения

- «slots всегда быстрее» — выигрыш по CPU часто минимален без профилирования.
- «slots в родителе достаточно» — потомок должен объявить свои slots.
- «slots = immutable» — нет, только фиксированный набор полей.

### Связь с модулями

- Модуль 16: магические методы в slotted-классах работают так же.
- Модуль 06: `@dataclass` и typing.
- Модуль 09: Big O — trade-off память vs гибкость.

## Дополнительные материалы

- [Python Data Model — `__slots__`](https://docs.python.org/3/reference/datamodel.html#slots)
- [dataclasses — `slots`](https://docs.python.org/3/library/dataclasses.html#dataclass-slots)
- PEP 487 — `__slots__` и подклассы
- `pympler` documentation
- Raymond Hettinger, «Supercharge your classes with super() and slots» (PyCon)
