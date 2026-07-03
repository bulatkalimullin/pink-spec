# Модуль 20: Протоколы и структурная типизация

## Метаданные

| Параметр | Значение |
|----------|----------|
| Предварительные знания | [Модуль 4: ООП](04-oop.md) — наследование, ABC; [Модуль 6: TypeVar](06-mutations-typevar.md) — `bound`, `Generic` |
| Следующий модуль | [Модуль 8: Паттерны проектирования](08-design-patterns.md) |
| Ориентировочное время | 3–4 ч |

## Цели обучения

1. **Объяснять** разницу между номинальной (наследование) и структурной (`Protocol`) субтипизацией на примерах из стандартной библиотеки.
2. **Объявлять** собственные `typing.Protocol` с методами и атрибутами и **использовать** их в аннотациях вместо конкретных классов.
3. **Применять** `@runtime_checkable` осознанно — зная ограничения проверки только по наличию атрибутов, не по сигнатурам.
4. **Использовать** встроенные протоколы `Iterable`, `Iterator`, `Hashable`, `Sized`, `SupportsFloat` для duck typing с проверкой типов.
5. **Проектировать** API библиотек и тестовых double без принудительного наследования от ABC — в духе [Модуля 8](08-design-patterns.md) (Strategy, DI).

## Теория

### 7.1 Duck typing и его пределы

«Если это ходит как утка и крякает как утка — это утка». В Python интерфейс = **набор методов**, не декларация `implements Duck`.

Без аннотаций:

```python
def render(stream):
  for chunk in stream:
    process(chunk)
```

Работает с `list`, `file`, генератором. Ошибка `AttributeError` — только в runtime.

**Протоколы** сохраняют duck typing, добавляя **статическую проверку** для IDE и mypy/pyright.

### 7.2 Номинальная vs структурная субтипизация

| | Номинальная | Структурная |
|---|-------------|-------------|
| Механизм | Явное наследование `class Dog(Animal)` | «Имеет нужные методы» |
| Python | `abc.ABC`, `class C(ABC)` | `typing.Protocol` |
| Плюс | Явный контракт в MRO | Гибкость, тестовые fakes |
| Минус | Жёсткая иерархия | Сложнее отследить «кто реализует» |

[Модуль 4](04-oop.md) фокусировался на наследовании и полиморфизме. Протоколы — **альтернативный** способ полиморфизма, ближе к Go interfaces и Rust traits (без compile-time enforcement в runtime по умолчанию).

### 7.3 typing.Protocol

```python
from typing import Protocol

class Drawable(Protocol):
  def draw(self) -> None: ...
```

Любой класс с методом `draw(self) -> None` **структурно** подтип `Drawable`, даже без `class Circle(Drawable)`.

Протоколы **не создают** базовый класс в runtime для обычных классов (до `@runtime_checkable` и `isinstance`). Для type checker — это интерфейс.

### 7.4 Синтаксис: методы, атрибуты, readonly

```python
from typing import Protocol

class Named(Protocol):
  name: str  # атрибут экземпляра

class Greeter(Protocol):
  def greet(self, who: str) -> str: ...
```

**ReadOnly** (3.13+) и `typing_extensions` для иммутабельных полей — см. документацию.

### 7.5 @runtime_checkable

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class SupportsLen(Protocol):
  def __len__(self) -> int: ...

isinstance([1, 2], SupportsLen)  # True
```

**Ограничения:**

- Проверяется **наличие** атрибутов по имени, не совместимость сигнатур.
- Не проверяет **типы** аргументов и возврата.
- Для **не** `@runtime_checkable` протоколов `isinstance` всегда False (или TypeError).

Используйте `@runtime_checkable` для границ плагинов; для бизнес-логики предпочтительнее type checker + тесты.

### 7.6 Протоколы и Generic

```python
from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)

class Iterable(Protocol[T_co]):
  def __iter__(self) -> Iterator[T_co]: ...
```

Связь с [Модулем 6](06-mutations-typevar.md): `TypeVar` с `bound=Protocol` ограничивает generic-функции.

### 7.7 Iterable, Iterator, Collection

**Iterable** — объект с `__iter__()` (или `__getitem__` устаревший путь).

```python
from collections.abc import Iterable

