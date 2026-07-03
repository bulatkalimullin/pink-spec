# Модуль 6: Мутации, копирование и TypeVar

## Метаданные

| Параметр | Значение |
|----------|----------|
| Предварительные знания | [Модуль 4: ООП](04-oop.md), [Модуль 5: Уязвимости объектов](05-object-vulnerabilities.md) — mutable defaults, shared state; базовые type hints |
| Следующий модуль | [Модуль 7: Протоколы](07-protocols.md) |
| Ориентировочное время | 3–4 ч |

## Цели обучения

1. **Различать** mutable и immutable типы Python и **предсказывать**, когда присваивание создаёт alias, а когда новый объект.
2. **Выбирать** между shallow и deep copy в конкретном сценарии (вложенные структуры, производительность) без скрытых багов shared state из [Модуля 5](05-object-vulnerabilities.md).
3. **Объявлять** обобщённые функции и классы с `typing.TypeVar`, `Generic` и `bound` так, чтобы mypy/pyright принимали код.
4. **Объяснять** разницу между `TypeVar` с `bound=`, `constraints` и `typing.Self` (Python 3.11+) на примерах методов «возвращаю тот же тип».
5. **Применять** `copy.copy` / `copy.deepcopy` и `dataclasses.replace` для безопасных трансформаций данных в API и тестах.

## Теория

### 6.1 Мутабельность в Python: не тип, а поведение

В Python нет ключевого слова `mut` / `const`. Мутабельность — свойство **конкретного класса**:

| Immutable (типично) | Mutable (типично) |
|---------------------|-------------------|
| `int`, `float`, `bool` | `list`, `dict`, `set` |
| `str`, `bytes` | `bytearray` |
| `tuple` (если элементы immutable) | пользовательские объекты с `__dict__` |
| `frozenset` | `datetime` (поля можно менять через `replace`) |
| `types.MappingProxyType` | `namedtuple` — поля «неизменяемы», но вложенные list — нет |

**Присваивание** всегда связывает имя с объектом (reference). `a = b` не копирует данные.

```python
x = [1, 2]
y = x
y.append(3)
# x is [1, 2, 3] — один объект, два имени
```

**Оператор `+=` для list:** вызывает `__iadd__` **на месте**, не создавая новый list. Для `int` создаётся новый объект (immutable).

Связь с [Модулем 5](05-object-vulnerabilities.md): mutable default arguments и атрибуты класса — частные случаи непонимания мутабельности.

### 6.2 Кортежи: «неизменяемые» с оговорками

```python
t = ([1], 2)
t[0].append(99)  # TypeError? Нет — меняем list ВНУТРИ tuple
```

Кортеж неизменяем в смысле **набора ссылок**, но ссылки могут указывать на mutable-объекты. Для hashable-ключей dict нужен **полностью** immutable граф (`tuple` из int/str/frozenset).

### 6.3 Shallow copy vs deep copy

**Shallow copy** создаёт новый контейнер, но элементы — те же объекты (общие ссылки).

```python
import copy
original = [[1, 2], [3, 4]]
shallow = copy.copy(original)
shallow[0].append(99)
# original[0] тоже [1, 2, 99]
```

**Deep copy** рекурсивно копирует вложенный граф. Циклические ссылки обрабатываются (`memo` dict внутри `deepcopy`).

| Метод | Скорость | Изоляция вложенности |
|-------|----------|---------------------|
| `list(s)` / `s[:]` / `dict(s)` | Быстро | Только верхний уровень |
| `copy.copy` | Быстро | Shallow |
| `copy.deepcopy` | Медленнее | Полная (с оговорками для синглтонов) |
| `dataclasses.replace(dc, field=v)` | Зависит от полей | Shallow по полям |

**Когда deepcopy избыточен:** плоский `dict` с int/str; immutable DTO после валидации.

**Когда shallow опасен:** конфиг с вложенными `list[dict]` — типичный баг в тестах и клонировании state.

### 6.4 Копирование и функциональный стиль

Иммутабельные обновления снижают shared state (важно для [asyncio](03-asyncio.md) и многопоточности из [Модуля 1](01-gil.md)):

```python
# Вместо config["retries"] += 1
config = {**config, "retries": config["retries"] + 1}
```

Для вложенных структур — библиотеки `immutables`, или явное `deepcopy` + изменение + возврат новой версии.

### 6.5 Зачем нужны Generics и TypeVar

Статический анализатор не знает:

