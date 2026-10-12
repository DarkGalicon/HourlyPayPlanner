# 12. Сборки Windows и macOS

PyInstaller создаёт приложение для той ОС и архитектуры, на которой запущена
сборка. Используется один `HourlyPayPlanner.spec` и режим `onedir`.

## Подготовка и проверка

На Windows и macOS из корня проекта:

```bash
uv sync --locked --all-groups
uv run --no-sync pytest -q
uv run --no-sync ruff check .
uv run --no-sync python -m PyInstaller --noconfirm HourlyPayPlanner.spec
```

Проверка собранного приложения запускает Qt без окна, создаёт временную БД
и тестовый DOCX с колонтитулами, а также открывает встроенный XLSX-шаблон
распределения. Так проверяются миграции и ресурсы экспорта;
рабочая БД пользователя не затрагивается.

macOS:

```bash
dist/HourlyPayPlanner.app/Contents/MacOS/HourlyPayPlanner --smoke-test
```

Windows (PowerShell):

```powershell
./dist/HourlyPayPlanner/HourlyPayPlanner.exe --smoke-test
```

Нулевой код завершения означает успешный запуск. Для обычного запуска используйте
`.app` на macOS или `.exe` внутри папки `dist/HourlyPayPlanner` на Windows. При
передаче Windows-сборки сохраняйте всю папку, включая `_internal`.

## Платформы

На macOS Intel и Apple Silicon нужны отдельные сборки и проверки на соответствующей
архитектуре. Windows-сборку также нужно выполнить на Windows; результат macOS не
является Windows-приложением.

Локально проверена сборка macOS Apple Silicon. Перед распространением выполнить
визуальную проверку интерфейса и экспорта DOCX на целевых ОС. Публикация macOS
приложения вне машины разработчика может потребовать отдельной подписи и
нотариального заверения Apple.
