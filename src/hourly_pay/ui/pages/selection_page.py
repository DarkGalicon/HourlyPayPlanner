from decimal import Decimal

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.selection_service import SelectionService
from hourly_pay.domain.enums import StudyForm, WorkType
from hourly_pay.domain.errors import DomainError
from hourly_pay.domain.models import WorkloadItem
from hourly_pay.domain.rules import MAX_HOURLY_HOURS
from hourly_pay.ui.pages.teacher_page import _decimal_text

HEADERS = (
    "Выбрать",
    "Семестр",
    "Форма",
    "Дисциплина",
    "Группа",
    "Поток",
    "Вид",
    "Доступно",
    "В почасовку",
    "Вечерний приоритет",
)
WORK_TYPE_LABELS = {
    WorkType.LECTURE: "Лек",
    WorkType.PRACTICE: "Пр",
    WorkType.LAB: "Лаб",
}
FORM_LABELS = {
    StudyForm.FULL_TIME: "Очная",
    StudyForm.CORRESPONDENCE: "Заочная",
}


class SelectionPage(QWidget):
    selections_saved = Signal()

    def __init__(self, service: SelectionService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._items: dict[int, WorkloadItem] = {}
        self._controls: dict[int, tuple[QCheckBox, QSpinBox, QCheckBox]] = {}
        self._limit = Decimal("0")
        self._excluded_saved_count = 0

        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("selectionTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("selectionYearSelector")
        self.year_box.currentIndexChanged.connect(self._load)

        self.semester_filter = QComboBox(self)
        self.semester_filter.addItem("Все", None)
        self.semester_filter.addItem("1 семестр", 1)
        self.semester_filter.addItem("2 семестр", 2)
        self.semester_filter.addItem("Не назначен", 0)
        self.form_filter = QComboBox(self)
        self.form_filter.addItem("Все", None)
        for form, label in FORM_LABELS.items():
            self.form_filter.addItem(label, form)
        self.type_filter = QComboBox(self)
        self.type_filter.addItem("Все", None)
        for work_type, label in WORK_TYPE_LABELS.items():
            self.type_filter.addItem(label, work_type)
        self.discipline_filter = QLineEdit(self)
        self.discipline_filter.setPlaceholderText("Часть названия")
        self.group_filter = QLineEdit(self)
        self.group_filter.setPlaceholderText("Часть названия")
        for control in (self.semester_filter, self.form_filter, self.type_filter):
            control.currentIndexChanged.connect(self._apply_filters)
        for control in (self.discipline_filter, self.group_filter):
            control.textChanged.connect(self._apply_filters)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setObjectName("hourlySelectionTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)

        self.summary_label = QLabel(self)
        self.summary_label.setObjectName("selectionSummary")
        self.allow_excess_check = QCheckBox(
            "Разрешить превышение расчётного лимита (не более 300 ч.)", self
        )
        self.allow_excess_check.setObjectName("allowHourlyLimitExcessCheck")
        self.allow_excess_check.toggled.connect(self._update_summary)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("selectionStatus")
        self.status_label.setWordWrap(True)
        self.save_button = QPushButton("Сохранить выбор", self)
        self.save_button.setObjectName("saveHourlySelectionButton")
        self.save_button.clicked.connect(self._save)

        filters = QGridLayout()
        for column, (label, control) in enumerate(
            (("Преподаватель", self.teacher_box), ("Учебный год", self.year_box))
        ):
            filters.addWidget(QLabel(label, self), 0, column)
            filters.addWidget(control, 1, column)
        for column, (label, control) in enumerate(
            (
                ("Семестр", self.semester_filter),
                ("Форма обучения", self.form_filter),
                ("Дисциплина", self.discipline_filter),
                ("Группа", self.group_filter),
                ("Вид занятия", self.type_filter),
            )
        ):
            filters.addWidget(QLabel(label, self), 2, column)
            filters.addWidget(control, 3, column)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(self.allow_excess_check)
        layout.addWidget(self.summary_label)
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
        self._select_teacher()

    @Slot()
    def _select_teacher(self) -> None:
        teacher_id = self.teacher_box.currentData()
        previous_id = self.year_box.currentData()
        self.year_box.blockSignals(True)
        self.year_box.clear()
        if teacher_id is not None:
            for year in self._service.list_years(teacher_id):
                self.year_box.addItem(year.name, year.id)
            index = self.year_box.findData(previous_id)
            if index >= 0:
                self.year_box.setCurrentIndex(index)
        self.year_box.blockSignals(False)
        self._load()

    @Slot()
    def _load(self) -> None:
        self._items.clear()
        self._controls.clear()
        self.table.setRowCount(0)
        self._limit = Decimal("0")
        self._excluded_saved_count = 0
        self.allow_excess_check.blockSignals(True)
        self.allow_excess_check.setChecked(False)
        self.allow_excess_check.setEnabled(False)
        self.allow_excess_check.blockSignals(False)
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            self.status_label.setText("Импортируйте XLSX и выберите преподавателя.")
            self._update_summary()
            return
        try:
            snapshot = self._service.load(teacher_id, year_id)
        except DomainError as error:
            self.status_label.setText(str(error))
            self._update_summary()
            return

        self._limit = snapshot.calculation.values.hourly_limit
        self.allow_excess_check.blockSignals(True)
        self.allow_excess_check.setChecked(snapshot.allow_limit_excess)
        self.allow_excess_check.setEnabled(True)
        self.allow_excess_check.blockSignals(False)
        self._excluded_saved_count = snapshot.excluded_saved_count
        for item in snapshot.calculation.eligible_items:
            if item.id is None:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._items[item.id] = item
            selected = snapshot.saved_hours.get(item.id, Decimal("0"))
            maximum = max(0, min((int(item.hours) // 2) * 2, 2_147_483_646))
            check = QCheckBox(self.table)
            check.setChecked(selected > 0)
            check.setEnabled(maximum >= 2)
            spin = QSpinBox(self.table)
            spin.setRange(0, maximum)
            spin.setSingleStep(2)
            spin.setValue(int(selected))
            spin.setEnabled(check.isChecked())
            check.toggled.connect(spin.setEnabled)
            check.toggled.connect(
                lambda checked, control=spin: control.setValue(2)
                if checked and control.value() == 0
                else None
            )
            check.toggled.connect(self._update_summary)
            spin.valueChanged.connect(self._update_summary)
            evening = QCheckBox(self.table)
            correspondence = item.study_form == StudyForm.CORRESPONDENCE
            evening.setChecked(correspondence or item.id in snapshot.evening_item_ids)
            evening.setEnabled(check.isChecked() and not correspondence)
            check.toggled.connect(
                lambda checked, control=evening, fixed=correspondence:
                control.setEnabled(checked and not fixed)
            )
            self._controls[item.id] = check, spin, evening
            self.table.setCellWidget(row, 0, check)
            self.table.setCellWidget(row, 8, spin)
            self.table.setCellWidget(row, 9, evening)
            for column, value in enumerate(
                (
                    str(item.semester) if item.semester is not None else "Не назначен",
                    FORM_LABELS[item.study_form],
                    item.discipline or "—",
                    item.group_name or "—",
                    item.stream or "—",
                    WORK_TYPE_LABELS[item.work_type],
                    _decimal_text(item.hours),
                ),
                start=1,
            ):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        self._apply_filters()
        self._update_summary()
        if self._excluded_saved_count:
            self.status_label.setText(
                f"Выбор из исключённых источников: {self._excluded_saved_count} строк. "
                "Сохранение удалит их, если для них нет помесячного распределения."
            )
        else:
            self.status_label.setText(
                "Выберите строки и часы вручную. Строки без семестра потребуется уточнить "
                "перед помесячным распределением. Для очно-заочных строк отметьте "
                "вечерний приоритет; для заочных он включён автоматически."
            )

    @Slot()
    def _apply_filters(self) -> None:
        semester = self.semester_filter.currentData()
        form = self.form_filter.currentData()
        work_type = self.type_filter.currentData()
        discipline = self.discipline_filter.text().strip().casefold()
        group = self.group_filter.text().strip().casefold()
        for row, item in enumerate(self._items.values()):
            visible = (
                (semester is None or (item.semester or 0) == semester)
                and (form is None or item.study_form == form)
                and (work_type is None or item.work_type == work_type)
                and discipline in (item.discipline or "").casefold()
                and group in (item.group_name or "").casefold()
            )
            self.table.setRowHidden(row, not visible)

    @Slot()
    def _update_summary(self) -> None:
        selected = sum(
            (
                Decimal(spin.value())
                for check, spin, _ in self._controls.values()
                if check.isChecked()
            ),
            Decimal("0"),
        )
        self.summary_label.setText(
            f"Лимит: {_decimal_text(self._limit)} ч.  ·  "
            f"Выбрано: {_decimal_text(selected)} ч.  ·  "
            f"Осталось: {_decimal_text(self._limit - selected)} ч."
        )
        self.save_button.setEnabled(
            self.teacher_box.currentData() is not None
            and self.year_box.currentData() is not None
            and (bool(self._items) or self._excluded_saved_count > 0)
            and selected <= MAX_HOURLY_HOURS
            and (selected <= self._limit or self.allow_excess_check.isChecked())
            and all(
                spin.value() % 2 == 0
                for check, spin, _ in self._controls.values()
                if check.isChecked()
            )
        )

    @Slot()
    def _save(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            return
        requested = {
            item_id: Decimal(spin.value())
            for item_id, (check, spin, _) in self._controls.items()
            if check.isChecked() and spin.value() > 0
        }
        evening_item_ids = frozenset(
            item_id for item_id, (check, spin, evening) in self._controls.items()
            if check.isChecked() and spin.value() > 0 and evening.isChecked()
        )
        try:
            plan = self._service.save(
                teacher_id, year_id, requested, evening_item_ids,
                allow_limit_excess=self.allow_excess_check.isChecked(),
            )
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._load()
        self.status_label.setText(f"Выбор сохранён: {_decimal_text(plan.selected_total)} ч.")
        self.selections_saved.emit()
