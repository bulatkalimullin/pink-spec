# Модуль 24: Структуры данных стандартной библиотеки

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 11 из 12 |
| Предварительные знания | Базовые коллекции Python, модуль 9 (Big O), базовое ООП |
| Следующий модуль | [12-engineering-thinking.md](12-engineering-thinking.md) — инженерное мышление |
| Ориентировочное время | 6–8 часов |
| Версия Python | 3.11+ |
| Ключевые темы | `list`, `dict`, `set`, `deque`, `heapq`, `bisect`, `dataclass`, `namedtuple` |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Выбирать** правильную встроенную структуру данных исходя из операций и сложности (модуль 9).
2. **Применять** `collections.deque` для очередей и скользящих окон с O(1) на концах.
3. **Использовать** `heapq` для приоритетных очередей и эффективного top-K.
4. **Работать** с отсортированными последовательностями через `bisect`.
5. **Моделировать** неизменяемые записи через `namedtuple` и изменяемые — через `dataclass`.
6. **Комбинировать** структуры в реальных алгоритмах: кэш, планировщик, агрегация событий.

---

## Теория

### 11.1 Обзор: встроенные типы vs модуль collections

CPython реализует основные структуры на C — они быстры и хорошо интегрированы в язык.

| Тип | Упорядоченность | Дубликаты | Hashable ключи | Типичная сложность |
|-----|-----------------|-----------|----------------|-------------------|
| `list` | да (индекс) | да | — | index O(1), insert(0) O(n) |
| `dict` | да (3.7+ insertion) | ключи уникальны | ключи hashable | get/set O(1) avg |
| `set` | нет | нет | элементы hashable | add/in O(1) avg |
| `deque` | да (двусторонняя) | да | — | append/pop с концов O(1) |
| `heapq` | min-heap порядок | да | — | push/pop O(log n) |
| `bisect` | на sorted list | — | — | insert/search O(log n) |

Выбор структуры — **инженерное решение**, не вопрос вкуса.

### 11.2 list — динамический массив

**Сильные стороны:**
- Индексация O(1)
- `append` / `pop()` с конца амортизированно O(1)
- Срезы, сортировка in-place

**Слабые стороны:**
- `insert(0, x)`, `pop(0)` — O(n)
- `x in lst` — O(n)
- Поиск по значению без индекса — O(n)

```python
items: list[int] = []
items.append(10)       # O(1) amortized
items.extend([20, 30]) # O(k)
items.sort()             # O(n log n)
```

**Когда использовать:** упорядоченная изменяемая последовательность, доступ по индексу, редкие вставки в середину.

### 11.3 dict — хеш-таблица

С Python 3.7+ `dict` **сохраняет порядок вставки** (в 3.7 — деталь реализации, с 3.8 — языковая гарантия).

```python
user_scores: dict[str, int] = {}
user_scores["alice"] = 100
user_scores.get("bob", 0)

# Итерация
for key, value in user_scores.items():
    ...
```

**Важно:**
- Ключи должны быть **hashable** (immutable: str, int, tuple из hashable).
- `list` и `dict` нельзя использовать как ключи.
- Рехешировка редко даёт O(n) на одну вставку, но амортизированно O(1).

**Паттерны:**
- Подсчёт: `counts[key] = counts.get(key, 0) + 1` или `Counter`
- Группировка: `defaultdict(list)`
- Кэш: `dict` + `functools.lru_cache` для функций

### 11.4 set — множество уникальных элементов

```python
tags: set[str] = {"python", "backend"}
tags.add("async")

if "python" in tags:  # O(1) average
    ...
```

**Операции теории множеств:** `union |`, `intersection &`, `difference -`, `symmetric_difference ^`.

**Когда использовать:** дедупликация, быстрый membership test, графовые алгоритмы (visited).

### 11.5 collections.deque — двусторонняя очередь

`deque` (double-ended queue) — блокированный список с O(1) на обоих концах.

```python
from collections import deque

queue: deque[str] = deque()
queue.append("task1")      # в конец
queue.appendleft("urgent") # в начало
item = queue.popleft()     # FIFO

# Ограниченное скользящее окно
window: deque[int] = deque(maxlen=3)
for x in data_stream:
    window.append(x)
    # window автоматически отбрасывает старые
```

