# Стартовый промпт для coding agent

Прочитай `AGENTS.md`, `README.md` и все файлы в `docs/` перед изменением кода.

Мы разрабатываем локальное кроссплатформенное desktop-приложение Windows/macOS на Python 3.12 + PySide6. На первом этапе не делай GUI целиком.

## Первая задача

1. Создай package skeleton `src/hourly_pay` по `docs/03_ARCHITECTURE.md`.
2. Реализуй domain enums/models без зависимости от PySide6/openpyxl/SQLAlchemy.
3. Реализуй `importers/nagr_xlsx_v1.py` по `docs/05_XLSX_IMPORT_SPEC.md`.
4. Напиши unit tests на importer и anomaly detection по `docs/09_TEST_PLAN.md`.
5. Реальные sample-файлы находятся локально в `tests/fixtures_private/` и не должны коммититься.
6. Не реализуй пока DOCX export, scheduler и полноценный GUI.
7. Не изменяй бизнес-правила и не делай предположений из `docs/10_OPEN_QUESTIONS.md` без явного решения.

После выполнения покажи:

- созданную структуру файлов;
- какие поля извлекаются из XLSX;
- отчет по трем sample-файлам;
- найденные warnings/anomalies;
- результаты `pytest` и `ruff check .`.
