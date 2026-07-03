# Модуль 5: Уязвимости объектов в Python

## Метаданные

| Параметр | Значение |
|----------|----------|
| Предварительные знания | [Модуль 1: GIL](01-gil.md), [Модуль 2: ASYNC](02-async.md), [Модуль 3: asyncio](03-asyncio.md), [Модуль 4: ООП](04-oop.md) — классы, атрибуты экземпляра и класса, `__init__`, наследование |
| Следующий модуль | [Модуль 6: Мутации и TypeVar](06-mutations-typevar.md) |
| Ориентировочное время | 3–4 ч (теория ~1,5 ч, примеры ~1 ч, практика ~1–1,5 ч) |

## Цели обучения

1. **Обнаруживать** классическую ошибку mutable default arguments и **исправлять** её с помощью `None` и инициализации в теле функции — без подсказок в тестовом коде.
2. **Объяснять** механизм shared mutable state между экземплярами и потоками, связывая его с темой GIL из [Модуля 1](01-gil.md): когда гонка данных возможна, а когда нет.
3. **Оценивать риски** десериализации через `pickle` и **предлагать** безопасные альтернативы (JSON, msgpack, явные схемы) для недоверенных данных.
4. **Распознавать** опасность `eval`/`exec` и **применять** whitelist-подход или специализированные парсеры вместо выполнения произвольного кода.
5. **Защищать** объекты от attribute injection через `__slots__`, валидацию `setattr` и принцип минимальных привилегий — в контексте ООП из [Модуля 4](04-oop.md).

## Теория

### 5.1 Почему «безопасность объектов» — отдельная тема

В Python «всё есть объект»: функции, классы, модули, даже `None`. Гибкость даёт скорость разработки, но создаёт класс уязвимостей, которых нет в строго типизированных языках с фиксированной памятью. Эти уязвимости не связаны с «дырами в CPython» — они возникают из **семантики языка** и **привычных идиом**.

Курс уже дал вам инструменты ООП ([Модуль 4](04-oop.md)) и конкурентность ([Модули 1–3](01-gil.md)). Уязвимости объектов — мост между ними: один и тот же mutable-список в default-аргументе может сломать и логику класса, и многопоточный сервис.

### 5.2 Mutable default arguments — классическая ловушка

Значения аргументов по умолчанию вычисляются **один раз** — в момент **определения** функции, а не при каждом вызове.

```python
def append_item(item, bucket=[]):  # bucket создаётся ОДИН раз
    bucket.append(item)
    return bucket
```

После первого вызова `append_item(1)` список `[1]` «прилипает» к функции. Второй вызов `append_item(2)` без второго аргумента увидит уже `[1]`, а не пустой список.

**Почему так устроено:** default — это объект в пространстве имён функции (`func.__defaults__`). Создавать новый список на каждый вызов было бы дороже; для immutable-значений (`None`, `0`, `"x"`) это корректно.

**Правильный паттерн:**

```python
def append_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```

Для mutable default часто используют `dataclasses.field(default_factory=list)` — об этом подробнее в [Модуле 6](06-mutations-typevar.md).

### 5.3 Shared mutable state

Shared state — ситуация, когда **несколько владельцев** ссылаются на **один и тот же** изменяемый объект.

Типичные источники:

| Источник | Пример |
|----------|--------|
| Default-аргумент | См. выше |
| Атрибут класса | `class C: items = []` — общий для всех экземпляров |
| Кэш модуля | Глобальный `dict` в `config.py` |
| Замыкание | `funcs = [lambda: i for i in range(3)]` — позднее связывание |
| Передача по ссылке | `process(user_list)` мутирует список вызывающего кода |

**Связь с GIL:** GIL гарантирует, что байткод одного потока выполняется атомарно *в смысле одной инструкции*, но **не** делает составные операции (`list.append` + проверка) атомарными. Два потока, мутирующие один `dict` без `Lock`, могут получить повреждённые данные. В [Модуле 1](01-gil.md) вы изучали, что для CPU-bound лучше `multiprocessing`, а для I/O — `asyncio` ([Модуль 3](03-asyncio.md)); для **shared mutable state** в потоках нужны явные примитивы синхронизации.

**Иммутабельность как защита:** если данные не меняются, shared state безопаснее. Кортежи, `frozenset`, `NamedTuple` — союзники. Подробнее — в [Модуле 6](06-mutations-typevar.md).

### 5.4 Pickle: удобство против произвольного кода

