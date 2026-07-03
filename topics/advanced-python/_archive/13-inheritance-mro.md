# Модуль 13. Наследование, MRO и функция super()

> Углублённое изучение механизма разрешения методов (Method Resolution Order), алгоритма C3-линеаризации, проблемы «ромба» и корректного использования `super()` в иерархиях множественного наследования.

## Метаданные

| Параметр | Значение |
|----------|----------|
| Номер модуля | 13 |
| Название | Наследование, MRO и super() |
| Предварительные знания | Модуль 04 (ООП в Python): классы, наследование, полиморфизм, инкапсуляция |
| Следующий модуль | [14-mixins.md](14-mixins.md) — Миксины |
| Ориентировочное время | 4–5 часов (теория + 3 задания) |
| Версия Python | 3.11+ |
| Сложность | Средняя → продвинутая |

## Цели обучения

После прохождения модуля студент сможет:

1. Объяснить, что такое MRO (Method Resolution Order) и зачем он нужен в Python.
2. Описать алгоритм C3-линеаризации и предсказать порядок поиска методов в иерархии классов.
3. Распознать и решить проблему «ромба» (diamond problem) с помощью MRO и `super()`.
4. Корректно вызывать методы родительских классов через `super()` в цепочках множественного наследования.
5. Диагностировать ошибки `TypeError: Cannot create a consistent method resolution order` при проектировании иерархий.
6. Использовать `__mro__`, `mro()` и `inspect.getmro()` для отладки наследования.

## Теория

### 13.1. Наследование в Python: краткий обзор

Наследование позволяет создавать новый класс на основе существующего, переиспользуя его атрибуты и методы. В Python поддерживается **множественное наследование** — класс может иметь несколько базовых классов одновременно:

```python
class Animal:
    def speak(self) -> str:
        return "..."

class Flyable:
    def fly(self) -> str:
        return "flying"

class Duck(Animal, Flyable):
    def speak(self) -> str:
        return "quack"
```

Когда вы вызываете `duck.speak()`, интерпретатор должен решить, **какой** метод `speak` вызвать, если он определён в нескольких предках. Для этого существует MRO.

### 13.2. Method Resolution Order (MRO)

**MRO** — упорядоченный список классов, в котором Python ищет атрибуты и методы при обращении к объекту. Порядок определяется при создании класса и хранится в атрибуте `__mro__` (кортеж) или доступен через метод `mro()` (список).

```python
class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass

print(D.__mro__)
# (<class 'D'>, <class 'B'>, <class 'C'>, <class 'A'>, <class 'object'>)
```

**Правила поиска атрибута:**

1. Сначала ищется в самом классе (`D`).
2. Затем в первом родителе из MRO (`B`).
3. Затем во втором (`C`), и так далее до `object`.
4. Если атрибут не найден — `AttributeError`.

MRO гарантирует, что каждый класс в иерархии появляется **ровно один раз** и что порядок согласован с порядком объявления базовых классов.

### 13.3. Алгоритм C3-линеаризации

Начиная с Python 2.3 (и во всех версиях Python 3), MRO вычисляется алгоритмом **C3-линеаризации**. Это детерминированный алгоритм, который строит линейный порядок классов, удовлетворяющий трём свойствам:

1. **Локальный порядок предшественников (L):** если класс `A` наследует `B` перед `C`, то `B` идёт раньше `C` в MRO класса `A`.
2. **Монотонность:** если `A` предшествует `B` в MRO какого-либо предка, то `A` предшествует `B` и в MRO потомка.
3. **Единственное появление:** каждый класс встречается в MRO не более одного раза.

**Упрощённая интуиция C3 для класса `D(B, C)`:**

```
MRO(D) = D + merge(
    [B] + MRO(B),
    [C] + MRO(C),
    [B, C]   # список прямых родителей
)
```

**Пример пошагово:**

```python
class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass
```

- `MRO(A) = [A, object]`
- `MRO(B) = [B, A, object]`
- `MRO(C) = [C, A, object]`
- `MRO(D) = merge([B,A,object], [C,A,object], [B,C])`
  - Берём `D`, затем `B` (голова первого списка, не в хвостах других)
  - Затем `C`
  - Затем `A`
  - Затем `object`
- Итог: `[D, B, C, A, object]`

### 13.4. Проблема «ромба» (Diamond Problem)

