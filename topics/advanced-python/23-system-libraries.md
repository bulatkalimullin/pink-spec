# Модуль 23: Системные библиотеки Python

## Метаданные

| Параметр | Значение |
|----------|----------|
| Курс | Продвинутый Python |
| Модуль | 10 из 12 |
| Предварительные знания | Базовый Python, работа с файлами, исключения, функции; модуль 9 (Big O) — для понимания I/O-bound задач |
| Следующий модуль | [11-data-structures.md](11-data-structures.md) — структуры данных стандартной библиотеки |
| Ориентировочное время | 5–7 часов |
| Версия Python | 3.11+ |
| Ключевые темы | `os`, `sys`, `pathlib`, `subprocess`, `logging`, `argparse` |

---

## Цели обучения

После изучения модуля вы сможете:

1. **Работать** с операционной системой через `os` и `sys`: переменные окружения, аргументы, кодировки, пути.
2. **Использовать** `pathlib` как современный объектно-ориентированный API для путей файловой системы.
3. **Запускать** внешние процессы через `subprocess` безопасно (без `shell=True` без необходимости).
4. **Настраивать** иерархическое логирование через `logging` вместо `print` в production-коде.
5. **Создавать** CLI-утилиты с `argparse`: позиционные и опциональные аргументы, subcommands, `--help`.
6. **Комбинировать** эти модули в переносимых скриптах и инженерных пайплайнах.

---

## Теория

### 10.1 Зачем системные библиотеки

Python позиционируется как «клей» между компонентами: скрипты деплоя, ETL, devtools, автоматизация CI. Стандартная библиотека даёт **кроссплатформенный** доступ к ОС без сторонних зависимостей.

Типичный стек утилиты:
1. `argparse` — разбор CLI
2. `pathlib` — пути к файлам
3. `logging` — наблюдаемость
4. `subprocess` — вызов git, ffmpeg, kubectl
5. `os` / `sys` — окружение и метаданные интерпретатора

### 10.2 Модуль `os` — интерфейс к ОС

#### Переменные окружения

```python
import os

# Чтение с default
db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")

# Установка (наследуется дочерними процессами текущего процесса)
os.environ["MY_APP_MODE"] = "debug"
```

**Практика:** секреты — только из env или secret manager, не из кода.

#### Работа с путями (legacy)

```python
path = os.path.join("data", "logs", "app.log")
exists = os.path.exists(path)
os.makedirs("output/reports", exist_ok=True)
```

`os.path` — legacy; для нового кода предпочтителен `pathlib`, но `os.path` встречается в legacy-коде.

#### Процесс и права

```python
pid = os.getpid()
cwd = os.getcwd()
# os.chdir("/tmp")  # осторожно — меняет CWD всего процесса
```

#### `os.walk` — обход дерева каталогов

```python
for dirpath, dirnames, filenames in os.walk("project"):
    for name in filenames:
        if name.endswith(".py"):
            print(os.path.join(dirpath, name))
```

Сложность: O(число файлов и каталогов). Для сложной фильтрации удобнее `pathlib.Path.rglob`.

### 10.3 Модуль `sys` — интерпретатор Python

#### Аргументы командной строки

```python
import sys

# sys.argv[0] — имя скрипта
# sys.argv[1:] — аргументы пользователя
args = sys.argv[1:]
```

Для реальных CLI используйте `argparse`; `sys.argv` — низкоуровневый доступ.

#### Потоки ввода-вывода

```python
sys.stdout.write("message\n")
sys.stderr.write("error\n")
```

`print()` пишет в `sys.stdout` и добавляет `end` и flush по умолчанию.

#### Завершение и лимиты

```python
sys.exit(0)   # успех
sys.exit(1)   # ошибка (код для shell)

# Увеличение лимита рекурсии (осторожно!)
# sys.setrecursionlimit(5000)
```

#### Кодировки и платформа

```python
encoding = sys.getdefaultencoding()  # обычно utf-8
platform = sys.platform  # 'linux', 'darwin', 'win32'
```

### 10.4 Модуль `pathlib` — объектные пути (Python 3.4+, рекомендован с 3.6+)

