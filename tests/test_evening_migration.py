import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_existing_selection_gets_safe_evening_default(tmp_path: Path) -> None:
    database = tmp_path / "upgrade.db"
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "src/hourly_pay/persistence/migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, "0006_semester_practice_starts")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO hourly_selections (teacher_id, workload_item_id, selected_hours) "
            "VALUES (1, 1, 2)"
        )

    command.upgrade(config, "head")

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT selected_hours, prefer_evening FROM hourly_selections"
        ).fetchone() == (2, 0)