`pickle` сериализует граф объектов Python, включая ссылки на классы и вызовы `__reduce__`. При **загрузке** (`pickle.loads`) интерпретатор **восстанавливает** объекты, потенциально вызывая произвольный код.

**Модель угроз:**

- Злоумышленник передаёт вам `.pickle`-файл или base64-строку.
- При `pickle.load` выполняется вредоносный `__reduce__`, например `os.system('rm -rf /')`.

**Когда pickle допустим:**

- Кэш внутри доверенного процесса (тот же код, тот же деплой).
- Обмен между воркерами `multiprocessing` (данные не покидают машину).
- ML-пайплайны, где вы сами сохраняете модель.

**Когда pickle запрещён:**

- API, принимающие сериализованные объекты от клиентов.
- Сообщения из Kafka/NATS без подписи и проверки схемы.
- Cookies, query-параметры, файлы от пользователей.

**Альтернативы:** JSON (ограниченные типы), MessagePack, Protocol Buffers, Pydantic-модели с явной валидацией.

### 5.5 eval, exec и compile — выполнение строк как кода

`eval(expression)` вычисляет **выражение** и возвращает результат.  
`exec(statement)` выполняет **операторы** (присваивания, циклы).  
`compile()` готовит байткод для последующего `eval`/`exec`.

Любая строка из недоверенного источника в этих функциях — **Remote Code Execution (RCE)**.

```python
# ОПАСНО: пользователь ввёл "__import__('os').system('id')"
eval(user_input)
```

**Кажущаяся «защита» `{"__builtins__": {}}`:** опытный атакующий обойдёт через цепочки dunder-атрибутов (`().__class__.__bases__[0].__subclasses__()`). Не полагайтесь на «пустой builtins».

**Безопасные подходы:**

1. **Не парсить код пользователя** — дать UI/DSL с фиксированным набором операций.
2. **`ast.literal_eval`** — только литералы (числа, строки, списки, dict, bool, None).
3. **Парсеры выражений:** `simpleeval`, собственный recursive descent для арифметики.
4. **Sandbox** (PyPy sandbox устарел; Docker/gVisor — инфраструктурный уровень, не замена валидации).

### 5.6 Attribute injection и динамическая модель Python

`obj.attr = value` вызывает `obj.__setattr__`. По умолчанию атрибуты пишутся в `obj.__dict__`. Злоумышленник или ошибочный код может:

- Перезаписать «служебные» поля: `user.is_admin = True`.
- Добавить неожиданные ключи в `__dict__` объекта, который потом сериализуется в JSON/SQL.
- Эксплуатировать `getattr(obj, user_controlled_name)` — **prototype pollution** в духе Python.

**Защита:**

1. **`__slots__`** — фиксированный набор атрибутов (см. также расширенный ООП в курсе).
2. **Переопределение `__setattr__`** с whitelist.
3. **`@property` + приватные поля** (`_balance`) с валидацией в сеттере.
4. **`dataclasses` с `frozen=True`** для неизменяемых DTO.
5. **Не использовать `**kwargs` из запроса напрямую** в `Model(**request.json)`.

Связь с [Модулем 4](04-oop.md): инкапсуляция в Python — соглашение + дисциплина, а не принуждение компилятора. Уязвимости появляются, когда соглашение нарушается на границе доверия (HTTP, pickle, плагины).

### 5.7 Чек-лист безопасного проектирования объектов

1. Default-аргументы — только `None` или immutable.
2. Атрибуты класса — не mutable контейнеры (или осознанный singleton).
3. Внешний ввод — никогда в `pickle`/`eval`/`exec`.
4. Десериализация — явная схема + валидация типов ([Модуль 7: Protocols](07-protocols.md) поможет описать контракты).
5. Публичные API классов — минимальный surface; опасные dunder — не вызывать извне.
6. Многопоточный shared state — `threading.Lock`, `queue.Queue`, или immutable messages (как в asyncio из [Модуля 3](03-asyncio.md)).

## Примеры кода

### Пример 1: Mutable default — демонстрация и исправление

```python
# --- ПЛОХО: общий список между вызовами ---
def add_tag_bad(tags, tag, store=[]):
  store.append(tag)
  return store

print(add_tag_bad(["a"], "b"))       # ['a', 'b']
print(add_tag_bad(["x"], "y"))       # ['a', 'b', 'x', 'y'] — сюрприз!


# --- ХОРОШО ---
def add_tag_good(tags, tag, store=None):
  if store is None:
    store = []
  store = list(tags)  # копия, не мутируем аргумент вызывающего
  store.append(tag)
  return store

print(add_tag_good(["a"], "b"))      # ['a', 'b']
print(add_tag_good(["x"], "y"))      # ['x', 'y']
```