`Path` объединяет чтение, запись и навигацию.

```python
from pathlib import Path

root = Path("project")
config = root / "config" / "settings.toml"

if config.is_file():
    text = config.read_text(encoding="utf-8")

# Создание каталогов
out_dir = Path("output") / "reports"
out_dir.mkdir(parents=True, exist_ok=True)

# Глобальный поиск
for py_file in root.rglob("*.py"):
    if "venv" not in py_file.parts:
        print(py_file)
```

**Ключевые методы:**

| Метод | Назначение |
|-------|------------|
| `read_text` / `write_text` | Текстовые файлы |
| `read_bytes` / `write_bytes` | Бинарные данные |
| `iterdir()` | Содержимое каталога |
| `glob` / `rglob` | Шаблоны поиска |
| `resolve()` | Абсолютный путь с symlink resolution |
| `with_name` / `with_suffix` | Манипуляция компонентами пути |

**Преимущества над `os.path`:** читаемость (`/` operator), единый тип, меньше строкового glue-кода.

### 10.5 Модуль `subprocess` — дочерние процессы

Запуск внешних команд **предпочтительнее** `os.system()`.

#### Базовый безопасный вызов

```python
import subprocess

result = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    capture_output=True,
    text=True,
    check=False,
    timeout=30,
)

if result.returncode == 0:
    commit = result.stdout.strip()
else:
    raise RuntimeError(result.stderr)
```

**Правила безопасности:**
- Передавайте **список аргументов**, не строку.
- **`shell=True`** — только если осознанно нужен shell (инъекции команд!).
- Устанавливайте **`timeout`** для сетевых/долгих команд.
- Используйте **`check=True`** или явную проверку `returncode`.

#### Потоковый ввод-вывод

```python
proc = subprocess.Popen(
    ["grep", "ERROR"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
)
out, _ = proc.communicate("INFO ok\nERROR fail\n", timeout=5)
```

#### `subprocess` vs `asyncio`

Для orchestration многих процессов в async-приложениях — `asyncio.create_subprocess_exec`. Модуль `subprocess` остаётся основой синхронных скриптов.

### 10.6 Модуль `logging` — структурированная наблюдаемость

`print` не масштабируется: нет уровней, ротации, форматов, фильтрации.

#### Иерархия логгеров

```python
import logging

logger = logging.getLogger(__name__)

def process() -> None:
    logger.debug("детали для разработчика")
    logger.info("нормальный ход работы")
    logger.warning("неожиданно, но продолжаем")
    logger.error("ошибка операции")
    logger.critical("критический сбой")
```

Уровни (по возрастанию): DEBUG → INFO → WARNING → ERROR → CRITICAL.

#### Базовая настройка

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

В библиотеках **не вызывайте** `basicConfig` — настраивает приложение.

#### Handlers и форматтеры

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
```

#### Логирование исключений

```python
try:
    risky()
except OSError:
    logger.exception("Не удалось выполнить risky")  # включает traceback
```

#### `logging` vs `structlog` / JSON logs

Для централизованного ELK/Datadog часто добавляют JSON-форматтер (сторонний пакет). Стандартный `logging` — фундамент.

### 10.7 Модуль `argparse` — CLI без боли

#### Минимальный парсер

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datasync",
        description="Синхронизация каталога с удалённым хранилищем",
    )
    parser.add_argument("source", type=str, help="Локальный каталог")
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Увеличить детализацию (-v INFO, -vv DEBUG)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать действия без выполнения",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # args.source, args.verbose, args.dry_run
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Типы аргументов

```python
parser.add_argument("--workers", type=int, default=4, choices=range(1, 33))
parser.add_argument("--format", choices=["json", "csv"], default="json")
parser.add_argument("--since", type=str, metavar="YYYY-MM-DD")
```

#### Subcommands

```python
parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command", required=True)

p_init = sub.add_parser("init", help="Инициализировать проект")
p_init.add_argument("name")

