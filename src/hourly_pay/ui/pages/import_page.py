from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.import_workload import ImportWorkloadService
from hourly_pay.domain.errors import DomainError
from hourly_pay.ui.models.import_preview import HEADERS, ImportPreviewTableModel


class ImportPage(QWidget):
    imports_saved = Signal()

    def __init__(self, service: ImportWorkloadService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self.model = ImportPreviewTableModel()

        self.import_button = QPushButton("Импортировать XLSX…", self)
        self.import_button.setObjectName("selectXlsxButton")
        self.import_button.clicked.connect(self._select_files)
        self.confirm_button = QPushButton("Подтвердить импорт", self)
        self.confirm_button.setObjectName("confirmImportButton")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self._confirm_import)

        self.table = QTableView(self)
        self.table.setObjectName("importPreviewTable")
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.selectionModel().currentRowChanged.connect(self._show_warnings)

        self.warning_details = QPlainTextEdit(self)
        self.warning_details.setObjectName("importWarningDetails")
        self.warning_details.setReadOnly(True)
        self.warning_details.setPlaceholderText("Выберите файл, чтобы посмотреть предупреждения.")
        self.warning_details.setMaximumHeight(145)

        self.status_label = QLabel("Выберите один или несколько XLSX-файлов.", self)
        self.status_label.setObjectName("importStatusLabel")
        self.status_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.confirm_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Предупреждения выбранного файла", self))
        layout.addWidget(self.warning_details)
        layout.addWidget(self.status_label)
        self.resize_preview_columns()

    def resize_preview_columns(self) -> None:
        self.table.resizeColumnsToContents()
        metrics = self.table.horizontalHeader().fontMetrics()
        for index, title in enumerate(HEADERS):
            minimum = metrics.horizontalAdvance(title) + 34
            self.table.setColumnWidth(index, max(self.table.columnWidth(index), minimum))

    @Slot()
    def _select_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Импорт индивидуальных планов",
            "",
            "Excel (*.xlsx)",
        )
        if filenames:
            self.load_files([Path(filename) for filename in filenames])

    def load_files(self, paths: list[Path]) -> None:
        batch = self._service.preview_files(paths)
        self.model.set_previews(batch.previews)
        if batch.previews:
            self.table.selectRow(0)
        else:
            self.warning_details.clear()
        has_duplicates = any(preview.is_duplicate for preview in batch.previews)
        has_upgrades = any(preview.is_upgrade for preview in batch.previews)
        self.confirm_button.setEnabled(bool(batch.previews) and not has_duplicates)

        status_parts = [f"Распознано файлов: {len(batch.previews)}."]
        if has_duplicates:
            status_parts.append("Повторно импортированные файлы нужно исключить из выбора.")
        if has_upgrades:
            status_parts.append(
                "Есть файлы старой версии импорта: после повторного импорта "
                "исключите прежние источники в разделе «Преподаватели»."
            )
        if batch.failures:
            details = "\n".join(
                f"{failure.path.name}: {failure.message}" for failure in batch.failures
            )
            status_parts.append(f"Не распознано: {len(batch.failures)}.")
            QMessageBox.warning(
                self,
                "Не все файлы распознаны",
                "Проверьте формат следующих файлов:\n" + details,
            )
        self.status_label.setText(" ".join(status_parts))
        self.resize_preview_columns()

    @Slot()
    def _show_warnings(self) -> None:
        row = self.table.currentIndex().row()
        if not 0 <= row < len(self.model.previews):
            self.warning_details.clear()
            return
        warnings = self.model.previews[row].result.warnings
        if not warnings:
            self.warning_details.setPlainText("Предупреждений нет.")
            return
        self.warning_details.setPlainText(
            "\n".join(
                f"{warning.sheet_name or 'Файл'}"
                f"{f', строка {warning.source_row_number}' if warning.source_row_number else ''}: "
                f"{warning.message}"
                for warning in warnings
            )
        )

    @Slot()
    def _confirm_import(self) -> None:
        try:
            saved = self._service.confirm_imports(self.model.previews)
        except DomainError as error:
            QMessageBox.warning(self, "Импорт не выполнен", str(error))
            return
        self.model.set_previews(())
        self.warning_details.clear()
        self.confirm_button.setEnabled(False)
        self.status_label.setText(f"Импортировано файлов: {len(saved)}.")
        self.imports_saved.emit()
