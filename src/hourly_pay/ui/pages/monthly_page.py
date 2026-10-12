from decimal import Decimal

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.monthly_planning import MonthlyPlanningService, MonthlyRowDraft
from hourly_pay.domain.errors import DomainError
from hourly_pay.ui.pages.teacher_page import _decimal_text

MONTHS = (9, 10, 11, 12, 1, 2, 3, 4, 5)
MONTH_LABELS = ("Сен", "Окт", "Ноя", "Дек", "Янв", "Фев", "Мар", "Апр", "Май")
HEADERS = (
    "Дисциплина",
    "Группа",
    "Вид",
    "Семестр",
    "Январь",
    "Выбрано",
    *MONTH_LABELS,
    "Остаток",
)


class MonthlyPage(QWidget):
    plan_saved = Signal()

    def __init__(self, service: MonthlyPlanningService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._controls: dict[
            int, tuple[QComboBox, QCheckBox, dict[int, QSpinBox], QLabel, int]
        ] = {}

        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("monthlyTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("monthlyYearSelector")
        self.year_box.currentIndexChanged.connect(self._load)
        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("Преподаватель", self))
        selectors.addWidget(self.teacher_box)
        selectors.addWidget(QLabel("Учебный год", self))
        selectors.addWidget(self.year_box)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setObjectName("monthlyAllocationTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("monthlyStatus")
        self.status_label.setWordWrap(True)
        self.save_button = QPushButton("Сохранить помесячный план", self)
        self.save_button.setObjectName("saveMonthlyPlanButton")
        self.save_button.clicked.connect(self._save)
        self.clear_button = QPushButton("Очистить месяцы учебного года…", self)
        self.clear_button.setObjectName("clearMonthlyPlanButton")
        self.clear_button.clicked.connect(self._clear)

        layout = QVBoxLayout(self)
        layout.addLayout(selectors)
        layout.addWidget(self.table)
        layout.addWidget(self.status_label)
        layout.addWidget(self.save_button)
        layout.addWidget(self.clear_button)
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
        self._controls.clear()
        self.table.setRowCount(0)
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            self.status_label.setText("Выберите преподавателя и учебный год.")
            self.save_button.setEnabled(False)
            self.clear_button.setEnabled(False)
            return
        try:
            snapshot = self._service.load(teacher_id, year_id)
        except DomainError as error:
            self.status_label.setText(str(error))
            self.save_button.setEnabled(False)
            self.clear_button.setEnabled(False)
            return

        self.clear_button.setEnabled(snapshot.stored_allocation_count > 0)

        for entry in snapshot.rows:
            selection_id = entry.selection.id
            if selection_id is None:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = entry.item
            selected = int(entry.selection.selected_hours)
            for column, value in enumerate(
                (item.discipline or "—", item.group_name or "—", item.work_type.value)
            ):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)
            semester = QComboBox(self.table)
            if item.semester is None:
                semester.addItem("Укажите", None)
            semester.addItem("1 семестр", 1)
            semester.addItem("2 семестр", 2)
            if item.semester is not None:
                semester.setCurrentIndex(semester.findData(item.semester))
                semester.setEnabled(False)
            elif entry.allocations:
                saved_semester = 1 if any(a.month >= 9 for a in entry.allocations) else 2
                semester.setCurrentIndex(semester.findData(saved_semester))
            january = QCheckBox(self.table)
            january.setChecked(any(a.month == 1 and a.hours > 0 for a in entry.allocations))
            self.table.setCellWidget(row, 3, semester)
            self.table.setCellWidget(row, 4, january)
            self.table.setItem(
                row, 5, QTableWidgetItem(_decimal_text(entry.selection.selected_hours))
            )
            saved_hours = {allocation.month: allocation.hours for allocation in entry.allocations}
            spins: dict[int, QSpinBox] = {}
            for column, month in enumerate(MONTHS, start=6):
                spin = QSpinBox(self.table)
                spin.setRange(0, selected)
                spin.setSingleStep(2)
                spin.setValue(int(saved_hours.get(month, Decimal("0"))))
                spin.valueChanged.connect(self._update)
                spins[month] = spin
                self.table.setCellWidget(row, column, spin)
            remainder = QLabel(self.table)
            self.table.setCellWidget(row, 15, remainder)
            self._controls[selection_id] = semester, january, spins, remainder, selected
            semester.currentIndexChanged.connect(self._update)
            january.toggled.connect(self._update)
        self.table.resizeColumnsToContents()
        self._update()
        if snapshot.rows:
            self.status_label.setText(
                "Заполните каждый месяц часами, кратными двум. Для строк без семестра "
                "укажите его явно; январь разрешается отдельно."
            )
        else:
            self.status_label.setText("Сначала сохраните выбор нагрузки на соседней вкладке.")

    @Slot()
    def _update(self) -> None:
        valid = bool(self._controls)
        for semester, january, spins, remainder, selected in self._controls.values():
            chosen = semester.currentData()
            january.setEnabled(chosen == 2)
            allowed = (
                {9, 10, 11, 12}
                if chosen == 1
                else ({1, 2, 3, 4, 5} if january.isChecked() else {2, 3, 4, 5})
                if chosen == 2
                else set()
            )
            allocated = sum(spin.value() for spin in spins.values())
            remainder.setText(str(selected - allocated))
            for month, spin in spins.items():
                spin.setEnabled(month in allowed or spin.value() > 0)
                if month not in allowed and spin.value() != 0:
                    valid = False
                if spin.value() % 2:
                    valid = False
            if chosen is None or allocated != selected:
                valid = False
        self.save_button.setEnabled(valid)

    @Slot()
    def _save(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            return
        drafts = {
            selection_id: MonthlyRowDraft(
                hours_by_month={
                    month: Decimal(spin.value())
                    for month, spin in spins.items()
                    if spin.value() > 0
                },
                include_january=january.isChecked(),
                semester_override=semester.currentData(),
            )
            for selection_id, (semester, january, spins, _, _) in self._controls.items()
        }
        try:
            self._service.save(teacher_id, year_id, drafts)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._load()
        self.status_label.setText("Помесячный план сохранён.")
        self.plan_saved.emit()

    @Slot()
    def _clear(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Очистить помесячный план",
            "Удалить все помесячные часы выбранного преподавателя за учебный год?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.clear(teacher_id, year_id)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._load()
        self.status_label.setText("Помесячный план очищен.")
        self.plan_saved.emit()
