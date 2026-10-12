"""User choices needed to export the whole academic-year XLSX distribution."""

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.distribution_export import DistributionExportService
from hourly_pay.domain.errors import DomainError
from hourly_pay.ui.pages.teacher_page import _decimal_text

MONTH_LABELS = {9: "сен", 10: "окт", 11: "ноя", 12: "дек", 1: "янв",
                2: "фев", 3: "мар", 4: "апр", 5: "май"}
HEADERS = ("Вид", "Дисциплина", "Группа", "По месяцам", "Всего", "Бюджет / коммерция")


class DistributionPage(QWidget):
    def __init__(self, service: DistributionExportService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._funding_controls: dict[int, QComboBox] = {}
        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("distributionTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("distributionYearSelector")
        self.year_box.currentIndexChanged.connect(self._load)
        self.output_edit = QLineEdit(self)
        self.output_edit.setObjectName("distributionOutputDirectory")
        self.output_edit.textChanged.connect(self._update_export_button)
        browse_button = QPushButton("Обзор…", self)
        browse_button.clicked.connect(self._choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit)
        output_row.addWidget(browse_button)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setObjectName("distributionTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.export_button = QPushButton("Создать распределение XLSX", self)
        self.export_button.setObjectName("exportDistributionButton")
        self.export_button.clicked.connect(self._export)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("distributionStatus")
        self.status_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Преподаватель", self.teacher_box)
        form.addRow("Учебный год", self.year_box)
        form.addRow("Папка для документа", output_row)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        explanation = QLabel(
            "Документ создаётся из сохранённого помесячного плана за весь учебный год. "
            "Для каждой строки явно выберите, в какую колонку шаблона записать часы.", self
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.export_button)
        layout.addWidget(self.status_label)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        previous = self.teacher_box.currentData()
        self.teacher_box.blockSignals(True)
        self.teacher_box.clear()
        for teacher in self._service.list_teachers():
            self.teacher_box.addItem(teacher.full_name, teacher.id)
        index = self.teacher_box.findData(previous)
        if index >= 0:
            self.teacher_box.setCurrentIndex(index)
        self.teacher_box.blockSignals(False)
        self._select_teacher()

    @Slot()
    def _select_teacher(self) -> None:
        teacher_id = self.teacher_box.currentData()
        previous = self.year_box.currentData()
        self.year_box.blockSignals(True)
        self.year_box.clear()
        if teacher_id is not None:
            for year in self._service.list_years(teacher_id):
                self.year_box.addItem(year.name, year.id)
            index = self.year_box.findData(previous)
            if index >= 0:
                self.year_box.setCurrentIndex(index)
        self.year_box.blockSignals(False)
        self._load()

    @Slot()
    def _load(self) -> None:
        previous_funding = {
            selection_id: control.currentData()
            for selection_id, control in self._funding_controls.items()
        }
        self._funding_controls.clear()
        self.table.setRowCount(0)
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            self.status_label.setText("Выберите преподавателя и учебный год.")
            self._update_export_button()
            return
        try:
            snapshot = self._service.load(teacher_id, year_id)
        except DomainError as error:
            self.status_label.setText(str(error))
            self._update_export_button()
            return
        for entry in snapshot.rows:
            if entry.selection.id is None:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            allocation_text = ", ".join(
                f"{MONTH_LABELS[a.month]}: {_decimal_text(a.hours)}"
                for a in sorted(entry.allocations, key=lambda value: (value.year, value.month))
            )
            for column, value in enumerate((
                entry.item.work_type.value,
                entry.item.discipline or "—",
                entry.item.group_name or "—",
                allocation_text or "Не распределено",
                _decimal_text(entry.selection.selected_hours),
            )):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)
            choice = QComboBox(self.table)
            choice.addItem("Выберите", None)
            choice.addItem("Бюджет", "budget")
            choice.addItem("Коммерция", "commercial")
            previous_index = choice.findData(previous_funding.get(entry.selection.id))
            if previous_index >= 0:
                choice.setCurrentIndex(previous_index)
            choice.currentIndexChanged.connect(self._update_export_button)
            self.table.setCellWidget(row, 5, choice)
            self._funding_controls[entry.selection.id] = choice
        self.table.resizeColumnsToContents()
        self.status_label.setText(
            "Шифры специальности и дисциплины отсутствуют в импортированной нагрузке "
            "и останутся пустыми в XLSX."
            if snapshot.rows else "Сначала сохраните выбор нагрузки и помесячный план."
        )
        self._update_export_button()

    @Slot()
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для распределения")
        if path:
            self.output_edit.setText(path)

    @Slot()
    def _update_export_button(self) -> None:
        self.export_button.setEnabled(
            bool(self._funding_controls)
            and bool(self.output_edit.text().strip())
            and all(control.currentData() is not None
                    for control in self._funding_controls.values())
        )

    @Slot()
    def _export(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            return
        funding = {selection_id: control.currentData()
                   for selection_id, control in self._funding_controls.items()}
        try:
            result = self._service.export(
                teacher_id, year_id, Path(self.output_edit.text().strip()), funding
            )
        except (DomainError, OSError, ValueError) as error:
            self.status_label.setText(f"Не удалось создать распределение: {error}")
            return
        self.status_label.setText(
            f"Создан файл {result.output_path} · {result.row_count} строк · "
            f"{_decimal_text(result.hours_sum)} ч."
        )
