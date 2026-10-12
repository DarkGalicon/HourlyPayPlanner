from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.calculate_teacher import (
    CalculationWarning,
    TeacherCalculationService,
)
from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.errors import DomainError
from hourly_pay.domain.rules import MAX_HOURLY_HOURS, counts_toward_plan
from hourly_pay.ui.pages.teacher_page import _decimal_text

VALUE_LABELS = (
    ("effective_rate", "Эффективная ставка"),
    ("norm_hours", "Норма (ставка × 900)"),
    ("fact_hours", "Фактические часы выбранных источников"),
    ("idpo_hours", "ИДПО"),
    ("net_hours", "После вычета ИДПО"),
    ("excess_hours", "Превышение"),
    ("eligible_auditory_hours", "Доступные Лек/Пр/Лаб"),
    ("maximum", "Максимум на сотрудника"),
    ("hourly_limit", "К распределению"),
)
WARNING_HEADERS = ("Файл", "Лист", "Строка", "Предупреждение")
WORK_TYPE_DISPLAY = {WorkType.UNCLASSIFIED: "Нерасшифрованные часы"}


class CalculationPage(QWidget):
    def __init__(
        self, service: TeacherCalculationService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._warnings: tuple[CalculationWarning, ...] = ()
        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("calculationTeacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("calculationYearSelector")
        self.year_box.currentIndexChanged.connect(self.recalculate)
        self.refresh_button = QPushButton("Обновить расчёт", self)
        self.refresh_button.setObjectName("refreshCalculationButton")
        self.refresh_button.clicked.connect(self.recalculate)

        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("Преподаватель", self))
        selectors.addWidget(self.teacher_box)
        selectors.addWidget(QLabel("Учебный год", self))
        selectors.addWidget(self.year_box)
        selectors.addWidget(self.refresh_button)

        self.value_labels: dict[str, QLabel] = {}
        values = QFormLayout()
        for field_name, title in VALUE_LABELS:
            label = QLabel("—", self)
            label.setObjectName(f"calculation_{field_name}")
            self.value_labels[field_name] = label
            values.addRow(title, label)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("calculationStatusLabel")
        self.status_label.setWordWrap(True)
        self.warning_table = QTableWidget(0, len(WARNING_HEADERS), self)
        self.warning_table.setObjectName("calculationWarningsTable")
        self.warning_table.setHorizontalHeaderLabels(WARNING_HEADERS)
        self.warning_table.horizontalHeader().setStretchLastSection(True)
        self.warning_table.setAlternatingRowColors(True)
        self.warning_table.cellClicked.connect(self._show_warning)
        self.warning_details = QPlainTextEdit(self)
        self.warning_details.setObjectName("calculationWarningDetails")
        self.warning_details.setReadOnly(True)
        self.warning_details.setMaximumHeight(105)
        self.warning_details.setPlaceholderText(
            "Выберите предупреждение, чтобы увидеть распознанные данные строки."
        )

        layout = QVBoxLayout(self)
        layout.addLayout(selectors)
        layout.addLayout(values)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Предупреждения включённых источников", self))
        layout.addWidget(self.warning_table)
        layout.addWidget(self.warning_details)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        previous_teacher_id = self.teacher_box.currentData()
        self.teacher_box.blockSignals(True)
        self.teacher_box.clear()
        for teacher in self._service.list_teachers():
            self.teacher_box.addItem(teacher.full_name, teacher.id)
        previous_index = self.teacher_box.findData(previous_teacher_id)
        if previous_index >= 0:
            self.teacher_box.setCurrentIndex(previous_index)
        self.teacher_box.blockSignals(False)
        self._select_teacher()

    @Slot()
    def _select_teacher(self) -> None:
        teacher_id = self.teacher_box.currentData()
        previous_year_id = self.year_box.currentData()
        self.year_box.blockSignals(True)
        self.year_box.clear()
        if teacher_id is not None:
            for year in self._service.list_years(teacher_id):
                self.year_box.addItem(year.name, year.id)
            previous_index = self.year_box.findData(previous_year_id)
            if previous_index >= 0:
                self.year_box.setCurrentIndex(previous_index)
        self.year_box.blockSignals(False)
        self.recalculate()

    @Slot()
    def recalculate(self) -> None:
        self._clear_results()
        teacher_id = self.teacher_box.currentData()
        year_id = self.year_box.currentData()
        if teacher_id is None or year_id is None:
            self.status_label.setText("Импортируйте XLSX и выберите преподавателя.")
            return
        try:
            result = self._service.calculate(teacher_id, year_id)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        values = result.values
        for name, _ in VALUE_LABELS:
            value = MAX_HOURLY_HOURS if name == "maximum" else getattr(values, name)
            self.value_labels[name].setText(_decimal_text(value))
        self.status_label.setText(
            f"Расчёт по распознанным часам. Включено источников: "
            f"{result.included_source_count}."
        )
        self._warnings = result.warnings
        self.warning_table.setRowCount(len(self._warnings))
        for row, warning in enumerate(self._warnings):
            for column, value in enumerate(
                (
                    warning.source_name,
                    warning.sheet_name or "—",
                    str(warning.row_number) if warning.row_number is not None else "—",
                    warning.message,
                )
            ):
                self.warning_table.setItem(row, column, QTableWidgetItem(value))
        self.warning_table.resizeColumnsToContents()

    @Slot(int, int)
    def _show_warning(self, row: int, _column: int) -> None:
        if not 0 <= row < len(self._warnings):
            self.warning_details.clear()
            return
        warning = self._warnings[row]
        location = f"{warning.source_name} — {warning.sheet_name or 'файл'}"
        if warning.row_number is not None:
            location += f", строка {warning.row_number}"
        items = (
            f"{item.group_name or 'Без группы'} · "
            f"{item.discipline or 'Без дисциплины'} · "
            f"{WORK_TYPE_DISPLAY.get(item.work_type, item.work_type.value)}: "
            f"{_decimal_text(item.hours)} ч"
            f"{' (вне итога строки)' if not counts_toward_plan(item) else ''}"
            for item in warning.row_items
        )
        details = "\n".join(items)
        self.warning_details.setPlainText(
            f"{location}\n{warning.message}" + (f"\n{details}" if details else "")
        )

    def _clear_results(self) -> None:
        for label in self.value_labels.values():
            label.setText("—")
        self._warnings = ()
        self.warning_table.setRowCount(0)
        self.warning_details.clear()