p_run = sub.add_parser("run", help="Запустить пайплайн")
p_run.add_argument("--config", default="config.toml")
```

#### `argparse` vs `click` / `typer`

`argparse` — stdlib, нулевые зависимости. `click`/`typer` — удобнее для сложных CLI, но вне scope модуля.

### 10.8 Сборка: паттерн production-скрипта

```text
1. parse_args() → конфигурация
2. setup_logging(level из -v)
3. Path operations через pathlib
4. бизнес-логика с logger.info/error
5. subprocess для внешних тулов
6. sys.exit(exit_code)
```

### 10.9 Кроссплатформенность и подводные камни

- Пути: `Path` нормализует разделители; для UNC Windows — `Path(r'\\server\share')`.
- `subprocess` на Windows: список аргументов, `shell=False` по умолчанию.
- Кодировка консоли Windows: явно `encoding="utf-8"` при чтении файлов.
- `os.environ` — строки; приведите типы сами (`int(os.environ["PORT"])`).

---

## Примеры кода

### Пример 1: Обход проекта с pathlib

```python
from pathlib import Path


def find_python_files(root: Path, *, skip_dirs: set[str] | None = None) -> list[Path]:
    skip = skip_dirs or {".git", ".venv", "venv", "__pycache__", "node_modules"}
    result: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        result.append(path)
    return sorted(result)


if __name__ == "__main__":
    files = find_python_files(Path("."))
    print(f"Найдено {len(files)} .py файлов")
    for p in files[:5]:
        print(f"  {p}")
```

### Пример 2: Безопасный git wrapper

```python
from __future__ import annotations

import subprocess
from typing import Sequence


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: str | None = None) -> str:
    cmd: Sequence[str] = ("git", *args)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git failed: {args}")
    return result.stdout.strip()


if __name__ == "__main__":
    print(git("rev-parse", "--abbrev-ref", "HEAD"))