```python
def first(items):
  return items[0]
```

Тип возврата — `Any` или union всех возможных элементов. **Generic** связывает типы входа и выхода:

```python
from typing import TypeVar

T = TypeVar("T")

def first(items: list[T]) -> T:
  return items[0]
```

Теперь `first([1, 2])` → `int`, `first(["a"])` → `str`.

Это дополняет ООП из [Модуля 4](04-oop.md): полиморфизм во время выполнения + проверка типов до запуска.

### 6.6 TypeVar: объявление и scope

```python
from typing import TypeVar

T = TypeVar("T")                    # любой тип
S = TypeVar("S", str, bytes)        # constraint: только str или bytes
U = TypeVar("U", bound="Comparable")  # U должен быть подтипом Comparable
```

- **Unconstrained `T`:** максимальная гибкость; mypy выводит из аргументов.
- **Constraints `(A, B, C)`:** union из перечисленных; используйте редко — часто лучше `Union` + overload.
- **`bound=`:** верхняя граница; `T` может быть `int`, `float`, но не `str` если bound `SupportsFloat`.

**Именование:** PEP 484 рекомендует короткие имена `T`, `K`, `V`, `T_co` для covariant.

### 6.7 Generic классы

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class Stack(Generic[T]):
  def __init__(self) -> None:
    self._items: list[T] = []

  def push(self, item: T) -> None:
    self._items.append(item)

  def pop(self) -> T:
    return self._items.pop()
```

Использование: `Stack[int]()`, `Stack[str]()`. В Python 3.12+ синтаксис `class Stack[T]:` (PEP 695).

Generic **не дублирует** код в runtime — это аннотации для type checker; в байткоде остаётся один класс `Stack`.

### 6.8 bound и протоколы

`bound` часто указывает на **Protocol** ([Модуль 7](07-protocols.md)):

```python
from typing import Protocol, TypeVar

class SupportsClose(Protocol):
  def close(self) -> None: ...

C = TypeVar("C", bound=SupportsClose)

def cleanup(resource: C) -> None:
  resource.close()
```

Структурная типизация: любой объект с методом `close()` подходит, без наследования.

### 6.9 TypeVar в методах класса: Self и clone

Проблема:

```python
class Point:
  def move(self, dx: int, dy: int) -> "Point":
    ...
```

Подкласс `Point3D` при `move` должен возвращать `Point3D`. Решения:

1. **`typing.Self`** (3.11+): `def move(self, ...) -> Self:`
2. **TypeVar с bound:** `P = TypeVar("P", bound="Point")`

```python
from typing import Self

class Point:
  def move(self, dx: int, dy: int) -> Self:
    return type(self)(self.x + dx, self.y + dy)
```

### 6.10 Variance (кратко)

Для контейнеров важна ковариантность/контравариантность:

- `list` **инвариантен:** `list[Dog]` не подтип `list[Animal]`.
- `Sequence` ковариантен (`Sequence[Dog]` OK где `Sequence[Animal]`).
- `Callable` контравариантен по аргументам, ковариантен по возврату.

На практике: не кастуйте `list[Child]` к `list[Parent]` без `cast` и понимания риска.

### 6.11 Мутации и dataclasses

```python
from dataclasses import dataclass, field

@dataclass
class Config:
  tags: list[str] = field(default_factory=list)  # не []
```

`frozen=True` делает поля непереназначаемыми, но вложенный `list` всё ещё mutable — нужен deep immutability или `tuple`.

## Примеры кода

### Пример 1: id() и alias

```python
a = [1, 2, 3]
b = a
c = list(a)  # shallow copy верхнего уровня — новый list, те же int (immutable)

print(id(a) == id(b))  # True
print(id(a) == id(c))  # False

b.append(4)
print(c)  # [1, 2, 3] — не затронут
```

### Пример 2: Shallow vs deep

```python
import copy

nested = {"users": [{"name": "Ann", "roles": ["user"]}]}
shallow = copy.copy(nested)
deep = copy.deepcopy(nested)

shallow["users"][0]["roles"].append("admin")
print(nested["users"][0]["roles"])   # ['user', 'admin'] — утечка!

nested2 = copy.deepcopy(nested)
deep["users"][0]["roles"].append("mod")
print(nested2["users"][0]["roles"])  # ['user', 'admin'] — deep не трогал nested2 так
```

### Пример 3: TypeVar в функции

```python
from typing import TypeVar, Iterable

