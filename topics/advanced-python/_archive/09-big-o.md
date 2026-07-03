# Модуль 9: Анализ сложности алгоритмов (Big O)

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 9 из 12 |
| Предварительные знания | Базовый Python: циклы, списки, словари, функции; понимание рекурсии; основы работы с коллекциями |
| Следующий модуль | [10-system-libraries.md](10-system-libraries.md) — системные библиотеки Python |
| Ориентировочное время | 4–6 часов (теория + практика + профилирование) |
| Версия Python | 3.11+ |
| Ключевые темы | O(1), O(log n), O(n), O(n log n), O(n²); амортизированный анализ; `timeit`, `cProfile` |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Классифицировать** алгоритмы по асимптотической сложности времени и памяти (от O(1) до O(n²) и выше).
2. **Объяснять** разницу между худшим, средним и лучшим случаем, а также понятие амортизированной сложности.
3. **Анализировать** реальный код на Python и определять доминирующий член сложности.
4. **Измерять** производительность с помощью `timeit` и `cProfile`, интерпретируя результаты без преждевременной оптимизации.
5. **Выбирать** подходящую структуру данных и алгоритм исходя из ограничений по времени и памяти.
6. **Избегать** типичных ловушек: скрытые O(n²) в «простых» конструкциях, ложные выводы из микробенчмарков.

---

## Теория

### 9.1 Зачем нужен анализ сложности

Программа может быть *корректной*, но *неприемлемо медленной* при росте входных данных. Анализ сложности (complexity analysis) отвечает на вопрос: **как меняется время работы (или память) при увеличении размера входа n?**

Мы описываем поведение **асимптотически** — при больших n, игнорируя константы и младшие члены. Запись **O(f(n))** («О-большое от f(n)») означает верхнюю границу роста в худшем (или согласованном) случае.

**Интуиция:** если алгоритм O(n), удвоение n примерно удваивает время. Если O(n²) — удвоение n увеличивает время примерно в 4 раза.

### 9.2 Основные классы сложности

#### O(1) — константное время

Время не зависит от n (в разумных пределах модели).

Примеры в Python:
- доступ к элементу списка по индексу: `lst[i]`
- вставка/удаление с конца списка: `lst.append()`, `lst.pop()`
- чтение/запись в словарь по ключу (в среднем): `d[key] = value`
- арифметические операции, присваивание

```python
def first_element(data: list[int]) -> int | None:
    return data[0] if data else None  # O(1)
```

#### O(log n) — логарифмическое время

Типично, когда на каждом шаге задача **уменьшается в фиксированное число раз** (бинарный поиск, операции в сбалансированном дереве).

```python
# Поиск в отсортированном списке — O(log n) с bisect
import bisect

def contains_sorted(sorted_data: list[int], target: int) -> bool:
    idx = bisect.bisect_left(sorted_data, target)
    return idx < len(sorted_data) and sorted_data[idx] == target
```

#### O(n) — линейное время

Один проход по данным размера n.

```python
def total(numbers: list[int]) -> int:
    s = 0
    for x in numbers:
        s += x
    return s  # O(n)
```

Встроенные функции `sum()`, `max()`, `min()` на списке — тоже O(n).

#### O(n log n) — линейно-логарифмическое время

Характерно для **эффективной сортировки** сравнением: `sorted()`, `list.sort()` в CPython используют Timsort — O(n log n) в среднем и худшем случае.

```python
def top_k_sorted(values: list[int], k: int) -> list[int]:
    return sorted(values, reverse=True)[:k]  # O(n log n)
```

#### O(n²) — квадратичное время

Вложенные циклы по одним и тем же данным:

```python
def all_pairs(items: list[int]) -> list[tuple[int, int]]:
    result = []
    for i in items:
        for j in items:
            result.append((i, j))
    return result  # O(n²)
```

**Скрытый O(n²) в Python:**
- проверка принадлежности в списке: `x in lst` — O(n)
- повторение такой проверки в цикле: O(n²)
- конкатенация строк в цикле через `+=` (исторически; в CPython 3.x есть оптимизации, но `''.join(parts)` надёжнее)

