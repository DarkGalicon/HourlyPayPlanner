from datetime import date

from PySide6.QtCore import QDate, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.availability_settings import AvailabilitySettingsService
from hourly_pay.domain.errors import DomainError, InvalidScheduleError

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт")
EXCEPTION_TYPES = (("Исключить дату", "excluded"), ("Слоты для даты", "per_date"))


class AvailabilityPage(QWidget):
    def __init__(self, service: AvailabilitySettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._slot_ids: tuple[int, ...] = ()
        self._week_checks: dict[tuple[int, int], QCheckBox] = {}
        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("availabilityTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._load)
        self.week_table = QTableWidget(0, len(WEEKDAYS), self)
        self.week_table.setObjectName("weeklyAvailabilityTable")
        self.week_table.setHorizontalHeaderLabels(WEEKDAYS)
        self.week_table.horizontalHeader().setStretchLastSection(True)

        self.exception_table = QTableWidget(0, 3, self)
        self.exception_table.setObjectName("availabilityExceptionsTable")
        self.exception_table.horizontalHeader().setStretchLastSection(True)
        self.add_exclusion_button = QPushButton("Исключить дату", self)
        self.add_exclusion_button.clicked.connect(
            lambda: self._add_exception("excluded", date.today(), frozenset())
        )
        self.add_date_slots_button = QPushButton("Слоты для даты", self)
        self.add_date_slots_button.clicked.connect(
            lambda: self._add_exception("per_date", date.today(), frozenset())
        )
        self.save_button = QPushButton("Сохранить доступность", self)
        self.save_button.setObjectName("saveAvailabilityButton")
        self.save_button.clicked.connect(self._save)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("availabilityStatus")
        self.status_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_exclusion_button)
        buttons.addWidget(self.add_date_slots_button)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Преподаватель", self))
        layout.addWidget(self.teacher_box)
        layout.addWidget(QLabel("Разрешённые слоты по будням", self))
        layout.addWidget(self.week_table)
        layout.addWidget(QLabel("Исключения для конкретных дат", self))
        layout.addLayout(buttons)
        layout.addWidget(self.exception_table)
        layout.addWidget(
            QLabel(
                "Выходные всегда исключены. Праздничные и глобальные календарные "
                "исключения будут настраиваться отдельно.",
                self,
            )
        )
        layout.addWidget(self.status_label)
        layout.addWidget(self.save_button)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        previous_id = self.teacher_box.currentData()
        self.teacher_box.blockSignals(True)
        self.teacher_box.clear()
        for teacher in self._service.list_teachers():
            self.teacher_box.addItem(teacher.full_name, teacher.id)
        index = self.teacher_box.findData(previous_id)
        if index >= 0:
            self.teacher_box.setCurrentIndex(index)
        self.teacher_box.blockSignals(False)
        self._load()

    @Slot()
    def _load(self) -> None:
        self._week_checks.clear()
        self.week_table.setRowCount(0)
        self.exception_table.setRowCount(0)
        teacher_id = self.teacher_box.currentData()
        enabled = teacher_id is not None
        self.save_button.setEnabled(enabled)
        self.add_exclusion_button.setEnabled(enabled)
        self.add_date_slots_button.setEnabled(enabled)
        if teacher_id is None:
            self.status_label.setText("Импортируйте XLSX и выберите преподавателя.")
            return
        snapshot = self._service.load(teacher_id)
        self._slot_ids = tuple(slot.id for slot in snapshot.time_slots)
        self.exception_table.setColumnCount(len(self._slot_ids) + 3)
        self.exception_table.setHorizontalHeaderLabels(
            ("Правило", "Дата", *[slot.display_text for slot in snapshot.time_slots], "Удалить")
        )
        self.week_table.setRowCount(len(snapshot.time_slots))
        slot_labels = [slot.display_text for slot in snapshot.time_slots]
        self.week_table.setVerticalHeaderLabels(slot_labels)
        self.week_table.verticalHeader().setFixedWidth(
            max(
                (
                    self.week_table.verticalHeader().fontMetrics().horizontalAdvance(label)
                    for label in slot_labels
                ),
                default=0,
            )
            + 32
        )
        for row, slot in enumerate(snapshot.time_slots):
            for weekday in range(5):
                check = QCheckBox(self.week_table)
                check.setChecked(
                    slot.id in snapshot.availability.weekday_allowed_slots.get(
                        weekday, frozenset()
                    )
                )
                self._week_checks[weekday, slot.id] = check
                self.week_table.setCellWidget(row, weekday, check)
        for target in sorted(snapshot.availability.excluded_dates):
            self._add_exception("excluded", target, frozenset())
        for target, slot_ids in sorted(snapshot.availability.per_date_allowed_slots.items()):
            self._add_exception("per_date", target, slot_ids)
        self.status_label.setText(
            "Отметьте разрешённые слоты. Пока ничего не выбрано, занятия не генерируются."
        )

    def _add_exception(
        self, rule_type: str, target: date, slot_ids: frozenset[int]
    ) -> None:
        row = self.exception_table.rowCount()
        self.exception_table.insertRow(row)
        kind = QComboBox(self.exception_table)
        for label, value in EXCEPTION_TYPES:
            kind.addItem(label, value)
        kind.setCurrentIndex(kind.findData(rule_type))
        target_edit = QDateEdit(self.exception_table)
        target_edit.setCalendarPopup(True)
        target_edit.setDisplayFormat("dd.MM.yyyy")
        target_edit.setDate(QDate(target.year, target.month, target.day))
        self.exception_table.setCellWidget(row, 0, kind)
        self.exception_table.setCellWidget(row, 1, target_edit)
        for column, slot_id in enumerate(self._slot_ids, start=2):
            check = QCheckBox(self.exception_table)
            check.setChecked(slot_id in slot_ids)
            check.setEnabled(rule_type == "per_date")
            kind.currentIndexChanged.connect(
                lambda _index, control=check, selector=kind: control.setEnabled(
                    selector.currentData() == "per_date"
                )
            )
            self.exception_table.setCellWidget(row, column, check)
        remove_button = QPushButton("×", self.exception_table)
        remove_button.clicked.connect(
            lambda _checked=False, button=remove_button: self._remove_exception(button)
        )
        self.exception_table.setCellWidget(row, len(self._slot_ids) + 2, remove_button)
        self.exception_table.resizeColumnsToContents()

    def _remove_exception(self, button: QPushButton) -> None:
        for row in range(self.exception_table.rowCount()):
            if self.exception_table.cellWidget(row, len(self._slot_ids) + 2) is button:
                self.exception_table.removeRow(row)
                return

    @Slot()
    def _save(self) -> None:
        teacher_id = self.teacher_box.currentData()
        if teacher_id is None:
            return
        weekdays = {
            weekday: frozenset(
                slot_id
                for slot_id in self._slot_ids
                if self._week_checks[weekday, slot_id].isChecked()
            )
            for weekday in range(5)
        }
        excluded: set[date] = set()
        per_date: dict[date, frozenset[int]] = {}
        seen: set[date] = set()
        try:
            for row in range(self.exception_table.rowCount()):
                kind = self.exception_table.cellWidget(row, 0).currentData()
                target = self.exception_table.cellWidget(row, 1).date().toPython()
                if target in seen:
                    raise InvalidScheduleError(
                        f"Дата {target:%d.%m.%Y} указана в исключениях несколько раз."
                    )
                seen.add(target)
                if kind == "excluded":
                    excluded.add(target)
                else:
                    per_date[target] = frozenset(
                        slot_id
                        for column, slot_id in enumerate(self._slot_ids, start=2)
                        if self.exception_table.cellWidget(row, column).isChecked()
                    )
            self._service.save(
                teacher_id,
                weekdays=weekdays,
                excluded_dates=excluded,
                per_date=per_date,
            )
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._load()
        self.status_label.setText("Доступность сохранена.")