T = TypeVar("T")
R = TypeVar("R")


def map_iterable(items: Iterable[T], fn) -> list:
  return [fn(x) for x in items]


# С двумя TypeVar — связь входа и выхода map невозможна без Callable generic;
# простой случай — first и last:

def first(items: list[T]) -> T:
  if not items:
    raise ValueError("empty")
  return items[0]


nums = first([1, 2, 3])      # checker: int
name = first(["a", "b"])     # checker: str
```

### Пример 4: bound=Comparable

```python
from typing import Protocol, TypeVar

class Comparable(Protocol):
  def __lt__(self, other) -> bool: ...

T = TypeVar("T", bound=Comparable)


def maximum(a: T, b: T) -> T:
  return a if a >= b else b


print(maximum(3, 7))           # 7
print(maximum("ab", "ac"))     # ac
```

### Пример 5: Generic Stack

```python
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


class Stack(Generic[T]):
  def __init__(self) -> None:
    self._data: list[T] = []

  def push(self, item: T) -> None:
    self._data.append(item)

  def pop(self) -> T:
    if not self._data:
      raise IndexError("pop from empty stack")
    return self._data.pop()

  def peek(self) -> Optional[T]:
    return self._data[-1] if self._data else None


int_stack: Stack[int] = Stack()
int_stack.push(42)
# int_stack.push("x")  # ошибка type checker
```

### Пример 6: Self в методе clone

```python
from dataclasses import dataclass
from typing import Self


@dataclass
class Vector2D:
  x: float
  y: float

  def add(self, other: Self) -> Self:
    return type(self)(self.x + other.x, self.y + other.y)


@dataclass
class Vector3D(Vector2D):
  z: float = 0.0

  def add(self, other: Self) -> Self:
    return type(self)(
      self.x + other.x,
      self.y + other.y,
      self.z + other.z,
    )


v = Vector3D(1, 2, 3).add(Vector3D(0, 0, 1))
assert type(v) is Vector3D
```

### Пример 7: dataclasses.replace vs мутация

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class Request:
  path: str
  retries: int = 3

req = Request("/api")
req2 = replace(req, retries=req.retries + 1)
assert req.retries == 3
assert req2.retries == 4
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| In-place мутация | Быстро, мало аллокаций | Shared state, сложнее отладка | Hot loop, локальные переменные |
| Immutable updates | Безопаснее в concurrent/async | Больше копий | Конфиги, Redux-style state |
| `copy.copy` | Дёшево | Вложенность shared | Плоские структуры |
| `copy.deepcopy` | Полная изоляция | CPU + память, не всё копируется (lock) | Клон state перед sandbox-тестом |
| `TypeVar` без bound | Просто | Нет ограничений API | `first`, `identity` |
| `TypeVar` + bound | Выражает контракт | Сложнее читать | `maximum`, `close()` |
| `Generic` класс | Типобезопасный контейнер | Шум в аннотациях | Stack, Repository[T] |
| `Any` вместо Generic | Быстрее написать | Нет проверок | Прототип, glue code |
| `frozen dataclass` | Hashable, меньше мутаций | Вложенные list всё ещё mutable | DTO, ключи dict |

## Практические задания

### Задание 1 (базовое): Клонировщик настроек

**Условие:** функция `clone_settings(settings: dict) -> dict` должна возвращать объект, изменение которого **не влияет** на оригинал, включая вложенные `list` и `dict`.

**Критерии:**

- `clone_settings({"a": [1]})` — append в клон не меняет оригинал.
- Оригинальный dict не заменяется (новый top-level).
- Без `deepcopy` в задании можно, если реализуете рекурсию сами.

**Подсказка:** `copy.deepcopy` или рекурсивный обход с `isinstance(..., dict/list)`.

---

### Задание 2 (среднее): Generic Pair и swap

**Условие:** реализуйте `@dataclass` класс `Pair[T]` с полями `first`, `second` и методом `swap() -> Pair[T]`, меняющим местами значения **новым экземпляром** (не мутировать frozen).

**Критерии:**

- `Pair[int](1, 2).swap()` → `Pair(2, 1)` с корректным типом.
- mypy/pyright без ошибок при `Pair[str]("a", "b")`.

**Подсказка:** `Generic[T]`, `frozen=True`, `replace` или конструктор.

---

### Задание 3 (продвинутое): Репозиторий с bound

**Условие:** определите `Protocol Identifiable` с `id: int` и generic-класс `InMemoryRepo[T: Identifiable]` с методами `add(item: T)`, `get(item_id: int) -> T | None`, `all() -> list[T]`.

**Критерии:**

- Работает с `@dataclass class User(Identifiable)` без наследования от ABC.
- `get` возвращает тот же тип `T`, что и `add`.
- Попытка добавить объект без `id` ловится type checker (structural — нужен атрибут).

**Подсказка:** `TypeVar("T", bound=Identifiable)`; связь с [Модулем 7](07-protocols.md).

## Эталонные решения

<details>
<summary>Задание 1 — clone_settings</summary>

```python
import copy
from typing import Any