#### Сводная таблица

| Сложность | n=100 | n=10 000 | Типичные операции |
|-----------|-------|----------|-------------------|
| O(1) | ~1 | ~1 | индекс, dict lookup |
| O(log n) | ~7 | ~13 | бинарный поиск |
| O(n) | 100 | 10 000 | один проход |
| O(n log n) | ~700 | ~130 000 | сортировка |
| O(n²) | 10 000 | 100 000 000 | вложенные циклы |

### 9.3 Худший, средний, лучший случай

- **Худший (worst case):** максимальное время для входа размера n. Обычно именно его обозначают O(...).
- **Средний (average case):** математическое ожидание по всем входам (например, вставка в hash table).
- **Лучший (best case):** минимум (редко используется в оценках, но полезен для понимания).

Пример: линейный поиск в несортированном списке — O(n) в худшем и среднем, O(1) в лучшем (элемент первый).

### 9.4 Сложность по памяти

**Пространственная сложность** — сколько дополнительной памяти растёт с n.

```python
def copy_list(data: list[int]) -> list[int]:
    return list(data)  # O(n) дополнительной памяти

def reverse_in_place(data: list[int]) -> None:
    data.reverse()  # O(1) доп. памяти (операция на месте)
```

Рекурсия добавляет O(глубина стека) — для глубокой рекурсии это критично.

### 9.5 Амортизированный анализ (amortized analysis)

Некоторые операции **дорогие редко**, но **дешёвые в среднем** на последовательности из n операций. Тогда говорят об **амортизированной** сложности O(1) или O(n) на операцию.

**Классический пример — `list.append` в CPython:**

- Большинство вызовов O(1): добавление в конец с зарезервированным местом.
- Иногда O(n): при переполнении capacity список перераспределяется с копированием всех элементов.
- На n последовательных append амортизированная стоимость — **O(1) на операцию**, суммарно O(n).

**Динамический массив (упрощённая модель):**
- capacity удваивается при заполнении
- копирования: 1 + 2 + 4 + ... + n/2 < 2n → O(n) на n вставок

**Другие примеры:**
- `dict` и `set`: вставка амортизированно O(1); редкая рехешировка — O(n), но редко
- `str.join` vs наивная конкатенация в цикле

Амортизированный анализ **не гарантирует** O(1) на *каждую* отдельную операцию — важно для real-time систем с жёсткими дедлайнами.

### 9.6 Как анализировать код на Python

**Правила большого пальца:**

1. Посчитайте вложенность циклов по n — часто это O(n^степень).
2. Вызов встроенной сортировки — добавьте O(n log n).
3. Операции над множествами/словарями — O(1) среднее для одной операции.
4. Срезы списка `lst[a:b]` — O(b-a), т.е. O(n) в худшем случае.
5. Генераторы и `yield` — часто O(1) по памяти на шаг (ленивые вычисления).

```python
# O(n): один проход, set для O(1) проверок
def unique_filter(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
```

### 9.7 Профилирование: измеряй, не угадывай

Асимптотика описывает **тренд**, но константы, кэш CPU, GIL и реализация CPython влияют на реальное время. **Профилирование** подтверждает узкие места на ваших данных.

#### Модуль `timeit`

Измеряет время выполнения небольшого фрагмента с высокой точностью (многократные прогоны).

```python
import timeit

setup = "data = list(range(10_000))"
stmt_linear = "sum(data)"
stmt_quadratic = "[(i, j) for i in data for j in data[:100]]"

t_linear = timeit.timeit(stmt_linear, setup=setup, number=100)
t_quad = timeit.timeit(stmt_quadratic, setup=setup, number=10)
```

**Параметры:**
- `setup` — код подготовки (не входит в замер)
- `stmt` — измеряемый код
- `number` — сколько раз повторить stmt
- `timeit.timeit` возвращает суммарное время в секундах

**CLI:** `python -m timeit -s "setup" "stmt"`

#### Модуль `cProfile`

Статистический профайлер: **где** программа тратит время (по функциям).

