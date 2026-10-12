from datetime import date

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.calendar_settings import CalendarSettingsService
from hourly_pay.domain.errors import DomainError
from hourly_pay.domain.models import CalendarOverride


class CalendarPage(QWidget):
    def __init__(self, service: CalendarSettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self.year_box = QSpinBox(self)
        self.year_box.setObjectName("calendarPreviewYear")
        self.year_box.setRange(1900, 2200)
        self.year_box.setValue(date.today().year)
        self.year_box.valueChanged.connect(self._refresh_holidays)
        self.holiday_table = QTableWidget(0, 2, self)
        self.holiday_table.setObjectName("baseHolidayTable")
        self.holiday_table.setHorizontalHeaderLabels(("Дата", "Статус для занятий"))
        self.holiday_table.horizontalHeader().setStretchLastSection(True)
        self.holiday_table.setMaximumHeight(240)
        self.override_table = QTableWidget(0, 3, self)
        self.override_table.setObjectName("calendarOverridesTable")
        self.override_table.setHorizontalHeaderLabels(("Дата", "Явное правило", "Удалить"))
        self.override_table.horizontalHeader().setStretchLastSection(True)

        self.add_nonworking_button = QPushButton("Добавить нерабочую дату", self)
        self.add_nonworking_button.clicked.connect(
            lambda: self._add_override(date(self.year_box.value(), 1, 1), False)
        )
        self.add_working_button = QPushButton("Разрешить рабочую дату", self)
        self.add_working_button.clicked.connect(
            lambda: self._add_override(date(self.year_box.value(), 1, 1), True)
        )
        self.save_button = QPushButton("Сохранить календарь", self)
        self.save_button.setObjectName("saveCalendarButton")
        self.save_button.clicked.connect(self._save)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("calendarStatus")
        self.status_label.setWordWrap(True)

        year_row = QHBoxLayout()
        year_row.addWidget(QLabel("Базовые праздники РФ за год", self))
        year_row.addWidget(self.year_box)
        year_row.addStretch()
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_nonworking_button)
        add_row.addWidget(self.add_working_button)
        add_row.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(year_row)
        layout.addWidget(self.holiday_table)
        layout.addWidget(
            QLabel(
                "Базовый календарь — подсказка. Явные даты ниже действуют для всех "
                "преподавателей; выходные всегда недоступны.",
                self,
            )
        )
        layout.addLayout(add_row)
        layout.addWidget(self.override_table)
        layout.addWidget(self.status_label)
        layout.addWidget(self.save_button)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        self.override_table.setRowCount(0)
        for entry in self._service.list_overrides():
            self._add_override(entry.target_date, entry.is_working)
        self._refresh_holidays()
        self.status_label.setText("Изменения календаря сохраняются только после подтверждения.")

    @Slot()
    def _refresh_holidays(self) -> None:
        year = self.year_box.value()
        policy = self._service.policy_for_years([year])
        holidays = self._service.base_holidays(year)
        self.holiday_table.setRowCount(len(holidays))
        for row, target in enumerate(holidays):
            status = "Рабочий по исключению" if policy.is_working_date(target) else "Нерабочий"
            for column, value in enumerate((target.strftime("%d.%m.%Y"), status)):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.holiday_table.setItem(row, column, cell)
        self.holiday_table.resizeColumnsToContents()

    def _add_override(self, target: date, is_working: bool) -> None:
        row = self.override_table.rowCount()
        self.override_table.insertRow(row)
        date_edit = QDateEdit(self.override_table)
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd.MM.yyyy")
        date_edit.setDate(QDate(target.year, target.month, target.day))
        status = QComboBox(self.override_table)
        status.addItem("Нерабочая", False)
        status.addItem("Рабочая", True)
        status.setCurrentIndex(status.findData(is_working))
        remove = QPushButton("×", self.override_table)
        remove.clicked.connect(
            lambda _checked=False, button=remove: self._remove_override(button)
        )
        self.override_table.setCellWidget(row, 0, date_edit)
        self.override_table.setCellWidget(row, 1, status)
        self.override_table.setCellWidget(row, 2, remove)
        self.override_table.resizeColumnsToContents()

    def _remove_override(self, button: QPushButton) -> None:
        for row in range(self.override_table.rowCount()):
            if self.override_table.cellWidget(row, 2) is button:
                self.override_table.removeRow(row)
                return

    @Slot()
    def _save(self) -> None:
        entries = tuple(
            CalendarOverride(
                target_date=self.override_table.cellWidget(row, 0).date().toPython(),
                is_working=self.override_table.cellWidget(row, 1).currentData(),
            )
            for row in range(self.override_table.rowCount())
        )
        try:
            self._service.save(entries)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self.refresh()
        self.status_label.setText("Календарь сохранён.")