### Пример 2: Атрибут класса vs экземпляра

```python
class ShoppingCart:
  # ОПАСНО: один список на ВСЕ корзины
  items_bad = []

  def __init__(self):
    # ПРАВИЛЬНО: свой список у каждого экземпляра
    self.items = []


cart_a = ShoppingCart()
cart_b = ShoppingCart()
cart_a.items.append("apple")

print(cart_b.items)  # [] — корзины независимы

# Но если бы использовали items_bad:
ShoppingCart.items_bad.append("leak")
print(ShoppingCart.items_bad)  # все «корзины» видят это
```

### Пример 3: Shared state и потоки (фрагмент)

```python
import threading

counter = {"value": 0}  # shared mutable dict


def unsafe_increment():
  for _ in range(100_000):
    counter["value"] += 1  # не атомарно: LOAD, ADD, STORE


threads = [threading.Thread(target=unsafe_increment) for _ in range(4)]
for t in threads:
  t.start()
for t in threads:
  t.join()

print(counter["value"])  # обычно < 400_000 — потерянные обновления
```

См. [Модуль 1: GIL](01-gil.md) — для счётчиков используйте `threading.Lock` или `itertools` не поможет; нужен `atomic` уровень или `multiprocessing.Value`.

### Пример 4: Почему pickle опасен (учебная демонстрация)

```python
import pickle
import pickletools


class Exploit:
  def __reduce__(self):
    import os
    # При unpickle вызовется os.system с командой
    return (os.system, ("echo PWNED",))


payload = pickle.dumps(Exploit())
# Никогда не делайте это с недоверенными данными:
pickle.loads(payload)  # напечатает PWNED в shell
```

**Вывод:** `pickle` — формат для доверенных данных, не для wire protocol.

### Пример 5: eval vs ast.literal_eval

```python
import ast

user_expr = "[1, 2, 3]"  # представим, что пришло из формы

# Безопасно для литералов:
data = ast.literal_eval(user_expr)
print(data, type(data))  # [1, 2, 3] <class 'list'>

malicious = "__import__('os').system('id')"
try:
  ast.literal_eval(malicious)
except (ValueError, SyntaxError) as e:
  print("literal_eval отклонил:", e)

# eval(malicious)  # НИКОГДА не раскомментируйте с пользовательским вводом
```

### Пример 6: Защита от attribute injection

```python
class SecureAccount:
  __slots__ = ("_username", "_role")

  def __init__(self, username: str, role: str = "user"):
    object.__setattr__(self, "_username", username)
    object.__setattr__(self, "_role", role)

  @property
  def role(self) -> str:
    return self._role

  def __setattr__(self, name: str, value) -> None:
    if name in SecureAccount.__slots__:
      if name == "_role" and value not in ("user", "moderator", "admin"):
        raise ValueError(f"Недопустимая роль: {value}")
      object.__setattr__(self, name, value)
    else:
      raise AttributeError(f"Запрещённый атрибут: {name}")


acc = SecureAccount("alice")
# acc.is_admin = True  # AttributeError
acc._role = "admin"    # через __setattr__ с валидацией — ок
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| `pickle` для кэша | Быстро, любые Python-типы | RCE при недоверенном вводе | Локальный кэш, тот же процесс |
| JSON / Pydantic | Безопасно, читаемо, кросс-языково | Нет произвольных типов | API, сообщения в очередях |
| `eval` для «гибких правил» | Минимум кода | Полный RCE | Никогда на проде с внешним вводом |
| `ast.literal_eval` | Простой whitelist литералов | Только константы | Конфиги из доверенных файлов |
| Mutable default `[]` | Короче запись | Скрытые баги | Никогда — используйте `None` |
| `__slots__` | Меньше памяти, нет лишних атрибутов | Несовместимость с некоторыми миксинами | Hot path, security-sensitive DTO |
| Глобальный mutable state | Простота прототипа | Гонки, тесты flaky | Только прототип; в проде — DI ([Модуль 8](08-design-patterns.md)) |
| `threading.Lock` вокруг dict | Корректность в потоках | Риск deadlock, сложнее asyncio | Shared state в threads ([Модуль 1](01-gil.md)) |

## Практические задания

### Задание 1 (базовое): Исправить API логгера

**Условие:** дан класс с багом mutable default. Найдите все места shared state и исправьте.

```python
class RequestLogger:
  def __init__(self, buffer=[]):
    self.buffer = buffer

  def log(self, message, extra_fields={}):
    entry = {"msg": message, **extra_fields}
    self.buffer.append(entry)
    return entry
