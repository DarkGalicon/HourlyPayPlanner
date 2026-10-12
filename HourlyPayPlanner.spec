"""Portable one-folder PyInstaller build for Windows and macOS."""

import sys
from pathlib import Path

import docx
from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).resolve()
migrations = project_root / "src" / "hourly_pay" / "persistence" / "migrations"
migration_files = [
    (str(path), str(Path("hourly_pay/persistence/migrations") / path.relative_to(migrations).parent))
    for path in migrations.rglob("*")
    if path.is_file() and path.suffix in {".py", ".mako"}
]
# python-docx resolves default header/footer resources using a path from its
# `parts` package to `../templates`. Frozen modules do not create that directory.
docx_parts_directory = (
    str(Path(docx.__file__).resolve().parent / "parts" / "__init__.py"),
    "docx/parts",
)

analysis = Analysis(
    [str(project_root / "src" / "hourly_pay" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        *migration_files,
        docx_parts_directory,
        (str(project_root / "src" / "hourly_pay" / "assets" /
             "distribution_template.xlsx"), "hourly_pay/assets"),
    ],
    hiddenimports=[
        "logging.config",
        "alembic.context",
        "alembic.op",
        "sqlalchemy.dialects.sqlite.pysqlite",
        *collect_submodules("holidays.countries"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="HourlyPayPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
bundle_directory = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="HourlyPayPlanner",
)

if sys.platform == "darwin":
    app = BUNDLE(
        bundle_directory,
        name="HourlyPayPlanner.app",
        icon=None,
        bundle_identifier="ru.stgau.hourlypayplanner",
    )