def total_length(chunks: Iterable[bytes]) -> int:
  return sum(len(c) for c in chunks)
```

Принимает `list`, `tuple`, генератор, `file.readlines()` iterator.

**Iterator** — объект с `__iter__` (возвращает self) и `__next__`.

Итератор **одноразовый**: после исчерпания нужен новый.

**Collection** = Sized + Iterable + Container.

В Python 3.9+ предпочитайте `collections.abc` вместо `typing.Iterable` в runtime-аннотациях (меньше forward ref проблем).

### 7.8 Hashable

Объект hashable, если:

1. Имеет `__hash__` (не `None`).
2. Имеет `__eq__`.
3. `a == b` → `hash(a) == hash(b)`.
4. Хеш не меняется за время жизни в `dict`/`set`.

| Hashable | Не hashable |
|----------|-------------|
| `int`, `str`, `tuple` (из hashable) | `list`, `dict`, `set` |
| `frozenset` | пользовательский класс с mutable `__eq__` |
| `@dataclass(frozen=True, eq=True)` | обычный mutable объект |

```python
from collections.abc import Hashable

def dedupe(items: Iterable[Hashable]) -> set:
  return set(items)
```

Попытка `set([[1]])` → `TypeError: unhashable type: 'list'`.

**Связь с [Модулем 6](06-mutations-typevar.md):** мутация полей после помещения в `set` нарушает инвариант dict — объект «пропадает».

### 7.9 Протоколы из typing vs collections.abc

`collections.abc` — **реальные ABC** с регистрацией виртуальных подклассов (`VirtualSubclass`).  
`typing.Protocol` — для **статической** проверки; часто дублируют имена.

На практике:

- Публичный API библиотеки: `collections.abc.Sequence`, `Iterable`.
- Узкий контракт только для mypy: свой `Protocol`.

### 7.10 Протоколы vs ABC

```python
from abc import ABC, abstractmethod

class WriterABC(ABC):
  @abstractmethod
  def write(self, data: bytes) -> int: ...
```

Класс **обязан** наследовать `WriterABC`, иначе `isinstance` не сработает как ожидается для ABC (хотя register может помочь).

`Protocol` не требует наследования — удобно для **сторонних** типов (`io.BytesIO`, mock).

### 7.11 Практическое проектирование

1. **Мелкие протоколы** — Interface Segregation (см. [Модуль 8](08-design-patterns.md)).
2. **Не злоупотребляйте `isinstance` с Protocol** — ломает расширяемость.
3. **Тесты:** `class FakeRepo(Protocol)` — просто класс с методами `get`/`save`.
4. **Документируйте** ожидаемые исключения протокола.

### 7.12 Протоколы и безопасность

В [Модуле 5](05-object-vulnerabilities.md) обсуждался `getattr(obj, user_name)`. Протоколы не защищают от injection, но позволяют **явно** описать допустимый интерфейс вместо «любой объект».

## Примеры кода

### Пример 1: Drawable без наследования

```python
from typing import Protocol


class Drawable(Protocol):
  def draw(self) -> None: ...


class Circle:
  def __init__(self, r: float) -> None:
    self.r = r

  def draw(self) -> None:
    print(f"circle r={self.r}")


def paint_all(shapes: list[Drawable]) -> None:
  for s in shapes:
    s.draw()


paint_all([Circle(1), Circle(2)])  # Circle не наследует Drawable
```

### Пример 2: @runtime_checkable

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class HasClose(Protocol):
  def close(self) -> None: ...


class Resource:
  def close(self) -> None:
    print("closed")


class Broken:
  def close(self, extra=None) -> None:  # другая сигнатура
    pass


print(isinstance(Resource(), HasClose))   # True
print(isinstance(Broken(), HasClose))     # True — runtime НЕ проверяет сигнатуру!
print(isinstance(42, HasClose))             # False
```

### Пример 3: Iterable в API

```python
from collections.abc import Iterable


def normalize_paths(paths: Iterable[str]) -> list[str]:
  return [p.strip().lower() for p in paths]


# list, tuple, generator — всё подходит
normalize_paths(p for p in [" /A ", "B "])
```