```

**Критерии приёмки:**

- Два экземпляра `RequestLogger()` не делят один буфер.
- Повторные вызовы `log("a")` и `log("b")` без `extra_fields` не смешивают поля.
- Публичный API сохраняет возможность передать внешний `buffer` явно.

**Подсказка:** паттерн `None` + создание в `__init__`; для `extra_fields` — копия `dict(extra_fields)` внутри `log`.

---

### Задание 2 (среднее): Безопасный mini-calculator

**Условие:** реализуйте функцию `safe_calculate(expression: str) -> float`, которая принимает только числа, `+`, `-`, `*`, `/`, скобки и пробелы. Запрещены имена, вызовы функций, атрибуты.

**Критерии приёмки:**

- `safe_calculate(" (2 + 3) * 4 ")` → `20.0`
- `safe_calculate("__import__('os')")` → `ValueError`
- Не используется `eval`/`exec`.

**Подсказка:** разберите выражение через `ast.parse` и обойдите только разрешённые узлы (`BinOp`, `UnaryOp`, `Constant`), либо используйте библиотеку `simpleeval` с пустым namespace.

---

### Задание 3 (продвинутое): Аудит десериализации в мини-сервисе

**Условие:** ниже псевдо-эндпоинт принимает «сессию» от клиента. Проведите рефакторинг: уберите pickle, добавьте валидацию, защитите модель пользователя от attribute injection.

```python
import pickle
from dataclasses import dataclass


@dataclass
class UserSession:
  user_id: int
  role: str = "user"


def load_session(blob: bytes) -> UserSession:
  return pickle.loads(blob)


def handle_request(blob: bytes, action: str) -> str:
  session = load_session(blob)
  if action == "delete_all" and session.role == "admin":
    return "deleted"
  return "forbidden"
```

**Критерии приёмки:**

- Сессия передаётся как JSON (или signed JWT — опционально) с полями `user_id`, `role`.
- Невалидный `role` отклоняется.
- Нельзя добавить поле `role: admin` через pickle gadget.
- Краткий комментарий в коде: почему pickle неприемлем для HTTP-cookie.

**Подсказка:** `json.loads` + проверка типов; `UserSession` с `__slots__` или `frozen=True`; для продакшена — HMAC-подпись.

## Эталонные решения

<details>
<summary>Задание 1 — RequestLogger</summary>

```python
class RequestLogger:
  def __init__(self, buffer=None):
    self.buffer = [] if buffer is None else buffer

  def log(self, message, extra_fields=None):
    fields = {} if extra_fields is None else dict(extra_fields)
    entry = {"msg": message, **fields}
    self.buffer.append(entry)
    return entry


# Проверка
a = RequestLogger()
b = RequestLogger()
a.log("one")
b.log("two")
assert len(a.buffer) == 1
assert len(b.buffer) == 1
```

</details>

<details>
<summary>Задание 2 — safe_calculate через AST</summary>

```python
import ast
import operator


_OPS = {
  ast.Add: operator.add,
  ast.Sub: operator.sub,
  ast.Mult: operator.mul,
  ast.Div: operator.truediv,
  ast.UAdd: operator.pos,
  ast.USub: operator.neg,
}


def _eval_node(node):
  if isinstance(node, ast.Expression):
    return _eval_node(node.body)
  if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
    return node.value
  if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
    return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
  if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
    return _OPS[type(node.op)](_eval_node(node.operand))
  raise ValueError(f"Запрещённый элемент: {ast.dump(node)}")


def safe_calculate(expression: str) -> float:
  tree = ast.parse(expression, mode="eval")
  return float(_eval_node(tree))
```

</details>

<details>
<summary>Задание 3 — JSON-сессия</summary>

```python
import json
from dataclasses import dataclass

ALLOWED_ROLES = frozenset({"user", "moderator", "admin"})


@dataclass(frozen=True, slots=True)
class UserSession:
  user_id: int
  role: str = "user"

  @classmethod
  def from_json(cls, raw: str) -> "UserSession":
    data = json.loads(raw)
    if not isinstance(data, dict):
      raise ValueError("Ожидался объект JSON")
    user_id = data.get("user_id")
    role = data.get("role", "user")
    if not isinstance(user_id, int) or user_id < 1:
      raise ValueError("Некорректный user_id")
    if role not in ALLOWED_ROLES:
      raise ValueError("Некорректная роль")
    return cls(user_id=user_id, role=role)