**Сложность:**
- `append`, `appendleft`, `pop`, `popleft` — O(1)
- доступ по индексу `d[i]` — O(n) в худшем (хуже list)

**Когда использовать:** BFS, producer-consumer очереди, sliding window, ротация буфера.

### 11.6 heapq — бинарная куча (min-heap)

Модуль `heapq` работает **in-place** со списком, поддерживая инвариант кучи.

```python
import heapq

heap: list[int] = []
heapq.heappush(heap, 5)
heapq.heappush(heap, 1)
smallest = heapq.heappop(heap)  # 1

# Быстрое построение кучи из списка
data = [3, 1, 4, 1, 5]
heapq.heapify(data)  # O(n)
```

**Сложность:** push/pop — O(log n); heapify — O(n); `heap[0]` — минимум за O(1).

**Max-heap:** инвертируйте знак: `heappush(h, -x)` / `-heappop(h)`.

**heapq.nlargest / nsmallest:**
```python
top3 = heapq.nlargest(3, scores, key=lambda u: u.score)
# O(n log k) — эффективнее полной сортировки при малом k
```

**Когда использовать:** планировщик задач по приоритету, Dijkstra, streaming top-K, merge k sorted lists.

### 11.7 bisect — бинарный поиск в отсортированном списке

```python
import bisect

sorted_ids = [10, 20, 30, 40, 50]

# Позиция вставки слева/справа от равных
pos = bisect.bisect_left(sorted_ids, 30)   # 2
bisect.insort(sorted_ids, 25)                # O(n) из-за сдвига элементов!

# Проверка наличия
idx = bisect.bisect_left(sorted_ids, 31)
found = idx < len(sorted_ids) and sorted_ids[idx] == 31
```

**Важно:** `insort` — O(n) из-за сдвига в list. Для частых вставок рассмотрите `sortedcontainers` (сторонний) или дерево.

**bisect.bisect_right** — вставка после группы равных элементов.

**Паттерн: интервалы**
```python
breakpoints = [0, 10, 20, 50, 100]
score = 37
bucket = bisect.bisect_right(breakpoints, score) - 1
```

### 11.8 namedtuple — лёгкие неизменяемые записи

```python
from collections import namedtuple

Point = namedtuple("Point", ["x", "y"])
p = Point(1, 2)
print(p.x, p.y)
# p.x = 3  # AttributeError — immutable
```

**Плюсы:** компактнее `dict`, читаемее tuple, `_asdict()`, распаковка.

**Минусы:** нет валидации полей, нет методов по умолчанию (до Python 3.7 можно было добавить через subclass).

С Python 3.7+ для новых записей чаще **`dataclass`** или **`typing.NamedTuple`**.

### 11.9 dataclass — декларативные data-классы (3.7+, улучшения в 3.10+)

```python
from dataclasses import dataclass, field


@dataclass
class User:
    id: int
    name: str
    email: str = ""
    tags: list[str] = field(default_factory=list)

    def display_name(self) -> str:
        return self.name or f"user-{self.id}"


@dataclass(frozen=True, slots=True)
class ImmutableConfig:
    host: str
    port: int = 8080
```

**Ключевые параметры:**
- `frozen=True` — неизменяемость (hashable если все поля hashable)
- `slots=True` (3.10+) — меньше памяти, быстрее доступ к атрибутам
- `order=True` — сравнение по полям
- `field(default_factory=...)` — **никогда** не используйте `tags: list = []` как default!

**dataclass vs namedtuple:**

| | namedtuple | dataclass |
|---|------------|-----------|
| Mutability | нет | настраивается |
| Наследование | ограничено | полноценное |
| Методы | редко | да |
| Память | компактно | slots помогает |
| Валидация | вручную | `__post_init__` |

### 11.10 typing.NamedTuple — типизированный namedtuple

```python
from typing import NamedTuple


class Point(NamedTuple):
    x: float
    y: float

    def distance_sq(self) -> float:
        return self.x ** 2 + self.y ** 2
```

Компромисс: immutability + аннотации типов + IDE support.

### 11.11 Комбинирование структур: типичные рецепты

#### LRU cache (упрощённо)

`OrderedDict` + move_to_end или `functools.lru_cache` для чистых функций.

#### Частотный top-K

`heapq.nlargest` или `Counter.most_common(k)`.

#### Очередь с приоритетом