**Diamond problem** возникает, когда один базовый класс наследуется по двум (или более) путям:

```
      A
     / \
    B   C
     \ /
      D
```

Без формального MRO возникли бы вопросы:

- Сколько раз вызывается `A.__init__` при создании `D()`?
- Какой `A.method` получит `D` — через `B` или через `C`?

В Python C3-линеаризация решает первый вопрос однозначно: `A` встречается в MRO **один раз**, после всех промежуточных классов:

```python
D.__mro__  # (D, B, C, A, object)
```

**Классический пример с «двойной инициализацией»:**

```python
class Base:
    def __init__(self) -> None:
        print("Base.__init__")

class Left(Base):
    def __init__(self) -> None:
        print("Left.__init__")
        Base.__init__(self)  # ЯВНЫЙ вызов — антипаттерн!

class Right(Base):
    def __init__(self) -> None:
        print("Right.__init__")
        Base.__init__(self)  # Base вызовется дважды!

class Diamond(Left, Right):
    def __init__(self) -> None:
        print("Diamond.__init__")
        Left.__init__(self)
        Right.__init__(self)

Diamond()
# Diamond.__init__
# Left.__init__
# Base.__init__
# Right.__init__
# Base.__init__   ← Base инициализирован дважды!
```

Правильный подход — использовать `super()` (см. раздел 13.5).

### 13.5. Функция super(): не только «вызов родителя»

Распространённое заблуждение: `super()` всегда вызывает **непосредственного** родительского класса. На самом деле `super()` делегирует вызов **следующему классу в MRO** текущего класса.

```python
class Base:
    def __init__(self) -> None:
        print("Base.__init__")

class Left(Base):
    def __init__(self) -> None:
        print("Left.__init__")
        super().__init__()

class Right(Base):
    def __init__(self) -> None:
        print("Right.__init__")
        super().__init__()

class Diamond(Left, Right):
    def __init__(self) -> None:
        print("Diamond.__init__")
        super().__init__()

Diamond()
# Diamond.__init__
# Left.__init__
# Right.__init__
# Base.__init__   ← Base вызван ровно один раз
```

**Как работает `super()` внутри `Left.__init__`:**

- Текущий класс: `Left`
- MRO `Diamond`: `(Diamond, Left, Right, Base, object)`
- `super(Left, self).__init__()` → следующий после `Left` — это `Right`, а не `Base`!

Это называется **кооперативное множественное наследование** (cooperative multiple inheritance): каждый класс в цепочке вызывает `super()`, и вместе они проходят MRO ровно один раз.

**Формы вызова super() в Python 3:**

```python
super().__init__()           # внутри метода класса — рекомендуемый способ
super(Left, self).__init__() # эквивалент в Python 3 при вызове из Left
super(Diamond, self).__init__() # начать цепочку с Diamond
```

### 13.6. Ошибки несовместимого MRO

C3 не всегда может построить согласованный порядок. Тогда Python выбрасывает `TypeError` при **определении** класса:

```python
class X: pass
class Y: pass
class A(X, Y): pass
class B(Y, X): pass

# class C(A, B): pass
# TypeError: Cannot create a consistent method resolution order (MRO) for bases X, Y
```

Здесь `A` требует `X` перед `Y`, а `B` — `Y` перед `X`. Эти требования несовместимы.

**Практические рекомендации при проектировании:**

- Избегайте «перекрёстных» иерархий с противоречивым порядком баз.
- Предпочитайте плоские миксины (см. модуль 14) вместо глубоких ромбовидных деревьев.
- Проверяйте MRO на этапе проектирования: `python -c "class D(A,B): pass; print(D.mro())"`.

### 13.7. MRO и встроенные типы

MRO применяется ко всем новым классам, включая те, что наследуют встроенные типы:

```python
class MyList(list):
    def first(self):
        return self[0] if self else None

print(MyList.mro())
# [MyList, list, object]
```

При множественном наследовании от встроенных и пользовательских типов порядок также определяется C3. Однако смешивание C-расширений и Python-классов иногда даёт неочевидный MRO — всегда проверяйте `__mro__`.

### 13.8. Инструменты отладки MRO

```python
import inspect

class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass

# Кортеж классов
print(D.__mro__)

# Список (метод класса)
print(D.mro())

# inspect — удобно для анализа чужого кода
print(inspect.getmro(D))

# Проверка, откуда пришёл метод
print(D.speak.__qualname__ if hasattr(D, 'speak') else "no speak")
print(B.__bases__)  # прямые родители
```