def load_session(blob: bytes) -> UserSession:
  # pickle.loads недопустим: произвольное выполнение кода при malicious payload
  return UserSession.from_json(blob.decode("utf-8"))


def handle_request(blob: bytes, action: str) -> str:
  session = load_session(blob)
  if action == "delete_all" and session.role == "admin":
    return "deleted"
  return "forbidden"
```

</details>

## Вопросы для самопроверки

1. **Почему `def f(x=[])` опасно, а `def f(x=0)` — нет?**  
   *Ответ:* список создаётся один раз при определении функции и переиспользуется; `0` — immutable, мутаций нет.

2. **Можно ли считать pickle «шифрованием» данных?**  
   *Ответ:* нет; это формат сериализации без криптографической защиты и с возможностью выполнения кода при загрузке.

3. **Чем `ast.literal_eval` принципиально отличается от `eval`?**  
   *Ответ:* обрабатывает только литералы AST, не вызывает функции и не обращается к builtins для произвольного кода.

4. **Как GIL связан с гонками при `counter += 1`?**  
   *Ответ:* GIL не делает составные операции атомарными; потоки чередуются между инструкциями, теряя обновления ([Модуль 1](01-gil.md)).

5. **Зачем `__slots__` в security-sensitive классах?**  
   *Ответ:* запрещает добавление произвольных атрибутов в `__dict__`, сужая поверхность attribute injection.

6. **Безопасно ли `getattr(obj, request.args['field'])`?**  
   *Ответ:* нет, если имя поля контролирует клиент — возможен доступ к приватным/служебным атрибутам; нужен whitelist.

7. **Почему атрибут класса `items = []` опасен?**  
   *Ответ:* один список разделяется всеми экземплярами, если не переопределить в `__init__`.

## Методические указания

### Для преподавателя

- **Акцент на «своих» багах:** студенты часто ищут «хакеры и CVE», а теряют mutable defaults в своём коде. Начните с живого демо двух вызовов `append` — эффект запоминается.
- **Связка с ООП:** вернитесь к [Модулю 4](04-oop.md) и покажите, как `@dataclass` с `default_factory` решает ту же проблему, что и `None` в `__init__`.
- **Pickle:** покажите `pickletools.dis(payload)` — байткод pickle пугает меньше, чем абстрактное «RCE», но дисассемблер нагляден.
- **Не пугать eval в учебном REPL:** различайте «интерактивная консоль разработчика» и «поле ввода на сайте».

### Для студента

- При code review задавайте вопрос: «Кто ещё владеет этим объектом?»
- Любой default-аргумент mutable — red flag.
- Перед `pickle.load` спросите: «Я бы выполнил `exec` из этого файла?»
- После модуля пройдите [Модуль 6](06-mutations-typevar.md) — копирование и immutability углубят тему shared state.

### Типичные ошибки

| Ошибка | Последствие |
|--------|-------------|
| `except: pass` вокруг `pickle.load` | Скрытый RCE или битые данные |
| `eval` с «ограниченным» builtins | Обход через dunder-цепочки |
| Копия списка забыта при `def f(lst): lst.append(1)` | Мутация аргумента вызывающего |
| Тесты без изоляции глобального state | Flaky CI |

## Дополнительные материалы

### Документация

- [Python docs: pickle — Warning](https://docs.python.org/3/library/pickle.html) — официальное предупреждение о безопасности.
- [ast.literal_eval](https://docs.python.org/3/library/ast.html#ast.literal_eval) — безопасный разбор литералов.
- [PEP 8 — Mutable default argument](https://peps.python.org/pep-0008/#function-and-method-arguments) — стилистическое правило.

### Статьи и инструменты

- *Armin Ronacher*: «Be Careful with Python's Mutable Default Arguments» — классический разбор.
- Bandit (SAST): правила B301 (pickle), B307 (eval).
- OWASP: Deserialization of untrusted data.

### Связь с дальнейшими модулями

- [Модуль 6](06-mutations-typevar.md) — shallow/deep copy, `TypeVar`, immutability.
- [Модуль 7](07-protocols.md) — типизированные контракты вместо «голых» dict.
- [Модуль 8](08-design-patterns.md) — Singleton и DI как ответ на глобальный mutable state.
