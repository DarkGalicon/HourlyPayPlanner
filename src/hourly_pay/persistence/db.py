from pathlib import Path

from alembic import command
from alembic.config import Config
from platformdirs import user_data_path
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

APP_NAME = "HourlyPayPlanner"
DATABASE_FILENAME = "hourly_pay.db"


def default_database_path() -> Path:
    return user_data_path(APP_NAME, appauthor=False) / DATABASE_FILENAME


def create_sqlite_engine(path: Path | None = None) -> Engine:
    database_path = path or default_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def upgrade_database(path: Path | None = None) -> Path:
    database_path = path or default_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config()
    migrations = Path(__file__).with_name("migrations")
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path
