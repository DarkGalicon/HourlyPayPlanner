from pathlib import Path

from hourly_pay.app import create_main_window


def test_statement_date_is_enabled_by_default(qtbot, tmp_path: Path) -> None:
    window = create_main_window(tmp_path / "documents.db")
    qtbot.addWidget(window)
    try:
        page = window.documents_page
        assert page.date_check.isChecked()
        assert page.statement_date.isEnabled()

        page.date_check.setChecked(False)
        assert not page.statement_date.isEnabled()
        assert window.documents_tabs.count() == 2
        assert window.documents_tabs.tabText(1) == "Распределение XLSX"
        assert not window.distribution_page.export_button.isEnabled()
    finally:
        window.close()
        window.database_engine.dispose()
