from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.teacher_settings import (
    TeacherPersonalData,
    TeacherProfile,
    TeacherSettingsService,
)
from hourly_pay.domain.errors import DomainError, InvalidTeacherSettingsError

SOURCE_HEADERS = (
    "Учитывать в фактической нагрузке",
    "Тип занятости",
    "Ставка из файла",
    "План часов",
    "Имя файла",
)
INCLUSION_CHOICES = (
    ("Не решено", None),
    ("Учитывать", True),
    ("Не учитывать", False),
)
PERSONAL_FIELDS = (
    ("full_name", "ФИО"),
    ("department", "Кафедра"),
    ("degree", "Учёная степень"),
    ("title", "Учёное звание"),
    ("position", "Должность"),
    ("birth_date", "Дата рождения (ДД.ММ.ГГГГ)"),
    ("address", "Адрес"),
    ("passport_series", "Серия паспорта"),
    ("passport_number", "Номер паспорта"),
    ("passport_issued_by", "Кем выдан паспорт"),
    ("passport_issue_date", "Дата выдачи (ДД.ММ.ГГГГ)"),
    ("snils", "СНИЛС"),
    ("inn", "ИНН"),
)


class TeacherPage(QWidget):
    settings_saved = Signal()

    def __init__(self, service: TeacherSettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._profile: TeacherProfile | None = None
        self._source_choices: dict[int, QComboBox] = {}
        self._visible_source_ids: list[int] = []

        self.teacher_box = QComboBox(self)
        self.teacher_box.setObjectName("teacherSelector")
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("academicYearSelector")
        self.year_box.currentIndexChanged.connect(self._show_sources)

        self.rate_input = QLineEdit(self)
        self.rate_input.setObjectName("effectiveRateInput")
        self.rate_input.setPlaceholderText("Например, 0,5")
        self.confirm_rate_button = QPushButton("Подтвердить ставку", self)
        self.confirm_rate_button.setObjectName("confirmEffectiveRateButton")
        self.confirm_rate_button.clicked.connect(self._confirm_rate)

        self.personal_inputs = {
            name: QLineEdit(self) for name, _ in PERSONAL_FIELDS
        }
        for name, edit in self.personal_inputs.items():
            edit.setObjectName(f"teacher_{name}")
        self.save_personal_button = QPushButton("Сохранить данные для заявления", self)
        self.save_personal_button.setObjectName("saveTeacherPersonalDataButton")
        self.save_personal_button.clicked.connect(self._save_personal_data)
        personal_form = QFormLayout()
        for name, label in PERSONAL_FIELDS:
            personal_form.addRow(label, self.personal_inputs[name])

        self.sources_table = QTableWidget(0, len(SOURCE_HEADERS), self)
        self.sources_table.setObjectName("teacherSourcesTable")
        self.sources_table.setHorizontalHeaderLabels(SOURCE_HEADERS)
        self.sources_table.setAlternatingRowColors(True)
        self.sources_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sources_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sources_table.horizontalHeader().setStretchLastSection(True)
        self.sources_table.itemSelectionChanged.connect(self._update_delete_button)
        self.save_sources_button = QPushButton("Сохранить выбор источников", self)
        self.save_sources_button.setObjectName("saveSourceInclusionsButton")
        self.save_sources_button.clicked.connect(self._save_sources)
        self.delete_source_button = QPushButton("Удалить выбранный источник", self)
        self.delete_source_button.setObjectName("deleteSourceButton")
        self.delete_source_button.clicked.connect(self._delete_source)
        self.delete_source_button.setEnabled(False)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("teacherStatusLabel")
        self.status_label.setWordWrap(True)

        selectors = QFormLayout()
        selectors.addRow("Преподаватель", self.teacher_box)
        selectors.addRow("Учебный год", self.year_box)
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.rate_input)
        rate_row.addWidget(self.confirm_rate_button)
        selectors.addRow("Эффективная ставка для расчета", rate_row)

        content = QWidget(self)
        content.setObjectName("teacherContent")
        content_layout = QVBoxLayout(content)
        content_layout.addLayout(selectors)
        content_layout.addWidget(QLabel("Данные преподавателя для шапки заявления", self))
        content_layout.addLayout(personal_form)
        content_layout.addWidget(self.save_personal_button)
        content_layout.addWidget(
            QLabel("Ставки из импортированных файлов не суммируются автоматически.", self)
        )
        content_layout.addWidget(self.sources_table)
        source_actions = QHBoxLayout()
        source_actions.addWidget(self.save_sources_button)
        source_actions.addWidget(self.delete_source_button)
        content_layout.addLayout(source_actions)
        content_layout.addWidget(self.status_label)
        content_layout.addStretch()
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("teacherScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        previous_teacher_id = self.teacher_box.currentData()
        teachers = self._service.list_teachers()
        self.teacher_box.blockSignals(True)
        self.teacher_box.clear()
        for teacher in teachers:
            self.teacher_box.addItem(teacher.full_name, teacher.id)
        previous_index = self.teacher_box.findData(previous_teacher_id)
        if previous_index >= 0:
            self.teacher_box.setCurrentIndex(previous_index)
        self.teacher_box.blockSignals(False)
        self._select_teacher()

    @Slot()
    def _select_teacher(self) -> None:
        teacher_id = self.teacher_box.currentData()
        if teacher_id is None:
            self._profile = None
            self._visible_source_ids.clear()
            self.rate_input.clear()
            for edit in self.personal_inputs.values():
                edit.clear()
            self.year_box.clear()
            self.sources_table.setRowCount(0)
            self._resize_sources_table()
            self.confirm_rate_button.setEnabled(False)
            self.save_personal_button.setEnabled(False)
            self.save_sources_button.setEnabled(False)
            self.delete_source_button.setEnabled(False)
            self.status_label.setText("Импортируйте XLSX, чтобы открыть карточку преподавателя.")
            return

        previous_year_id = self.year_box.currentData()
        self._profile = self._service.get_profile(teacher_id)
        rate = self._profile.teacher.effective_rate
        self.rate_input.setText(_decimal_text(rate) if rate is not None else "")
        for name, edit in self.personal_inputs.items():
            value = getattr(self._profile.teacher, name)
            edit.setText(value.strftime("%d.%m.%Y") if isinstance(value, date) else value or "")
        self.confirm_rate_button.setEnabled(True)
        self.save_personal_button.setEnabled(True)
        self.year_box.blockSignals(True)
        self.year_box.clear()
        years = {
            source.academic_year.id: source.academic_year.name
            for source in self._profile.sources
        }
        for year_id, name in sorted(years.items(), key=lambda entry: entry[1]):
            self.year_box.addItem(name, year_id)
        previous_index = self.year_box.findData(previous_year_id)
        if previous_index >= 0:
            self.year_box.setCurrentIndex(previous_index)
        self.year_box.blockSignals(False)
        self._show_sources()
        self.status_label.setText(
            "Подтвердите эффективную ставку и выберите источники фактической нагрузки."
        )

    @Slot()
    def _show_sources(self) -> None:
        self._source_choices.clear()
        self._visible_source_ids.clear()
        self.sources_table.setRowCount(0)
        if self._profile is None:
            return
        year_id = self.year_box.currentData()
        sources = [
            entry.source
            for entry in self._profile.sources
            if entry.academic_year.id == year_id
        ]
        self.sources_table.setRowCount(len(sources))
        for row, source in enumerate(sources):
            choice = QComboBox(self.sources_table)
            for label, value in INCLUSION_CHOICES:
                choice.addItem(label, value)
            choice.setCurrentIndex(choice.findData(source.include_in_fact))
            self.sources_table.setCellWidget(row, 0, choice)
            for column, value in enumerate(
                (
                    source.employment_type,
                    _decimal_text(source.reported_rate),
                    _decimal_text(source.reported_total_hours),
                    source.original_filename,
                ),
                start=1,
            ):
                self.sources_table.setItem(row, column, QTableWidgetItem(value))
            if source.id is not None:
                self._source_choices[source.id] = choice
                self._visible_source_ids.append(source.id)
        self.save_sources_button.setEnabled(bool(self._source_choices))
        self._update_delete_button()
        self.sources_table.resizeColumnsToContents()
        self._resize_sources_table()

    def _resize_sources_table(self) -> None:
        header_height = self.sources_table.horizontalHeader().height()
        rows_height = sum(
            self.sources_table.rowHeight(row)
            for row in range(self.sources_table.rowCount())
        )
        self.sources_table.setFixedHeight(
            max(170, header_height + rows_height + 2 * self.sources_table.frameWidth() + 20)
        )

    @Slot()
    def _update_delete_button(self) -> None:
        row = self.sources_table.currentRow()
        self.delete_source_button.setEnabled(0 <= row < len(self._visible_source_ids))

    @Slot()
    def _delete_source(self) -> None:
        teacher_id = self.teacher_box.currentData()
        row = self.sources_table.currentRow()
        if teacher_id is None or not 0 <= row < len(self._visible_source_ids):
            return
        source_id = self._visible_source_ids[row]
        filename = self.sources_table.item(row, 4).text()
        answer = QMessageBox.question(
            self, "Удалить импортированный источник?",
            f"Удалить «{filename}» из базы данных?\n"
            "Исходный XLSX-файл на диске останется. Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.delete_source(teacher_id, source_id)
        except DomainError as error:
            self._show_error(error)
            return
        self.refresh()
        self.status_label.setText("Импортированный источник удалён из базы данных.")
        self.settings_saved.emit()

    @Slot()
    def _confirm_rate(self) -> None:
        teacher_id = self.teacher_box.currentData()
        if teacher_id is None:
            return
        raw = self.rate_input.text().strip().replace(",", ".")
        try:
            rate = Decimal(raw)
        except InvalidOperation:
            self._show_error(InvalidTeacherSettingsError("Введите ставку числом, например 0,5."))
            return
        try:
            self._service.confirm_effective_rate(teacher_id, rate)
        except DomainError as error:
            self._show_error(error)
            return
        self.status_label.setText("Эффективная ставка подтверждена.")
        self.settings_saved.emit()

    @Slot()
    def _save_personal_data(self) -> None:
        teacher_id = self.teacher_box.currentData()
        if teacher_id is None:
            return
        values = {name: edit.text() for name, edit in self.personal_inputs.items()}
        try:
            for name in ("birth_date", "passport_issue_date"):
                raw = values[name].strip()
                values[name] = datetime.strptime(raw, "%d.%m.%Y").date() if raw else None
            self._service.save_personal_data(teacher_id, TeacherPersonalData(**values))
        except ValueError:
            self._show_error(InvalidTeacherSettingsError(
                "Даты укажите в формате ДД.ММ.ГГГГ, например 15.04.1980."
            ))
            return
        except DomainError as error:
            self._show_error(error)
            return
        self.refresh()
        self.status_label.setText("Данные преподавателя сохранены.")
        self.settings_saved.emit()

    @Slot()
    def _save_sources(self) -> None:
        teacher_id = self.teacher_box.currentData()
        if teacher_id is None:
            return
        choices = {
            source_id: choice.currentData()
            for source_id, choice in self._source_choices.items()
        }
        try:
            self._service.save_source_inclusions(teacher_id, choices)
        except DomainError as error:
            self._show_error(error)
            return
        self.status_label.setText("Выбор источников сохранен.")
        self.settings_saved.emit()

    def _show_error(self, error: DomainError) -> None:
        QMessageBox.warning(self, "Не удалось сохранить карточку", str(error))


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "—"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