```python
import heapq

@dataclass(order=True)
class Task:
    priority: int
    name: str = field(compare=False)
```

Осторожно: `order=True` сравнивает все поля по порядку объявления.

#### Индекс inverted

`dict[str, set[int]]` — слово → множество doc_id.

### 11.12 Hashability и равенство

- Объекты с `__eq__` без `__hash__` (например, изменяемый `list`) не hashable.
- `dataclass(frozen=True)` получает `__hash__` автоматически если `eq=True`.
- Для кастомных классов в `set`/`dict` определите согласованные `__eq__` и `__hash__`.

---

## Примеры кода

### Пример 1: deque для BFS

```python
from collections import deque


def bfs(graph: dict[str, list[str]], start: str) -> list[str]:
    visited: set[str] = set()
    order: list[str] = []
    queue: deque[str] = deque([start])

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)

    return order


if __name__ == "__main__":
    g = {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }
    print(bfs(g, "A"))  # ['A', 'B', 'C', 'D']
```

### Пример 2: heapq — планировщик задач

```python
from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    sequence: int
    name: str = field(compare=False)


class TaskScheduler:
    def __init__(self) -> None:
        self._heap: list[PrioritizedTask] = []
        self._seq = 0

    def submit(self, name: str, priority: int) -> None:
        heapq.heappush(
            self._heap,
            PrioritizedTask(priority, self._seq, name),
        )
        self._seq += 1

    def run_next(self) -> str | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap).name


if __name__ == "__main__":
    sched = TaskScheduler()
    sched.submit("low", 10)
    sched.submit("high", 1)
    sched.submit("mid", 5)
    print(sched.run_next())  # high
    print(sched.run_next())  # mid
```

### Пример 3: bisect — таблица тарифов

```python
import bisect
from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    up_to_gb: int
    price_per_gb: float


TIERS = [
    Tier(10, 0.10),
    Tier(100, 0.08),
    Tier(1_000, 0.05),
]

breakpoints = [t.up_to_gb for t in TIERS]


def price_for_usage(gb: float) -> float:
    idx = bisect.bisect_right(breakpoints, gb)
    tier = TIERS[min(idx, len(TIERS) - 1)]
    return gb * tier.price_per_gb
```

### Пример 4: dataclass с валидацией

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
        if not self.subject.strip():
            raise ValueError("Subject cannot be empty")


msg = EmailMessage("alice@example.com", "bob@example.com", "Hello")
```

### Пример 5: namedtuple для парсинга CSV-строки

```python
from collections import namedtuple

LogEntry = namedtuple("LogEntry", "timestamp user_id action status")


def parse_log_line(line: str) -> LogEntry | None:
    parts = line.strip().split(",")
    if len(parts) != 4:
        return None
    ts, uid, action, status = parts
    return LogEntry(ts, uid, action, int(status))


line = "2026-07-03T09:00:00,user_42,login,200"
entry = parse_log_line(line)
if entry:
    print(entry.user_id, entry.status)
```

### Пример 6: set + dict — инвертированный индекс

```python
def build_inverted_index(documents: list[list[str]]) -> dict[str, set[int]]:
    index: dict[str, set[int]] = {}
    for doc_id, words in enumerate(documents):
        for word in set(words):  # уникальные в документе
            index.setdefault(word, set()).add(doc_id)
    return index


docs = [
    ["python", "async"],
    ["python", "data"],
    ["rust", "systems"],
]
idx = build_inverted_index(docs)
print(idx["python"])  # {0, 1}
```

### Пример 7: nlargest для streaming top-K

```python
import heapq
from collections import Counter


def top_k_stream(stream: list[str], k: int) -> list[tuple[str, int]]:
    counts = Counter(stream)
    return heapq.nlargest(k, counts.items(), key=lambda x: x[1])


