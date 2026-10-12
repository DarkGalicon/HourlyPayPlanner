import calendar
from datetime import date

from PySide6.QtCore import QDate, Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.schedule_month import ScheduleMonthService
from hourly_pay.domain.errors import DomainError
from hourly_pay.ui.pages.teacher_page import _decimal_text

MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
HEADERS = ("Дата", "Время", "Группа", "Дисциплина", "Вид", "Часы", "Ручная правка")


class SchedulePage(QWidget):
    def __init__(self, service: ScheduleMonthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("scheduleTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("scheduleYearSelector")
        self.year_box.currentIndexChanged.connect(self._select_year)
        self.month_box = QComboBox(self)
        self.month_box.setObjectName("scheduleMonthSelector")
        self.month_box.currentIndexChanged.connect(self._show_lessons)

        self.generate_button = QPushButton("Сгенерировать", self)
        self.generate_button.setObjectName("generateScheduleButton")
        self.generate_button.clicked.connect(self._generate)
        self.regenerate_button = QPushButton("Перегенерировать", self)
        self.regenerate_button.setObjectName("regenerateScheduleButton")
        self.regenerate_button.clicked.connect(self._regenerate)
        self.validate_button = QPushButton("Проверить конфликты", self)
        self.validate_button.setObjectName("validateScheduleButton")
        self.validate_button.clicked.connect(self._validate)
        self.clear_button = QPushButton("Очистить месяц", self)
        self.clear_button.setObjectName("clearScheduleMonthButton")
        self.clear_button.clicked.connect(self._clear_month)

        self.edit_date = QDateEdit(self)
        self.edit_date.setObjectName("editLessonDate")
        self.edit_date.setCalendarPopup(True)
        self.edit_date.setDisplayFormat("dd.MM.yyyy")
        self.edit_slot = QComboBox(self)
        self.edit_slot.setObjectName("editLessonSlot")
        for slot in self._service.list_time_slots():
            self.edit_slot.addItem(slot.display_text, slot.id)
        self.edit_button = QPushButton("Перенести занятие", self)
        self.edit_button.setObjectName("moveLessonButton")
        self.edit_button.clicked.connect(self._move_lesson)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setObjectName("scheduleLessonsTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._select_lesson)
        self._rows = ()
        self.status_label = QLabel(self)
        self.status_label.setObjectName("scheduleStatus")
        self.status_label.setWordWrap(True)

        selectors = QHBoxLayout()
        for title, control in (
            ("Преподаватель", self.teacher_box),
            ("Учебный год", self.year_box),
            ("Месяц", self.month_box),
        ):
            selectors.addWidget(QLabel(title, self))
            selectors.addWidget(control)
        actions = QHBoxLayout()
        actions.addWidget(self.generate_button)
        actions.addWidget(self.regenerate_button)
        actions.addWidget(self.validate_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        edit_row = QHBoxLayout()
        edit_row.addWidget(QLabel("Выбранное занятие: дата", self))
        edit_row.addWidget(self.edit_date)
        edit_row.addWidget(QLabel("Время", self))
        edit_row.addWidget(self.edit_slot)
        edit_row.addWidget(self.edit_button)
        edit_row.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(selectors)
        layout.addLayout(actions)
        layout.addLayout(edit_row)
        layout.addWidget(self.table)
        layout.addWidget(self.status_label)
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
        self._select_year()

    @Slot()
    def _select_year(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        previous_month = self.month_box.currentData()
        load_error: str | None = None
        self.month_box.blockSignals(True)
        self.month_box.clear()
        if teacher_id is not None and year_id is not None:
            try:
                months = self._service.available_months(teacher_id, year_id)
            except DomainError as error:
                load_error = str(error)
            else:
                for entry in months:
                    self.month_box.addItem(
                        f"{MONTH_NAMES.get(entry.month, str(entry.month))} {entry.year} "
                        f"· {entry.lesson_count} занятий",
                        (entry.year, entry.month),
                    )
                index = self.month_box.findData(previous_month)
                if index >= 0:
                    self.month_box.setCurrentIndex(index)
        self.month_box.blockSignals(False)
        if load_error is not None:
            self._rows = ()
            self.table.setRowCount(0)
            self._set_buttons(False)
            self.status_label.setText(load_error)
            return
        self._show_lessons()

    @Slot()
    def _show_lessons(self) -> None:
        previous_id = None
        selected_row = self.table.currentRow()
        if 0 <= selected_row < len(self._rows):
            previous_id = self._rows[selected_row].lesson.id
        self._rows = ()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        teacher_id = self.teacher_box.currentData()
        period = self.month_box.currentData()
        if teacher_id is None or period is None:
            self._set_buttons(False)
            self.status_label.setText(
                "Сначала сохраните помесячный план и выберите месяц с часами."
            )
            return
        year, month = period
        try:
            lessons = self._service.list_lessons(teacher_id, year, month)
        except DomainError as error:
            self._set_buttons(False)
            self.status_label.setText(str(error))
            return
        self._rows = lessons
        self.table.blockSignals(True)
        self.table.setRowCount(len(lessons))
        for row, entry in enumerate(lessons):
            lesson = entry.lesson
            values = (
                lesson.lesson_date.strftime("%d.%m.%Y"),
                entry.time_slot.display_text,
                lesson.group_name,
                lesson.discipline,
                lesson.work_type.value,
                _decimal_text(lesson.hours),
                "Да" if lesson.manual_override else "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, cell)
        self.table.blockSignals(False)
        index = next(
            (row for row, entry in enumerate(lessons) if entry.lesson.id == previous_id),
            -1,
        )
        if index >= 0:
            self.table.selectRow(index)
        self.table.resizeColumnsToContents()
        self._set_buttons(bool(lessons))
        self._select_lesson()
        self.status_label.setText(
            f"Сохранённых занятий: {len(lessons)}."
            if lessons
            else "Расписание ещё не создано."
        )

    def _set_buttons(self, has_lessons: bool) -> None:
        has_month = self.month_box.currentData() is not None
        self.generate_button.setEnabled(has_month and not has_lessons)
        self.regenerate_button.setEnabled(has_month and has_lessons)
        self.validate_button.setEnabled(has_month and has_lessons)
        self.clear_button.setEnabled(has_month and has_lessons)
        self._set_edit_enabled(False)

    def _set_edit_enabled(self, enabled: bool) -> None:
        self.edit_date.setEnabled(enabled)
        self.edit_slot.setEnabled(enabled)
        self.edit_button.setEnabled(enabled)

    @Slot()
    def _select_lesson(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._rows):
            self._set_edit_enabled(False)
            return
        lesson = self._rows[row].lesson
        year, month = self.month_box.currentData()
        self.edit_date.setDateRange(
            QDate(year, month, 1), QDate(year, month, calendar.monthrange(year, month)[1])
        )
        self.edit_date.setDate(QDate(
            lesson.lesson_date.year, lesson.lesson_date.month, lesson.lesson_date.day
        ))
        self.edit_slot.setCurrentIndex(self.edit_slot.findData(lesson.time_slot_id))
        self._set_edit_enabled(True)

    @Slot()
    def _move_lesson(self) -> None:
        row = self.table.currentRow()
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        period = self.month_box.currentData()
        if not 0 <= row < len(self._rows) or None in (teacher_id, year_id, period):
            return
        lesson_id = self._rows[row].lesson.id
        assert lesson_id is not None
        year, month = period
        selected = self.edit_date.date()
        target_date = date(selected.year(), selected.month(), selected.day())
        try:
            changed = self._service.move_lesson(
                teacher_id, year_id, year, month, lesson_id,
                target_date, self.edit_slot.currentData(),
            )
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._show_lessons()
        self.status_label.setText(
            "Занятие перенесено; ручная правка сохранена."
            if changed else "Дата и время занятия не изменились."
        )

    @Slot()
    def _clear_month(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        period = self.month_box.currentData()
        if None in (teacher_id, year_id, period):
            return
        year, month = period
        question = (
            f"Удалить все занятия за {MONTH_NAMES.get(month, str(month)).lower()} {year} года? "
            "Помесячный план останется без изменений; расписание можно создать заново."
        )
        if QMessageBox.question(self, "Очистить расписание месяца", question) != (
            QMessageBox.StandardButton.Yes
        ):
            return
        try:
            deleted = self._service.clear_month(teacher_id, year_id, year, month)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._show_lessons()
        self.status_label.setText(f"Расписание месяца очищено: удалено занятий {deleted}.")

    @Slot()
    def _generate(self) -> None:
        self._run_generation(replace_existing=False)

    @Slot()
    def _regenerate(self) -> None:
        teacher_id = self.teacher_box.currentData()
        period = self.month_box.currentData()
        if teacher_id is None or period is None:
            return
        year, month = period
        try:
            has_manual = self._service.has_manual_changes(teacher_id, year, month)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        warning = (
            "В расписании есть ручные изменения. Перегенерация заменит их. Продолжить?"
            if has_manual
            else "Перегенерация заменит текущее расписание месяца. Продолжить?"
        )
        if QMessageBox.question(self, "Перегенерировать расписание", warning) != (
            QMessageBox.StandardButton.Yes
        ):
            return
        self._run_generation(replace_existing=True, allow_replace_manual=has_manual)

    def _run_generation(
        self, *, replace_existing: bool, allow_replace_manual: bool = False
    ) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        period = self.month_box.currentData()
        if teacher_id is None or year_id is None or period is None:
            return
        year, month = period
        try:
            result = self._service.generate(
                teacher_id,
                year_id,
                year,
                month,
                replace_existing=replace_existing,
                allow_replace_manual=allow_replace_manual,
            )
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self._show_lessons()
        self.status_label.setText(f"Сохранено занятий: {len(result.lessons)}.")

    @Slot()
    def _validate(self) -> None:
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        period = self.month_box.currentData()
        if teacher_id is None or year_id is None or period is None:
            return
        year, month = period
        try:
            self._service.validate_existing(teacher_id, year_id, year, month)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self.status_label.setText("Конфликтов не найдено.")