```python
import cProfile
import pstats

def slow_function():
    total = 0
    for i in range(10_000):
        for j in range(100):
            total += i * j
    return total

profiler = cProfile.Profile()
profiler.enable()
slow_function()
profiler.disable()

stats = pstats.Stats(profiler).sort_stats("cumulative")
stats.print_stats(10)
```

**CLI:** `python -m cProfile -s cumulative script.py`

**Ключевые метрики в отчёте:**
- `ncalls` — число вызовов
- `tottime` — время внутри функции (без подвызовов)
- `cumtime` — суммарное с к подфункциями
- `percall` — среднее на вызов

#### `profile` vs `cProfile`

- `profile` — чистый Python, точнее по времени, медленнее
- `cProfile` — на C, быстрее, стандарт для production-like замеров

### 9.8 Типичные ошибки при оценке сложности

1. **Путать n и константу:** O(2n) = O(n).
2. **Игнорировать скрытые циклы:** `if x in list` внутри цикла.
3. **Экстраполировать с малых n:** O(n²) может быть быстрее O(n log n) при n < 50 из-за констант.
4. **Оптимизировать без профиля:** «серебряная пуля» редко там, где кажется.
5. **Забывать про память:** O(n) времени с O(n²) памяти убьёт процесс раньше, чем CPU.

### 9.9 Big O и инженерная практика

- Для **интерактивных** задач (UI, API) целевые порядки: миллисекунды на запрос.
- Для **batch** обработки — общее время на весь датасет и масштабирование.
- **Правило 80/20:** сначала корректный алгоритм правильного порядка, потом микрооптимизации.

Связь с последующими модулями: выбор `list` vs `set` vs `deque` vs `heapq` (модуль 11) напрямую определяется сложностью операций.

---

## Примеры кода

### Пример 1: Сравнение O(n) и O(n²) поиска дубликатов

```python
def has_duplicate_quadratic(nums: list[int]) -> bool:
    """O(n²) — вложенное сравнение."""
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] == nums[j]:
                return True
    return False


def has_duplicate_linear(nums: list[int]) -> bool:
    """O(n) — множество для O(1) проверки."""
    seen: set[int] = set()
    for x in nums:
        if x in seen:
            return True
        seen.add(x)
    return False


if __name__ == "__main__":
    import timeit

    n = 5_000
    data = list(range(n))

    t1 = timeit.timeit(
        lambda: has_duplicate_quadratic(data),
        number=3,
    )
    t2 = timeit.timeit(
        lambda: has_duplicate_linear(data),
        number=100,
    )
    print(f"O(n²): {t1:.4f}s (3 runs)")
    print(f"O(n):  {t2:.4f}s (100 runs)")
```

### Пример 2: Амортизированная стоимость append

```python
def measure_append_growth(n: int = 100_000) -> list[int]:
    """Демонстрация редких «дорогих» append при росте capacity."""
    import sys

    lst: list[int] = []
    capacities: list[int] = []
    prev_cap = 0

    for i in range(n):
        lst.append(i)
        # sys.getsizeof не равен len*element, но отражает рост буфера
        cap = lst.__sizeof__()
        if cap != prev_cap:
            capacities.append((i, cap))
            prev_cap = cap

    return [size for _, size in capacities]


if __name__ == "__main__":
    steps = measure_append_growth(50_000)
    print(f"Число изменений размера буфера: {len(steps)}")
    print("Рост нелинейный, но число реаллокаций O(log n)")
```

### Пример 3: Профилирование с cProfile

```python
"""profile_demo.py — запуск: python -m cProfile -s cumulative profile_demo.py"""
from __future__ import annotations

import random


def generate_data(n: int) -> list[int]:
    return [random.randint(0, n) for _ in range(n)]


def sort_and_filter(data: list[int], threshold: int) -> list[int]:
    sorted_data = sorted(data)
    return [x for x in sorted_data if x > threshold]


def main() -> None:
    data = generate_data(50_000)
    result = sort_and_filter(data, 25_000)
    print(len(result))


if __name__ == "__main__":
    main()
```

### Пример 4: Оценка сложности рекурсии