words = ["a", "b", "a", "c", "a", "b", "d"]
print(top_k_stream(words, 2))  # [('a', 3), ('b', 2)]
```

---

## Trade-off: компромиссы

| Структура | Плюсы | Минусы | Когда выбирать |
|-----------|-------|--------|----------------|
| `list` | Универсальность, срезы, sort | Медленные insert/pop с начала | Индексный доступ, малые n |
| `dict` | O(1) lookup, порядок вставки | Память, ключи hashable | Ассоциативные данные, кэш |
| `set` | Уникальность, быстрый `in` | Нет порядка (до сортировки) | Дедуп, membership, граф |
| `deque` | O(1) на концах | Медленный random access | Очереди, BFS, окна |
| `heapq` | Динамический min/max | Не полная сортировка | Priority queue, top-K |
| `bisect` на list | Простота, sorted order | insort O(n) | Редкие вставки, статичные справочники |
| `namedtuple` | Immutable, лёгкий | Нет валидации, legacy feel | Совместимость, tuple API |
| `dataclass` | Методы, defaults, slots | Больше boilerplate чем dict | DTO, domain models |
| `sorted()` | Полный порядок | O(n log n) | Финальный отчёт, малые данные |

---

## Практические задания

### Задание 1 (базовое): Агрегатор событий

Реализуйте функцию:

```python
def aggregate_events(events: list[tuple[str, str]]) -> dict[str, set[str]]:
    """
    events: список пар (user_id, event_type)
    Возвращает: для каждого user_id — множество уникальных event_type.
    """
```

Используйте `dict` и `set`. Напишите 3 теста в `if __name__ == "__main__"` (пустой список, один пользователь, дубликаты событий).

**Оцените сложность** по времени и памяти.

---

### Задание 2 (среднее): Sliding window maximum

Реализуйте `sliding_max(numbers: list[int], k: int) -> list[int]` — максимум в каждом окне размера `k`.

**Требования:**
- Используйте `deque` для индексов (монотонная очередь).
- Сложность O(n), не O(n * k).
- `k <= 0` или `k > len(numbers)` — вернуть `[]`.

Пример: `sliding_max([1, 3, -1, -3, 5, 3, 6, 7], 3)` → `[3, 3, 5, 5, 6, 7]`.

---

### Задание 3 (продвинутое): Мини-система бронирования

Спроектируйте классы с `dataclass`:

```python
@dataclass(frozen=True, slots=True)
class TimeSlot: ...

