# 03. Architecture

## Общий подход

Desktop monolith с четким разделением слоев.

```text
PySide6 UI
   ↓
Application Services / Use Cases
   ↓
Domain
   ↓
Repositories
   ↓
SQLite / filesystem
```

Отдельные adapters:

```text
XLSX Importer → Domain
Domain → DOCX Exporter
```

## Предлагаемая структура

```text
src/hourly_pay/
├── __init__.py
├── __main__.py
├── app.py
├── domain/
│   ├── enums.py
│   ├── models.py
│   ├── rules.py
│   └── errors.py
├── application/
│   ├── import_workload.py
│   ├── calculate_hourly.py
│   ├── allocate_months.py
│   ├── generate_schedule.py
│   └── export_statement.py
├── importers/
│   ├── base.py
│   └── nagr_xlsx_v1.py
├── exporters/
│   └── hourly_docx.py
├── persistence/
│   ├── db.py
│   ├── orm_models.py
│   ├── repositories.py
│   └── migrations/
├── scheduler/
│   ├── availability.py
│   └── generator.py
├── ui/
│   ├── main_window.py
│   ├── pages/
│   ├── dialogs/
│   └── models/
├── config/
│   └── defaults.py
└── resources/
    └── templates/
```

## Domain first

Domain не импортирует PySide6, openpyxl, python-docx или SQLAlchemy.

### Domain содержит

- Teacher
- WorkloadSource
- WorkloadItem
- HourlyCalculation
- HourlySelection
- MonthlyAllocation
- AvailabilityRule
- Lesson
- Warning/Anomaly

## Application layer

Use cases должны быть вызываемы из unit tests без UI.

Пример:

```python
result = calculate_hourly_limit(
    effective_rate=Decimal("1.0"),
    fact_hours=Decimal("1080"),
    idpo_hours=Decimal("40"),
    eligible_hours=Decimal("240"),
)
```

## Persistence

SQLite хранить через `platformdirs.user_data_dir()`.

Пример логического пути:

```text
Windows: %APPDATA%/HourlyPayPlanner/hourly_pay.db
macOS:   ~/Library/Application Support/HourlyPayPlanner/hourly_pay.db
```

Не хардкодить эти пути.

## Миграции

Предпочтительно Alembic. Если агент решит отказаться от Alembic, должен быть отдельный, тестируемый механизм migration/versioning DB.

## Конфигурация

Настройки, которые пользователь может менять, должны храниться в БД или отдельном config-файле:

- временные слоты;
- allowlist видов контроля;
- праздничные/исключенные даты;
- mapping подписи вида занятия для DOCX;
- политика заполнения шапки;
- default semester settings.

## Логирование

Использовать стандартный `logging`.

Лог должен помогать диагностировать импорт, но **не писать в лог паспортные/налоговые/страховые данные**.