def clone_settings(settings: dict[str, Any]) -> dict[str, Any]:
  return copy.deepcopy(settings)


# Тест
orig = {"retries": 3, "hosts": ["h1"]}
clone = clone_settings(orig)
clone["hosts"].append("h2")
assert orig["hosts"] == ["h1"]
```

</details>

<details>
<summary>Задание 2 — Pair[T]</summary>

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Pair(Generic[T]):
  first: T
  second: T

  def swap(self) -> "Pair[T]":
    return Pair(self.second, self.first)
```

</details>

<details>
<summary>Задание 3 — InMemoryRepo</summary>

```python
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

class Identifiable(Protocol):
  id: int

T = TypeVar("T", bound=Identifiable)


class InMemoryRepo(Generic[T]):
  def __init__(self) -> None:
    self._store: dict[int, T] = {}

  def add(self, item: T) -> None:
    self._store[item.id] = item

  def get(self, item_id: int) -> T | None:
    return self._store.get(item_id)

  def all(self) -> list[T]:
    return list(self._store.values())


@dataclass
class User:
  id: int
  name: str


repo: InMemoryRepo[User] = InMemoryRepo()
repo.add(User(1, "Ann"))
assert repo.get(1).name == "Ann"
```

</details>

## Вопросы для самопроверки

1. **Почему `tuple` с list внутри может быть «логически» mutable?**  
   *Ответ:* неизменяемость tuple — это фиксированный набор ссылок; содержимое по ссылке можно менять.

2. **Чем `list.copy()` отличается от `copy.deepcopy` для `[[1]]`?**  
   *Ответ:* `list.copy()` shallow — внутренний list общий; deepcopy создаёт новый внутренний list.

3. **Зачем `field(default_factory=list)` в dataclass?**  
   *Ответ:* избежать shared mutable default ([Модуль 5](05-object-vulnerabilities.md)).

4. **Что даёт `TypeVar("T", bound=SupportsFloat)`?**  
   *Ответ:* T только для типов, совместимых с bound; checker отклонит несовместимые аргументы.

5. **Инвариантность `list[Dog]` и `list[Animal]` — в чём риск каста?**  
   *Ответ:* в list[Animal] можно положить Cat, сломав ожидание Dog-only.

6. **Когда `Self` предпочтительнее строки `"Point"`?**  
   *Ответ:* корректный тип возврата в подклассах без дублирования TypeVar.

7. **`frozen=True` делает dataclass полностью immutable?**  
   *Ответ:* нет, если поля — mutable контейнеры; freeze только запрет переназначения полей.

## Методические указания

### Для преподавателя

- Нарисуйте диаграмму «два имени → один list» перед shallow/deep.
- Свяжите deepcopy с тестами: «fixture не должен протекать между тестами».
- Generics вводите после одного конкретного бага: `def parse(s) -> ???` без TypeVar.
- Покажите ошибку mypy при `Stack[int]().push("s")` — мгновенная обратная связь.

### Для студента

- В REPL проверяйте `id()` при сомнениях.
- Перед изменением аргумента-контейнера спросите: «Чей это объект?»
- Используйте `pyright` или `mypy` в CI — Generics окупаются на больших кодовых базах.

### Связь с курсом

- [Модуль 5](05-object-vulnerabilities.md) — откуда берётся shared state.
- [Модуль 7](07-protocols.md) — `bound` на Protocol.
- [Модуль 8](08-design-patterns.md) — Generic Repository, Strategy с TypeVar.

## Дополнительные материалы

- [typing — Generics](https://docs.python.org/3/library/typing.html#generics) — официальная документация.
- PEP 484, PEP 695 (type parameter syntax 3.12+).
- *Fluent Python* (Ramalho), гл. про мутабельность и copy.
- Библиотека `typing_extensions` для `Self` на Python < 3.11.