@dataclass
class Booking: ...
```

**Функциональность класса `BookingSystem`:**
- `book(room_id: str, start: int, end: int) -> bool` — бронь на полуинтервал `[start, end)` если нет пересечений.
- Храните занятые интервалы эффективно: отсортированный список + `bisect` для поиска пересечения.
- `schedule` возвращает список броней, отсортированный по `start`.

Покройте edge cases: нулевая длительность, полное перекрытие, смежные интервалы (не пересекаются).

---

## Эталонные решения

<details>
<summary>Задание 1 — aggregate_events</summary>

```python
def aggregate_events(events: list[tuple[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for user_id, event_type in events:
        if user_id not in result:
            result[user_id] = set()
        result[user_id].add(event_type)
    return result


# Или короче:
def aggregate_events_compact(events: list[tuple[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for user_id, event_type in events:
        result.setdefault(user_id, set()).add(event_type)
    return result


if __name__ == "__main__":
    assert aggregate_events([]) == {}
    assert aggregate_events([("u1", "login")]) == {"u1": {"login"}}
    data = [("u1", "a"), ("u1", "a"), ("u1", "b"), ("u2", "a")]
    assert aggregate_events(data) == {"u1": {"a", "b"}, "u2": {"a"}}
    print("OK")
```

**Сложность:** O(n) по времени, O(n) по памяти в худшем случае (все события уникальны).

</details>

<details>
<summary>Задание 2 — sliding_max</summary>

```python
from collections import deque


def sliding_max(numbers: list[int], k: int) -> list[int]:
    if k <= 0 or k > len(numbers):
        return []

    idx_deque: deque[int] = deque()
    result: list[int] = []

    for i, value in enumerate(numbers):
        # Удаляем индексы вне окна
        while idx_deque and idx_deque[0] <= i - k:
            idx_deque.popleft()

        # Поддерживаем убывающие значения
        while idx_deque and numbers[idx_deque[-1]] <= value:
            idx_deque.pop()

        idx_deque.append(i)

        if i >= k - 1:
            result.append(numbers[idx_deque[0]])

    return result


if __name__ == "__main__":
    assert sliding_max([1, 3, -1, -3, 5, 3, 6, 7], 3) == [3, 3, 5, 5, 6, 7]
    assert sliding_max([1], 1) == [1]
    assert sliding_max([1, 2], 3) == []
    print("OK")
```

</details>

<details>
<summary>Задание 3 — BookingSystem</summary>

```python
from __future__ import annotations

import bisect
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TimeSlot:
    room_id: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("start must be < end")


@dataclass
class Booking:
    room_id: str
    start: int
    end: int
    guest: str = ""


class BookingSystem:
    def __init__(self) -> None:
        # room_id -> sorted list of (start, end, Booking)
        self._rooms: dict[str, list[tuple[int, int, Booking]]] = {}

    def book(self, room_id: str, start: int, end: int, guest: str = "") -> bool:
        if start >= end:
            return False

        slots = self._rooms.setdefault(room_id, [])
        new_interval = (start, end)
        idx = bisect.bisect_left(slots, new_interval)

        # Проверка пересечения с предыдущим
        if idx > 0 and slots[idx - 1][1] > start:
            return False
        # Проверка пересечения со следующим
        if idx < len(slots) and end > slots[idx][0]:
            return False

        booking = Booking(room_id, start, end, guest)
        slots.insert(idx, (start, end, booking))
        return True

    def schedule(self, room_id: str) -> list[Booking]:
        return [b for _, _, b in self._rooms.get(room_id, [])]


if __name__ == "__main__":
    sys = BookingSystem()
    assert sys.book("A", 10, 12)
    assert sys.book("A", 12, 14)  # смежные — OK
    assert not sys.book("A", 11, 13)  # пересечение
    assert not sys.book("A", 10, 12)  # дубликат
    print(sys.schedule("A"))
```

</details>

---

## Вопросы для самопроверки

1. Почему `default_factory=list` обязателен в dataclass для поля-списка?
2. Какова сложность `heapq.heappop` и `heapq.heapify`?
3. Чем `deque.appendleft` отличается от `list.insert(0, x)` по сложности?
4. Можно ли использовать `list` как ключ `dict`? Почему?
5. Когда `bisect` предпочтительнее `dict`?
6. Что вернёт `heapq.heappop` на max-heap, построенном через отрицание?
7. Зачем `frozen=True` в dataclass для использования в `set`?
8. Как `Counter` связан с `dict`?
9. Почему `insort` на большом списке может быть медленным?
10. В чём разница между `typing.NamedTuple` и `@dataclass`?

---

## Методические указания

### Для студента

1. Перед выбором структуры **запишите операции**, которые нужны чаще всего (lookup, insert, min, order).
2. Рисуйте схемы: deque для BFS, heap для priority queue.
3. Для задания 2 изучите паттерн **monotonic deque** — он встречается в LeetCode и stream analytics.
4. Используйте `slots=True` в dataclass на hot path с миллионами объектов.
5. Сверяйтесь с модулем 9: каждая структура — конкретные O(...).

### Для преподавателя

- **Live coding:** реализовать top-K без сортировки всего списка — сравнить с `sorted`.
- **Мини-хакатон:** BookingSystem + unit tests за 45 минут.
- Обсудите **PEP 557** (dataclasses) и миграцию legacy namedtuple.
- Типичная ошибка: mutable default в dataclass — показать баг с общим списком.

### Лабораторная работа (опционально)

Реализовать простой in-memory поисковик: inverted index (`dict[str, set[int]]`) + ranked results через `heapq.nlargest` по tf-idf (упрощённо).

---

## Дополнительные материалы

### Документация

- [collections — Container datatypes](https://docs.python.org/3/library/collections.html)
- [heapq — Heap queue algorithm](https://docs.python.org/3/library/heapq.html)
- [bisect — Array bisection algorithm](https://docs.python.org/3/library/bisect.html)
- [dataclasses — Data Classes](https://docs.python.org/3/library/dataclasses.html)

### PEP

- [PEP 557 – Data Classes](https://peps.python.org/pep-0557/)
- [PEP 585 – Type Hinting Generics In Standard Collections](https://peps.python.org/pep-0585/)

### Расширения

- `sortedcontainers` — SortedList с O(log n) insert
- `pydantic` — валидация поверх dataclass-like моделей

### Упражнения

- LeetCode: 239 Sliding Window Maximum, 295 Find Median from Data Stream (two heaps)
- Advent of Code: задачи на priority queue и BFS

### Связь с модулями курса

- **Модуль 9:** обоснование выбора deque/heapq/bisect
- **Модуль 10:** сериализация dataclass в JSON для CLI
- **Модуль 12:** проектирование DTO vs domain entities
