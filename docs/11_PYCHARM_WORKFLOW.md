# 11. PyCharm Workflow

## Рекомендуемая версия Python

Python 3.12.x.

Не начинать проект на Python 3.13 до проверки совместимости PySide6/PyInstaller на обеих ОС.

## Создание проекта

В терминале:

```bash
mkdir hourly-pay-planner
cd hourly-pay-planner
uv sync --all-groups
```

В PyCharm:

```text
Settings / Preferences
→ Project
→ Python Interpreter
→ Add Existing
→ <project>/.venv/bin/python        # macOS
→ <project>/.venv/Scripts/python.exe # Windows
```

## Run configuration

Создать Python run config:

```text
Module name: hourly_pay
Working directory: project root
```

Либо запускать:

```bash
uv run python -m hourly_pay
```

## Tests

PyCharm:

```text
Settings → Python Integrated Tools → Default test runner → pytest
```

CLI:

```bash
uv run pytest -q
```

## Ruff

```bash
uv run ruff check .
uv run ruff format .
```

## Private fixtures

Скопировать реальные пользовательские XLSX/DOCX только локально:

```text
tests/fixtures_private/
```

Не коммитить.

Имена можно дать нейтральные:

```text
staff.xlsx
internal_part_time.xlsx
hourly.xlsx
hourly_template.docx
```

## PyCharm + coding agent

Перед началом задачи агент должен прочитать:

```text
AGENTS.md
README.md
соответствующий файл из docs/
```

Для первой задачи дать агенту scope только на importer/domain tests. Не просить сразу построить весь GUI.

## Рекомендуемый порядок задач в IDE

### Task 1

Создать skeleton проекта + domain enums/models + тесты Decimal.

### Task 2

Реализовать `nagr_xlsx_v1.py` и snapshot/report импорта.

### Task 3

SQLite + repositories.

### Task 4

Расчет почасовки.

### Task 5

Monthly allocation.

### Task 6

Schedule generator.

### Task 7

DOCX exporter.

### Task 8

PySide6 UI.

### Task 9

PyInstaller builds Windows/macOS.

## Сборка

Собирать отдельно на каждой ОС.

Windows build не является macOS build и наоборот.

На раннем этапе достаточно `onedir` PyInstaller. `onefile` можно рассмотреть позже, когда приложение стабилизируется.