### Пример 4: Hashable ключи

```python
from collections.abc import Hashable


def index_by_id(rows: Iterable[tuple[Hashable, str]]) -> dict:
  return {key: value for key, value in rows}


index_by_id([(1, "a"), (2, "b")])
# index_by_id([([1], "x")])  # TypeError at runtime
```

### Пример 5: Протокол + TypeVar bound

```python
from typing import Protocol, TypeVar

class SupportsDiv(Protocol):
  def __truediv__(self, other) -> float: ...

T = TypeVar("T", bound=SupportsDiv)


def average_pair(a: T, b: T) -> float:
  return (a + b) / 2  # нужен ещё SupportsAdd — упрощённо через float() в проде
```

Упрощённый учебный фрагмент; в реальности объедините `SupportsFloat` или используйте `numbers.Real`.

### Пример 6: FileLike Protocol

```python
from typing import Protocol


class Readable(Protocol):
  def read(self, n: int = -1) -> bytes: ...


def load_header(stream: Readable, size: int = 8) -> bytes:
  return stream.read(size)


class BytesReader:
  def __init__(self, data: bytes) -> None:
    self._data = data
    self._pos = 0

  def read(self, n: int = -1) -> bytes:
    if n < 0:
      chunk = self._data[self._pos :]
      self._pos = len(self._data)
      return chunk
    chunk = self._data[self._pos : self._pos + n]
    self._pos += n
    return chunk


load_header(BytesReader(b"HEADERPAYLOAD"))
```

### Пример 7: Iterator vs Iterable

```python
from collections.abc import Iterator, Iterable


def consume_once(items: Iterable[int]) -> int:
  it = iter(items)
  return sum(it)


gen = (x for x in range(3))
print(consume_once(gen))  # 3
# print(consume_once(gen))  # 0 — генератор исчерпан
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| `Protocol` | Нет наследования, сторонние типы | Не видно в MRO | Публичные утилиты, DI |
| `abc.ABC` | Явная иерархия, `isinstance` | Жёсткая связь | Framework с hooks |
| `@runtime_checkable` | `isinstance` в плагинах | Ложные срабатывания по сигнатуре | Entry points, плагины |
| `typing.Iterable` | Универсальный вход | Не различает list vs generator | Обход один раз |
| Конкретный класс в аннотации | Просто | Ломает mocks и adapters | Внутренний код |
| `collections.abc` | Виртуальная регистрация | Путаница с typing | Runtime polymorphism |
| Много мелких Protocol | ISP, тестируемость | Шум в импортах | Библиотеки, [Модуль 8](08-design-patterns.md) |

## Практические задания

### Задание 1 (базовое): Protocol Sortable

**Условие:** объявите `Protocol Sortable` с методом `__lt__` и функцию `sort_asc(items: list[Sortable]) -> list[Sortable]`, работающую с `int` и с классом `Product(price: float)` без наследования от Protocol.

**Критерии:**

- Сортировка по возрастанию.
- Type checker доволен вызовом с `list[Product]`.

**Подсказка:** `@dataclass` + `def __lt__(self, other)`.

---

### Задание 2 (среднее): Cache с Hashable ключами

**Условие:** класс `SimpleCache` с методами `get(key: Hashable)`, `set(key: Hashable, value: object)`, `clear()`. Документируйте, почему `list` нельзя использовать как ключ.

**Критерии:**

- `set` + `get` для `str` и `tuple`.
- Попытка `set([1], "x")` даёт понятную ошибку или отклоняется type checker где возможно.

**Подсказка:** `dict[Hashable, object]` внутри; в docstring — инвариант hashable.

---

### Задание 3 (продвинутое): Plugin loader с runtime_checkable

**Условие:** протокол `Plugin` с `name: str` и `run(config: dict) -> None`. Функция `load_plugins(modules: Iterable[object]) -> list[Plugin]` фильтрует объекты через `isinstance(obj, Plugin)`.

**Критерии:**

- Реальный модуль-класс без наследования Plugin попадает в список, если структура совпадает.
- Объект без `run` отфильтровывается.
- Комментарий: почему нельзя полагаться только на runtime check для сигнатуры `run`.

**Подсказка:** `@runtime_checkable`; связь с [Модулем 5](05-object-vulnerabilities.md) — валидация `config`.

## Эталонные решения

<details>
<summary>Задание 1 — Sortable</summary>

```python
from dataclasses import dataclass
from typing import Protocol