**Визуализация в REPL:**

```python
def print_mro(cls: type) -> None:
    for i, c in enumerate(cls.mro()):
        print(f"{i}: {c.__name__}")

print_mro(D)
```

### 13.9. super() и статические/классовые методы

`super()` работает и с `@classmethod`:

```python
class Base:
    @classmethod
    def create(cls) -> "Base":
        return cls()

class Child(Base):
    @classmethod
    def create(cls) -> "Child":
        obj = super().create()
        # дополнительная настройка
        return obj
```

Для `@staticmethod` `super()` обычно не нужен — статические методы не участвуют в полиморфной цепочке.

### 13.10. Сравнение: явный вызов родителя vs super()

| Подход | Поведение при одиночном наследовании | Поведение при множественном наследовании |
|--------|--------------------------------------|------------------------------------------|
| `Parent.method(self)` | Всегда вызывает `Parent` | Может пропустить классы в MRO; риск двойного вызова |
| `super().method()` | Следующий в MRO | Корректная кооперативная цепочка |

**Правило:** при множественном наследовании **всегда** используйте кооперативный стиль с `super()` во всех классах цепочки.

## Примеры кода

### Пример 1. Предсказание MRO

```python
class O: pass
class A(O): pass
class B(O): pass
class C(A, B): pass
class D(A): pass
class E(C, D): pass

assert E.mro() == [E, C, A, D, B, O, object]
```

### Пример 2. Кооперативные миксины с super()

```python
class LoggingMixin:
    def __init__(self, *args, **kwargs) -> None:
        print(f"LoggingMixin: init {self.__class__.__name__}")
        super().__init__(*args, **kwargs)

class TimestampMixin:
    def __init__(self, *args, **kwargs) -> None:
        print("TimestampMixin: setting timestamp")
        super().__init__(*args, **kwargs)

class Entity:
    def __init__(self, name: str) -> None:
        self.name = name
        print(f"Entity: name={name}")

class User(LoggingMixin, TimestampMixin, Entity):
    pass

u = User("alice")
# LoggingMixin: init User
# TimestampMixin: setting timestamp
# Entity: name=alice
```

### Пример 3. Переопределение метода с super()

```python
class Storage:
    def save(self, data: bytes) -> None:
        print(f"Storage: saving {len(data)} bytes")

class CompressedStorage(Storage):
    def save(self, data: bytes) -> None:
        compressed = data  # упрощение: без реального сжатия
        print(f"CompressedStorage: compressed to {len(compressed)} bytes")
        super().save(compressed)

class EncryptedStorage(Storage):
    def save(self, data: bytes) -> None:
        encrypted = data  # упрощение
        print(f"EncryptedStorage: encrypted")
        super().save(encrypted)

class SecureCompressedStorage(EncryptedStorage, CompressedStorage):
    def save(self, data: bytes) -> None:
        print("SecureCompressedStorage: pipeline start")
        super().save(data)

SecureCompressedStorage().save(b"hello")
```

MRO: `SecureCompressedStorage → EncryptedStorage → CompressedStorage → Storage → object`.

### Пример 4. Диагностика AttributeError через MRO

```python
class A:
    def method(self) -> str:
        return "A"

class B(A):
    pass

class C:
    def method(self) -> str:
        return "C"

class D(B, C):
    pass

d = D()
print(d.method())  # "A" — B не переопределяет, ищем дальше по MRO
print(D.mro())     # [D, B, A, C, object]
```

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| Одиночное наследование | Простота, предсказуемость | Дублирование кода, слабая композиция | Небольшие иерархии, доменные модели |
| Множественное наследование + super() | Гибкая композиция поведения | Сложность отладки, риск ошибок MRO | Миксины, кооперативные pipeline-классы |
| Явный вызов `Base.method(self)` | Понятно, куда идёт вызов | Ломает MRO при ромбе, двойные вызовы | Только одиночное наследование |
| Композиция вместо наследования | Явные зависимости, тестируемость | Больше boilerplate | Когда иерархия становится запутанной |
| `__mro__` / inspect при ревью | Раннее обнаружение проблем | Дополнительное время на анализ | Любое множественное наследование |

## Практические задания

### Задание 1 (базовое). Предсказание MRO

Даны классы:

```python
class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass
class E(C, B): pass
```