```python
def fib_recursive(n: int) -> int:
    """O(2^n) — экспоненциальная без мемоизации."""
    if n < 2:
        return n
    return fib_recursive(n - 1) + fib_recursive(n - 2)


def fib_linear(n: int) -> int:
    """O(n) время, O(1) память — итеративно."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
```

### Пример 5: timeit с разными размерами входа

```python
import timeit


def bench_sort_scaling() -> None:
    sizes = [1_000, 5_000, 10_000, 20_000]
    for n in sizes:
        setup = f"data = list(range({n}, 0, -1))"
        stmt = "sorted(data)"
        elapsed = timeit.timeit(stmt, setup=setup, number=10)
        print(f"n={n:>6}: {elapsed:.4f}s total (10 runs)")


if __name__ == "__main__":
    bench_sort_scaling()
```

### Пример 6: Анализ вложенных операций

```python
def count_pairs_with_membership(items: list[str], targets: set[str]) -> int:
    """
    O(n * m) где n = len(items), m = len(targets) в худшем для `t in targets`.
    set lookup O(1) → итого O(n).
    """
    count = 0
    for item in items:
        for t in targets:
            if item == t:
                count += 1
    return count


def count_pairs_optimized(items: list[str], targets: set[str]) -> int:
    """O(n) — проверка через set."""
    return sum(1 for item in items if item in targets)
```

---

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| O(n²) простой двойной цикл | Понятен, мало кода, нет доп. памяти | Не масштабируется | n < 200, прототип, разовый скрипт |
| O(n) с `set`/`dict` | Быстро на больших n | Доп. память O(n); элементы должны быть hashable | Поиск, дедупликация, частые membership-тесты |
| Сортировка O(n log n) + проход O(n) | Упорядоченный результат, бинарный поиск | Меняет порядок / нужна копия | Top-K, интервалы, merge-подобные задачи |
| `heapq` O(n log k) | Эффективный top-K без полной сортировки | Сложнее API | Потоковые данные, k << n |
| Мемоизация / DP | Снижает экспоненту до полинома | Память, сложность кода | Перекрывающиеся подзадачи |
| Преждевременная оптимизация | — | Тратится время, падает читаемость | Избегать до профилирования |
| Только Big O на бумаге | Быстрая оценка | Игнорирует константы и железо | Первичный дизайн; затем — замеры |

**Золотое правило:** сначала **правильный порядок** сложности, затем **профилирование**, затем **точечная** оптимизация горячих участков.

---

## Практические задания

### Задание 1 (базовое): Классификация сложности

Проанализируйте следующие фрагменты и укажите доминирующую временную сложность в терминах O(...). Обоснуйте ответ.

```python
# A
def func_a(n: int) -> int:
    total = 0
    for i in range(n):
        total += i
    return total

# B
def func_b(n: int) -> list[int]:
    return [i * 2 for i in range(n)]

# C
def func_c(matrix: list[list[int]]) -> int:
    s = 0
    for row in matrix:
        for val in row:
            s += val
    return s

# D
def func_d(items: list[int], target: int) -> bool:
    return target in items

# E
def func_e(items: list[int], targets: list[int]) -> int:
    count = 0
    for t in targets:
        if t in items:
            count += 1
    return count
```

**Дополнительно:** для `func_e` перепишите решение с O(n + m) вместо O(n * m).

---

### Задание 2 (среднее): Бенчмарк и амортизированный append

Напишите скрипт `bench_complexity.py`, который:

1. С помощью `timeit` сравнивает время `func_a` и `func_c` из задания 1 на входах n ∈ {100, 1_000, 10_000} (для C — квадратная матрица n×n).
2. Строит таблицу (print) «размер → время» и кратко комментирует, совпадает ли рост с ожидаемым O(n) и O(n²).
3. Измеряет 100_000 вызовов `list.append` в пустой список и объясняет в комментарии, почему суммарное время линейно по числу операций (амортизированный O(1)).

---

### Задание 3 (продвинутое): Профилирование реального пайплайна

Реализуйте модуль обработки логов:

```python
def parse_line(line: str) -> tuple[str, int] | None: ...
def process_file(path: str) -> dict[str, int]: ...
```