```

### Пример 3: Полноценный CLI с logging

```python
"""backup_cli.py — резервное копирование каталога."""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Резервное копирование каталога")
    parser.add_argument("source", type=Path, help="Исходный каталог")
    parser.add_argument(
        "-d", "--dest",
        type=Path,
        default=Path("backups"),
        help="Каталог для бэкапов",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def backup(source: Path, dest_root: Path, *, dry_run: bool) -> Path:
    logger = logging.getLogger("backup")
    if not source.is_dir():
        raise NotADirectoryError(f"Не каталог: {source}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = dest_root / f"{source.name}_{stamp}"

    logger.info("Источник: %s", source.resolve())
    logger.info("Цель: %s", target)

    if dry_run:
        logger.warning("DRY RUN — копирование не выполняется")
        return target

    dest_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    logger.info("Готово: %s", target)
    return target


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)
    logger = logging.getLogger("backup")

    try:
        backup(args.source, args.dest, dry_run=args.dry_run)
    except (OSError, NotADirectoryError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Пример 4: Чтение конфигурации из окружения

```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    debug: bool


def load_config() -> AppConfig:
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8000"))
    debug = os.environ.get("APP_DEBUG", "0").lower() in {"1", "true", "yes"}
    return AppConfig(host=host, port=port, debug=debug)
```

### Пример 5: Пайплайн subprocess с логированием

```python
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_formatter(project_dir: Path) -> None:
    """Запуск ruff format (если установлен)."""
    cmd = ["ruff", "format", str(project_dir)]
    logger.info("Выполняем: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except FileNotFoundError:
        logger.warning("ruff не найден в PATH")
    except subprocess.CalledProcessError as exc:
        logger.error("ruff завершился с кодом %s", exc.returncode)
        raise
```

### Пример 6: Комбинация sys + argparse exit codes

```python
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()
    if args.fail:
        print("Ошибка", file=sys.stderr)
        sys.exit(2)
    print("OK")


if __name__ == "__main__":
    main()
```

---

## Trade-off: компромиссы

| Решение | Плюсы | Минусы | Когда выбирать |
|---------|-------|--------|----------------|
| `pathlib.Path` | Читаемость, `/` operator, rich API | Незначительный overhead vs строки | Новый код, файловые утилиты |
| `os.path` + строки | Привычно в legacy | Verbose, легко ошибиться со слешами | Поддержка старого кода |
| `subprocess.run([...])` | Безопасность, контроль | Verbose для сложных shell-пайпов | 95% случаев |
| `subprocess` + `shell=True` | Однострочные shell-пайпы | Риск command injection | Только доверенный ввод |
| `logging` | Уровни, handlers, ротация | Настройка сложнее print | Production, библиотеки |
| `print` | Мгновенно для отладки | Нет структуры, сложно фильтровать | REPL, одноразовые скрипты |
| `argparse` | Stdlib, автогенерация `--help` | Многословный код | CLI без зависимостей |
| `click` / `typer` | Декораторы, красивый UX | Внешняя зависимость | Богатые CLI продукты |
| `os.environ` для config | 12-factor apps | Всё строки, нет валидации | Контейнеры, деплой |
| Файл config.toml/yaml | Сложная конфигурация | Ещё один артефакт | Много параметров |

---

## Практические задания

### Задание 1 (базовое): Инвентаризация каталога

Напишите скрипт `dir_stats.py`:

**Требования:**
- Позиционный аргумент `directory` (тип `Path`).
- Опция `--pattern` (default `*`) для фильтра glob.
- Вывод: число файлов, суммарный размер в байтах, топ-5 самых больших файлов.
- Логирование INFO при старте и ERROR при несуществующем каталоге.
- Код возврата 1 при ошибке, 0 при успехе.

**Пример:**
```bash
python dir_stats.py ./src --pattern "*.py"
```

---

### Задание 2 (среднее): Git log exporter

Создайте `git_export.py`:

1. Subcommand `export`: аргумент `repo` (Path), опции `--since` (дата), `-o` / `--output` (файл).
2. Внутри — вызов `git -C <repo> log --since=... --pretty=format:%H|%an|%s` через `subprocess`.
3. Результат записать в output через `pathlib` (UTF-8).
4. При отсутствии git в PATH — понятное сообщение в stderr и exit code 127.
5. `--verbose` включает DEBUG-логи с полной командой.

---

### Задание 3 (продвинутое): Мини-оркестратор задач

Реализуйте `task_runner.py` с subcommands:

- `run <script.py>` — запуск `python script.py` с захватом stdout/stderr в `logs/<timestamp>_<name>.log`.
- `env-show` — печать переменных окружения с префиксом `TASK_` (без значений секретов: маскируйте значения длиннее 8 символов как `***`).

**Требования:**
- `argparse` subparsers, `logging` с RotatingFileHandler на `logs/runner.log`.
- Таймаут 300 с на запуск скрипта.
- Таблица exit codes в docstring модуля.

---

## Эталонные решения

<details>
<summary>Задание 1 — dir_stats.py</summary>

```python
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Статистика каталога")
    p.add_argument("directory", type=Path)
    p.add_argument("--pattern", default="*")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    log = logging.getLogger("dir_stats")
    args = parse_args()

    directory: Path = args.directory
    if not directory.is_dir():
        logging.error("Каталог не существует: %s", directory)
        return 1

    log.info("Сканируем %s", directory.resolve())
    files = [p for p in directory.rglob(args.pattern) if p.is_file()]

    total_size = sum(f.stat().st_size for f in files)
    top5 = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:5]

    print(f"Файлов: {len(files)}")
    print(f"Суммарный размер: {total_size} байт")
    print("Топ-5:")
    for f in top5:
        print(f"  {f.stat().st_size:>12}  {f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

</details>

<details>
<summary>Задание 2 — git_export.py (фрагмент)</summary>

```python
import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path


def run_git_log(repo: Path, since: str | None) -> str:
    if shutil.which("git") is None:
        print("git не найден в PATH", file=sys.stderr)
        raise SystemExit(127)

    cmd = ["git", "-C", str(repo), "log", "--pretty=format:%H|%an|%s"]
    if since:
        cmd.insert(-1, f"--since={since}")

    logging.debug("CMD: %s", cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    export = sub.add_parser("export")
    export.add_argument("repo", type=Path)
    export.add_argument("--since")
    export.add_argument("-o", "--output", type=Path, required=True)
    export.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    text = run_git_log(args.repo, args.since)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

</details>

<details>
<summary>Задание 3 — task_runner.py (скелет run)</summary>

```python
import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


def mask_secret(value: str) -> str:
    return "***" if len(value) > 8 else value


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler("logs/runner.log", maxBytes=1_000_000, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])


def cmd_run(script: Path) -> int:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = log_dir / f"{stamp}_{script.stem}.log"

    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    out_file.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    logging.info("Завершено %s код=%s лог=%s", script, proc.returncode, out_file)
    return proc.returncode


def cmd_env_show() -> int:
    for key, val in sorted(os.environ.items()):
        if key.startswith("TASK_"):
            print(f"{key}={mask_secret(val)}")
    return 0


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("script", type=Path)
    p_env = sub.add_parser("env-show")
    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args.script)
    if args.command == "env-show":
        return cmd_env_show()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

</details>

---

## Вопросы для самопроверки

1. Чем `Path / "subdir"` лучше `os.path.join` для читаемости?
2. Почему `subprocess.run("rm -rf /", shell=True)` опасен при пользовательском вводе?
3. Какой уровень логирования по умолчанию у root logger до `basicConfig`?
4. Зачем в библиотеках использовать `logging.getLogger(__name__)` вместо root?
5. Как передать список файлов в argparse как `nargs='+'`?
6. Что вернёт `sys.exit(0)` для родительского shell?
7. Как создать каталог `a/b/c`, если `a` и `b` ещё не существуют, одной операцией в pathlib?
8. Чем `capture_output=True` отличается от перенаправления в файл вручную?
9. Где хранить секреты: в `os.environ`, в argparse или в коде?
10. Когда `os.walk` предпочтительнее `Path.rglob`?

---

## Методические указания

### Для студента

1. Пишите CLI с `--help` с первого дня — это документация.
2. Замените `print` на `logging` в заданиях 2–3 и сравните удобство отладки.
3. На Linux проверьте `echo $?` после exit codes; на Windows — `echo %ERRORLEVEL%`.
4. Прочитайте stderr при падении subprocess — там обычно причина.
5. Изучите `shutil` как дополнение к pathlib для copy/move/tree.

### Для преподавателя

- **Демо live:** сломать subprocess (неверный путь к git) и разобрать traceback vs logger.exception.
- **Безопасность:** обязательная мини-лекция про injection в `shell=True`.
- Парное программирование на задании 3: один пишет argparse, другой — logging handlers.
- Критерии оценки: корректность (50%), идиоматичность pathlib/logging (30%), UX CLI (20%).

### Типичные ошибки

- Забыть `encoding="utf-8"` при `read_text`/`write_text` на Windows.
- Логировать на уровне INFO в цикле по миллиону файлов — I/O bottleneck.
- Путать `Path("rel")` с абсолютным путём — использовать `resolve()`.

---

## Дополнительные материалы

### Документация Python 3.11+

- [os — Miscellaneous operating system interfaces](https://docs.python.org/3/library/os.html)
- [sys — System-specific parameters](https://docs.python.org/3/library/sys.html)
- [pathlib — Object-oriented filesystem paths](https://docs.python.org/3/library/pathlib.html)
- [subprocess — Subprocess management](https://docs.python.org/3/library/subprocess.html)
- [logging — Logging facility](https://docs.python.org/3/library/logging.html)
- [argparse — Parser for command-line options](https://docs.python.org/3/library/argparse.html)

### Смежные модули stdlib

- `shutil` — высокоуровневые операции с файлами
- `tempfile` — временные файлы и каталоги
- `glob` — шаблоны имён (альтернатива pathlib.glob)

### Статьи и практики

- [The Twelve-Factor App: Config](https://12factor.net/config) — конфигурация через окружение
- Real Python: «Python subprocess», «Logging in Python», «Argparse Tutorial»

### Связь с другими модулями

- **Модуль 9:** профилирование скриптов обхода больших деревьев файлов
- **Модуль 11:** `dataclass` для конфигурации (пример 4)
- **Модуль 12:** декомпозиция CLI на функции, тестируемые без subprocess