**Задачи:**

1. Без запуска кода запишите MRO для `D` и `E`.
2. Запустите код и проверьте себя через `D.mro()` и `E.mro()`.
3. Объясните, почему порядок `B` и `C` различается в `D` и `E`.

**Критерии:** корректный MRO, объяснение роли порядка базовых классов в объявлении.

### Задание 2 (среднее). Исправление ромба

Дан «сломанный» код:

```python
class Base:
    def __init__(self) -> None:
        self.data: dict = {}
        print("Base init")

class Left(Base):
    def __init__(self) -> None:
        self.data["left"] = True
        print("Left init")
        Base.__init__(self)

class Right(Base):
    def __init__(self) -> None:
        self.data["right"] = True
        print("Right init")
        Base.__init__(self)

class Child(Left, Right):
    def __init__(self) -> None:
        print("Child init")
        Left.__init__(self)
        Right.__init__(self)
```

**Задачи:**

1. Запустите код и зафиксируйте, сколько раз вызывается `Base.__init__`.
2. Перепишите все `__init__` с кооперативным `super()`.
3. Убедитесь, что `Child().data` содержит и `"left"`, и `"right"`, а `Base.__init__` вызван один раз.

### Задание 3 (продвинутое). Pipeline обработки с MRO

Реализуйте систему обработки HTTP-запроса через цепочку middleware-классов:

- `AuthMiddleware` — проверяет заголовок `Authorization` (упрощённо: непустая строка).
- `RateLimitMiddleware` — логирует «rate limit ok».
- `Handler` — финальный обработчик, возвращает `{"status": "ok"}`.

Класс `App(AuthMiddleware, RateLimitMiddleware, Handler)` должен вызывать метод `handle(request: dict) -> dict`, проходя всю цепочку через `super().handle(request)`.

**Требования:**

- Каждый уровень добавляет ключ в `request["trace"]` (список строк).
- При отсутствии `Authorization` `AuthMiddleware` возвращает `{"status": "unauthorized"}` без вызова `super()`.
- Напишите тесты на MRO и на успешный/неуспешный сценарий.

## Эталонные решения

<details>
<summary>Задание 1 — решение</summary>

```python
class A: pass
class B(A): pass
class C(A): pass
class D(B, C): pass
class E(C, B): pass

# D: merge([B,A,obj], [C,A,obj], [B,C]) → D, B, C, A, object
assert D.mro() == [D, B, C, A, object]

# E: merge([C,A,obj], [B,A,obj], [C,B]) → E, C, B, A, object
assert E.mro() == [E, C, B, A, object]
```

**Объяснение:** в объявлении `class D(B, C)` первым указан `B`, поэтому в MRO `B` идёт раньше `C`. В `class E(C, B)` — наоборот. C3 сохраняет локальный порядок базовых классов.

</details>

<details>
<summary>Задание 2 — решение</summary>

```python
class Base:
    def __init__(self) -> None:
        self.data: dict = {}
        print("Base init")

class Left(Base):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.data["left"] = True
        print("Left init")

class Right(Base):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.data["right"] = True
        print("Right init")

class Child(Left, Right):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        print("Child init")

c = Child()
# Child init → Left init → Right init → Base init
assert c.data == {"left": True, "right": True}
```

**Ключевой момент:** `super()` в `Left` вызывает `Right.__init__`, а не `Base.__init__` напрямую. Инициализация `self.data` должна произойти в `Base` до установки ключей — поэтому `super().__init__()` вызывается **до** модификации `self.data` в `Left`/`Right`, либо `Base` инициализирует словарь первым в цепочке.

Альтернативный порядок (сначала super, потом модификация):

```python
class Left(Base):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.data["left"] = True
```

</details>

<details>
<summary>Задание 3 — решение</summary>

```python
from __future__ import annotations

class Handler:
    def handle(self, request: dict) -> dict:
        request.setdefault("trace", []).append("handler")
        return {"status": "ok", "trace": request["trace"]}

class RateLimitMiddleware:
    def handle(self, request: dict) -> dict:
        request.setdefault("trace", []).append("rate_limit")
        print("rate limit ok")
        return super().handle(request)

class AuthMiddleware:
    def handle(self, request: dict) -> dict:
        request.setdefault("trace", []).append("auth")
        auth = request.get("headers", {}).get("Authorization", "")
        if not auth:
            return {"status": "unauthorized", "trace": request["trace"]}
        return super().handle(request)

class App(AuthMiddleware, RateLimitMiddleware, Handler):
    pass

# Тесты
assert App.mro()[0] is App
app = App()

ok = app.handle({"headers": {"Authorization": "Bearer x"}})
assert ok["status"] == "ok"
assert ok["trace"] == ["auth", "rate_limit", "handler"]

fail = app.handle({"headers": {}})
assert fail["status"] == "unauthorized"
assert fail["trace"] == ["auth"]
```