class Sortable(Protocol):
  def __lt__(self, other) -> bool: ...


def sort_asc(items: list[Sortable]) -> list[Sortable]:
  return sorted(items)


@dataclass(order=True)
class Product:
  price: float
  name: str = ""

  # order=True даёт __lt__ по полям по порядку — для учебника упростим:
  def __lt__(self, other: "Product") -> bool:
    return self.price < other.price


products = [Product(10), Product(5)]
assert [p.price for p in sort_asc(products)] == [5, 10]
```

</details>

<details>
<summary>Задание 2 — SimpleCache</summary>

```python
from collections.abc import Hashable


class SimpleCache:
  """Ключи должны быть hashable: неизменяемы и с устойчивым __hash__. list не подходит."""

  def __init__(self) -> None:
    self._data: dict[Hashable, object] = {}

  def get(self, key: Hashable):
    return self._data.get(key)

  def set(self, key: Hashable, value: object) -> None:
    self._data[key] = value

  def clear(self) -> None:
    self._data.clear()
```

</details>

<details>
<summary>Задание 3 — load_plugins</summary>

```python
from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
  name: str

  def run(self, config: dict) -> None: ...


def load_plugins(modules: Iterable[object]) -> list[Plugin]:
  result: list[Plugin] = []
  for obj in modules:
    if isinstance(obj, Plugin):
      # runtime не проверяет, что run принимает dict — нужны тесты/inspect
      result.append(obj)
  return result


class HelloPlugin:
  name = "hello"

  def run(self, config: dict) -> None:
    print(config.get("msg", "hi"))


assert load_plugins([HelloPlugin(), object()]) == [HelloPlugin()]
```

</details>

## Вопросы для самопроверки

1. **Нужно ли писать `class X(Protocol)` для реализации?**  
   *Ответ:* нет; достаточно совпадающих методов/атрибутов (structural subtyping).

2. **Почему `isinstance(x, MyProtocol)` без decorator может быть бесполезен?**  
   *Ответ:* без `@runtime_checkable` Protocol не участвует в isinstance checks.

3. **Чем Iterator отличается от Iterable?**  
   *Ответ:* Iterator имеет `__next__` и обычно одноразовый; Iterable только предоставляет итератор.

4. **Почему list не Hashable?**  
   *Ответ:* mutable; изменение list сломает инвариант хеш-таблицы.

5. **Protocol vs ABC — когда ABC лучше?**  
   *Ответ:* когда нужна общая реализация базового класса или строгая регистрация подклассов в framework.

6. **Проверяет ли runtime_checkable типы аргументов `run`?**  
   *Ответ:* нет, только наличие атрибута по имени.

7. **Связь Protocol и TypeVar bound из [Модуля 6](06-mutations-typevar.md)?**  
   *Ответ:* `TypeVar(..., bound=MyProtocol)` ограничивает generic только структурными субтипами.

## Методические указания

### Для преподавателя

- Сравните с Go `interface{}` — знакомый мост для изучающих Go.
- Демо: один и тот же код с `list` и генератором — мотивация `Iterable`.
- Покажите ложноположительный `isinstance(Broken(), HasClose)` — дискуссия о границах runtime.

### Для студента

- Предпочитайте `collections.abc` в публичных сигнатурах.
- Пишите Protocol для **потребностей** функции, не для «всех методов класса».
- Перед `isinstance(Protocol)` спросите: «Достаточно ли static check?»

### Дальнейший путь

- [Модуль 8](08-design-patterns.md) — Strategy и DI через Protocol.
- Интеграция с async: `Protocol` с `async def` (asyncio, [Модуль 3](03-asyncio.md)).

## Дополнительные материалы

- PEP 544 — Structural Subtyping (Protocols).
- [typing.Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol).
- [collections.abc](https://docs.python.org/3/library/collections.abc.html) — Iterable, Hashable, Iterator.
- Статья mypy: *Protocols and structural subtyping*.
