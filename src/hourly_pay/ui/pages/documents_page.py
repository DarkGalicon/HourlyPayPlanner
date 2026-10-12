from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.statement_export import StatementExportService
from hourly_pay.config.defaults import DEFAULT_DOCX_WORK_TYPE_LABELS
from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.errors import DomainError
from hourly_pay.exporters.hourly_docx import DocxExportOptions
from hourly_pay.ui.pages.schedule_page import MONTH_NAMES


class DocumentsPage(QWidget):
    def __init__(self, service: StatementExportService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self.teacher_box = QComboBox(self)
        self.teacher_box.currentIndexChanged.connect(self._select_teacher)
        self.year_box = QComboBox(self)
        self.year_box.currentIndexChanged.connect(self._select_year)
        self.month_box = QComboBox(self)
        self.month_box.currentIndexChanged.connect(self._update_export_button)
        self.template_edit = QLineEdit(self)
        self.template_edit.setObjectName("statementTemplatePath")
        self.template_edit.textChanged.connect(self._update_export_button)
        self.output_edit = QLineEdit(self)
        self.output_edit.setObjectName("statementOutputDirectory")
        self.output_edit.textChanged.connect(self._update_export_button)
        self.degree_check = QCheckBox("Указать степень", self)
        self.title_check = QCheckBox("Указать звание", self)
        self.position_check = QCheckBox("Указать должность", self)
        self.date_check = QCheckBox("Указать дату заявления", self)
        self.date_check.setChecked(True)
        self.statement_date = QDateEdit(QDate.currentDate(), self)
        self.statement_date.setCalendarPopup(True)
        self.statement_date.setDisplayFormat("dd.MM.yyyy")
        self.date_check.toggled.connect(self.statement_date.setEnabled)
        self.type_edits = {
            kind: QLineEdit(DEFAULT_DOCX_WORK_TYPE_LABELS[kind], self)
            for kind in (WorkType.LECTURE, WorkType.PRACTICE, WorkType.LAB)
        }
        self.export_button = QPushButton("Создать DOCX", self)
        self.export_button.setObjectName("exportStatementButton")
        self.export_button.clicked.connect(self._export)
        self.status_label = QLabel("Сначала выберите преподавателя и месяц с занятиями.", self)
        self.status_label.setObjectName("documentStatus")
        self.status_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Преподаватель", self.teacher_box)
        form.addRow("Учебный год", self.year_box)
        form.addRow("Месяц", self.month_box)
        form.addRow("Шаблон DOCX", self._path_row(self.template_edit, self._choose_template))
        form.addRow("Папка для документа", self._path_row(self.output_edit, self._choose_output))
        header_title = QLabel("Данные для шапки", self)
        header_title.setProperty("uiRole", "section")
        form.addRow(header_title)
        form.addRow(self.degree_check)
        form.addRow(self.title_check)
        form.addRow(self.position_check)
        form.addRow(self.date_check, self.statement_date)
        labels_title = QLabel("Формулировки видов занятий", self)
        labels_title.setProperty("uiRole", "section")
        form.addRow(labels_title)
        for kind, caption in (
            (WorkType.LECTURE, "Текст для лекций"),
            (WorkType.PRACTICE, "Текст для практик"),
            (WorkType.LAB, "Текст для лабораторных"),
        ):
            form.addRow(caption, self.type_edits[kind])
        content = QWidget(self)
        content.setObjectName("documentsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addLayout(form)
        content_layout.addStretch()
        scroll = QScrollArea(self)
        scroll.setObjectName("documentsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.export_button)
        layout.addWidget(self.status_label)
        self.refresh()

    def _path_row(self, edit: QLineEdit, action) -> QWidget:
        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        button = QPushButton("Обзор…", widget)
        button.clicked.connect(action)
        layout.addWidget(button)
        return widget

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
        self._select_year()

    @Slot()
    def _select_year(self) -> None:
        teacher_id = self.teacher_box.currentData()
        academic_year_id = self.year_box.currentData()
        previous = self.month_box.currentData()
        self.month_box.blockSignals(True)
        self.month_box.clear()
        if teacher_id is not None and academic_year_id is not None:
            try:
                months = self._service.available_months(teacher_id, academic_year_id)
            except DomainError as error:
                self.status_label.setText(str(error))
            else:
                for entry in months:
                    self.month_box.addItem(
                        f"{MONTH_NAMES.get(entry.month, str(entry.month))} {entry.year}",
                        (entry.year, entry.month),
                    )
                index = self.month_box.findData(previous)
                if index >= 0:
                    self.month_box.setCurrentIndex(index)
                if not months:
                    self.status_label.setText(
                        "Для выбранного учебного года нет распределённых часов. "
                        "Сначала сохраните помесячный план."
                    )
                else:
                    self.status_label.setText(
                        "Выберите шаблон и папку. Занятия месяца будут проверены перед экспортом."
                    )
        else:
            self.status_label.setText("Сначала выберите преподавателя и месяц с занятиями.")
        self.month_box.blockSignals(False)
        self._update_export_button()

    @Slot()
    def _choose_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите шаблон заявления", "", "DOCX (*.docx)"
        )
        if path:
            self.template_edit.setText(path)

    @Slot()
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для документа")
        if path:
            self.output_edit.setText(path)

    @Slot()
    def _update_export_button(self) -> None:
        self.export_button.setEnabled(
            self.teacher_box.currentData() is not None
            and self.year_box.currentData() is not None
            and self.month_box.currentData() is not None
            and bool(self.template_edit.text().strip())
            and bool(self.output_edit.text().strip())
        )

    @Slot()
    def _export(self) -> None:
        teacher_id = self.teacher_box.currentData()
        academic_year_id = self.year_box.currentData()
        period = self.month_box.currentData()
        if teacher_id is None or academic_year_id is None or period is None:
            return
        labels = {kind: edit.text().strip() for kind, edit in self.type_edits.items()}
        if any(not value for value in labels.values()):
            self.status_label.setText("Заполните текст для всех видов занятий.")
            return
        chosen_date = self.statement_date.date()
        options = DocxExportOptions(
            include_degree=self.degree_check.isChecked(),
            include_title=self.title_check.isChecked(),
            include_position=self.position_check.isChecked(),
            statement_date=(
                date(chosen_date.year(), chosen_date.month(), chosen_date.day())
                if self.date_check.isChecked() else None
            ),
            work_type_labels=labels,
        )
        try:
            result = self._service.export(
                teacher_id, academic_year_id, *period,
                Path(self.template_edit.text().strip()),
                Path(self.output_edit.text().strip()),
                options,
            )
        except (DomainError, OSError, ValueError) as error:
            self.status_label.setText(f"Не удалось создать документ: {error}")
            return
        self.status_label.setText(
            f"Создан файл {result.output_path} · {result.lesson_count} занятий · "
            f"{result.hours_sum} ч."
        )