</details>

## Вопросы для самопроверки

1. Что такое MRO и где его посмотреть у класса?
2. Какие три свойства обеспечивает C3-линеаризация?
3. Почему `Base.__init__(self)` в ромбовидной иерархии может вызвать двойную инициализацию?
4. Куда «смотрит» `super()` внутри метода класса `Left` при MRO `(D, Left, Right, Base, object)`?
5. При каких условиях Python выбрасывает `TypeError: Cannot create a consistent method resolution order`?
6. В чём разница между `D.__mro__` и `D.mro()`?
7. Нужно ли вызывать `super()` во **всех** классах кооперативной цепочки? Что будет, если забыть в одном?
8. Как MRO влияет на поиск не только методов, но и атрибутов класса?

<details>
<summary>Ответы</summary>

1. Method Resolution Order — порядок поиска атрибутов; `Cls.__mro__` или `Cls.mro()`.
2. Локальный порядок предшественников, монотонность, единственное появление каждого класса.
3. Потому что `Left` и `Right` каждый явно вызывают `Base.__init__`, не зная о совместном предке.
4. На следующий класс после `Left` в MRO — `Right`, а не `Base`.
5. Когда требования к порядку предшественников из разных веток противоречат друг другу.
6. `__mro__` — кортеж; `mro()` — список (результат тот же).
7. Да, нужно во всех участниках цепочки; иначе часть классов будет пропущена.
8. Атрибуты ищутся по тому же MRO; первое совпадение побеждает.

</details>

## Методические указания для преподавателя

### Акценты лекции

- Начните с **живого примера ромба** и двойного вызова `Base.__init__` — студенты часто «узнают» баг из своего кода.
- Нарисуйте DAG иерархии на доске, затем покажите линеаризацию C3 пошагово для `D(B, C)`.
- Подчеркните: `super()` — это **не** `Parent`, а **next in MRO**.

### Типичные ошибки студентов

| Ошибка | Как объяснить |
|--------|---------------|
| `Parent.method(self)` в ромбе | Покажите двойной вызов в REPL |
| Забытый `super()` в одном миксине | Цепочка обрывается — часть логики не выполняется |
| Путаница MRO объекта и класса | MRO — свойство **класса**, не экземпляра |
| Попытка «починить» MRO переименованием | C3 — алгоритм; порядок баз в объявлении критичен |

### Тайминг (4–5 ч)

| Блок | Время |
|------|-------|
| Теория MRO и C3 | 90 мин |
| Разбор super() и ромба | 60 мин |
| Примеры в REPL | 30 мин |
| Задание 1–2 | 60 мин |
| Задание 3 + разбор | 60 мин |

### Связь с другими модулями

- Модуль 14 (миксины) опирается на кооперативный `super()`.
- Модуль 04 (ООП) — базовое наследование без MRO.
- Модуль 08 (паттерны) — Template Method часто использует `super()`.

## Дополнительные материалы

### Документация

- [Python Data Model — Method resolution order](https://docs.python.org/3/glossary.html#term-method-resolution-order)
- [The Python 2.3 Method Resolution Order (MRO)](https://www.python.org/download/releases/2.3/mro/) — историческая статья Michele Simionato
- [super() — Built-in Functions](https://docs.python.org/3/library/functions.html#super)

### Книги и статьи

- Luciano Ramalho, *Fluent Python*, 2nd ed., глава о наследовании и миксинах
- Raymond Hettinger, «Python's super() considered super!» (PyCon talk)

### Упражнения для углубления

1. Реализуйте `class_consistent_mro(*bases)` — функцию, проверяющую, можно ли создать класс с данными базами (без `TypeError`).
2. Изучите MRO у `collections.abc` и `typing` Protocol — как stdlib решает сложные иерархии.
3. Сравните MRO в Python и Java (single inheritance + interfaces) — дискуссия на 15 минут.