- `parse_line` парсит строку вида `"user_id,action"` → `(user_id, 1)` или `None` при ошибке.
- `process_file` читает файл, считает число действий по каждому `user_id`.

Создайте синтетический файл на 100_000 строк (генератор). Запустите `cProfile`, найдите функцию с наибольшим `cumtime`. Оптимизируйте **одно** узкое место (например, замените накопление через список на `Counter` или уберите лишние вызовы) и покажите разницу в `timeit` до/после.

**Критерии:** корректность сохраняется; в отчёте — 5–10 строк вывода `cProfile` и краткий вывод.

---

## Эталонные решения

<details>
<summary>Задание 1 — ответы и оптимизация func_e</summary>

**Сложность:**
- `func_a`: **O(n)** — один цикл.
- `func_b`: **O(n)** — list comprehension один проход.
- `func_c`: **O(n²)** если матрица n×n; O(строки × столбцы) в общем случае.
- `func_d`: **O(n)** — линейный поиск в списке.
- `func_e`: **O(len(targets) × len(items))** — для каждого target линейный поиск в items.

**Оптимизация func_e:**

```python
def func_e_optimized(items: list[int], targets: list[int]) -> int:
    item_set = set(items)  # O(n)
    return sum(1 for t in targets if t in item_set)  # O(m)
```

Итого **O(n + m)**.

</details>

<details>
<summary>Задание 2 — bench_complexity.py</summary>

```python
"""bench_complexity.py"""
from __future__ import annotations

import timeit


def func_a(n: int) -> int:
    total = 0
    for i in range(n):
        total += i
    return total


def func_c_matrix(n: int) -> int:
    matrix = [[j for j in range(n)] for _ in range(n)]
    s = 0
    for row in matrix:
        for val in row:
            s += val
    return s


def bench() -> None:
    print("=== func_a O(n) ===")
    for n in (100, 1_000, 10_000):
        t = timeit.timeit(lambda n=n: func_a(n), number=100)
        print(f"n={n:>6}: {t:.6f}s")

    print("\n=== func_c O(n²) matrix ===")
    for n in (100, 500, 1_000):
        t = timeit.timeit(lambda n=n: func_c_matrix(n), number=5)
        print(f"n={n:>6}: {t:.6f}s")

    print("\n=== append amortized ===")
    t_append = timeit.timeit(
        "lst = []\nfor i in range(100_000): lst.append(i)",
        number=10,
    )
    print(f"100k append x10 runs: {t_append:.4f}s total")
    print("# Суммарно O(n): редкие O(n) реаллокации не доминируют.")


if __name__ == "__main__":
    bench()
```

</details>

<details>
<summary>Задание 3 — process_file и профилирование</summary>

```python
"""log_pipeline.py"""
from __future__ import annotations

import cProfile
import pstats
import timeit
from collections import Counter
from pathlib import Path


def parse_line(line: str) -> tuple[str, int] | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split(",", 1)
    if len(parts) != 2:
        return None
    user_id, _action = parts[0].strip(), parts[1].strip()
    if not user_id:
        return None
    return user_id, 1


def process_file_naive(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue
            user_id, inc = parsed
            if user_id in counts:
                counts[user_id] += inc
            else:
                counts[user_id] = inc
    return counts


def process_file_optimized(path: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue
            user_id, inc = parsed
            counter[user_id] += inc
    return dict(counter)


def generate_log(path: Path, lines: int = 100_000) -> None:
    import random

    users = [f"user_{i % 500}" for i in range(500)]
    actions = ["login", "logout", "click", "view"]
    with path.open("w", encoding="utf-8") as f:
        for _ in range(lines):
            f.write(f"{random.choice(users)},{random.choice(actions)}\n")


def profile_main() -> None:
    log_path = Path("synthetic.log")
    generate_log(log_path)

    profiler = cProfile.Profile()
    profiler.enable()
    process_file_naive(str(log_path))
    profiler.disable()
    pstats.Stats(profiler).sort_stats("cumulative").print_stats(8)


def compare_timing() -> None:
    log_path = Path("synthetic.log")
    t1 = timeit.timeit(
        lambda: process_file_naive(str(log_path)),
        number=5,
    )
    t2 = timeit.timeit(
        lambda: process_file_optimized(str(log_path)),
        number=5,
    )
    print(f"naive: {t1:.4f}s, optimized: {t2:.4f}s")


if __name__ == "__main__":
    profile_main()
    compare_timing()
```

</details>

---

## Вопросы для самопроверки

1. Чем отличается O(2n + 5) от O(n)? Почему константы отбрасывают?
2. Какова сложность `sorted(lst)` и `lst.sort()` в CPython?
3. Почему `x in my_list` внутри цикла по n элементам даёт O(n²)?
4. Объясните амортизированный O(1) для `list.append` своими словами.
5. Когда бинарный поиск O(log n) **нельзя** применить к данным?
6. Чем `tottime` отличается от `cumtime` в отчёте `cProfile`?
7. Может ли алгоритм O(n²) быть быстрее O(n log n) на практике? При каких условиях?
8. Какова пространственная сложность `return sorted(data)` vs `data.sort(); return data`?
9. Зачем запускать `timeit` с параметром `number` > 1?
10. Как связаны выбор `set` вместо `list` и анализ Big O?

---

## Методические указания

### Для студента

1. **Не заучивайте формулы** — тренируйте распознавание паттернов: циклы, рекурсия, встроенные операции.
2. При бенчмарках **фиксируйте окружение**: версия Python, загрузка CPU, холодный/тёплый кэш.
3. Увеличивайте n в **2–10 раз** и смотрите, как растёт время — это лучшая проверка гипотезы о сложности.
4. Для задания 3 сохраните **до/после** вывод профайлера в отчёте — это навык code review и incident analysis.
5. Свяжите тему с реальностью: парсинг 1M строк логов, API с пагинацией, поиск в каталоге товаров.

### Для преподавателя

- На занятии 1: теория O(1)–O(n²) + ручной разбор 5 фрагментов кода.
- На занятии 2: live demo `timeit` и `cProfile` на проекторе; студенты приносят свой медленный скрипт.
- **Типичные ошибки:** путают размер входа и значение элементов; считают срез O(1); не учитывают hash collisions (редко, но для теории полноты).
- **Дискуссия:** «Нужен ли Big O в эпоху облачного автоскейлинга?» — направьте к cost и latency SLO.
- Оценивание задания 3: 40% корректность, 30% профилирование, 30% обоснованная оптимизация (не обязательно максимальный выигрыш).

### Рекомендуемый порядок изучения

1. Теория 9.1–9.5 → примеры 1–2
2. Практика задание 1
3. Теория 9.7 → примеры 3–5 → задание 2
4. Задание 3 + вопросы для самопроверки

---

## Дополнительные материалы

### Официальная документация

- [timeit — Measure execution time](https://docs.python.org/3/library/timeit.html)
- [profile — Python Profilers](https://docs.python.org/3/library/profile.html)
- [statistics — Statistical calculations](https://docs.python.org/3/library/statistics.html) (для анализа серий замеров)

### Книги и статьи

- Thomas H. Cormen et al., *Introduction to Algorithms* (CLRS) — главы об асимптотической нотации и амортизированном анализе.
- Agner Fog, *Optimization manuals* — почему константы и CPU matter на практике.
- Donald Knuth, *The Art of Computer Programming*, Vol. 1 — математическая строгость анализа.

### Инструменты

- [`pytest-benchmark`](https://github.com/ionelmc/pytest-benchmark) — бенчмарки в тестах.
- [`line_profiler`](https://github.com/pyutils/line_profiler) — построчное профилирование (`@profile`).
- [`memory_profiler`](https://github.com/pythonprofilers/memory_profiler) — профиль памяти.

### Видео и курсы

- MIT 6.006 Introduction to Algorithms (лекции по Big O, доступны онлайн).
- Real Python: «Python Timer Functions» и «Profiling Python Code».

### Связь с другими модулями

- **Модуль 11:** структуры данных и их операционная сложность.
- **Модуль 12:** когда останавливать оптимизацию ради читаемости.
- **Модуль 10:** `timeit` и скрипты измерения в CLI-утилитах.
