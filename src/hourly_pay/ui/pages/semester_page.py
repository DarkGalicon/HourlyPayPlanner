from datetime import datetime

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hourly_pay.application.semester_settings import SemesterSettingsService
from hourly_pay.domain.errors import DomainError, InvalidScheduleError


class SemesterPage(QWidget):
    def __init__(self, service: SemesterSettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self.year_box = QComboBox(self)
        self.year_box.setObjectName("semesterSettingsYear")
        self.year_box.currentIndexChanged.connect(self._show_dates)
        self.start_inputs: dict[int, QLineEdit] = {}
        self.save_buttons: dict[int, QPushButton] = {}
        form = QFormLayout()
        form.addRow("Учебный год", self.year_box)
        for semester in (1, 2):
            field = QLineEdit(self)
            field.setObjectName(f"practiceStartSemester{semester}")
            field.setPlaceholderText("ДД.ММ.ГГГГ; пусто — дата не задана")
            self.start_inputs[semester] = field
            button = QPushButton("Сохранить", self)
            button.setObjectName(f"saveSemesterStart{semester}")
            button.clicked.connect(lambda _checked=False, number=semester: self._save(number))
            self.save_buttons[semester] = button
            row = QHBoxLayout()
            row.addWidget(field)
            row.addWidget(button)
            form.addRow(f"Первая дата Пр/Лаб, {semester}-й семестр", row)
        self.status_label = QLabel(self)
        self.status_label.setObjectName("semesterSettingsStatus")
        self.status_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(
            "Дата общая для всех преподавателей, дисциплин и групп учебного года. "
            "До неё генератор ставит только лекции. Январь для II семестра остаётся "
            "необязательным согласно помесячному плану.", self
        ))
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        current_id = self.year_box.currentData()
        self.year_box.blockSignals(True)
        self.year_box.clear()
        for year in self._service.list_years():
            self.year_box.addItem(year.name, year.id)
        if current_id is not None:
            index = self.year_box.findData(current_id)
            if index >= 0:
                self.year_box.setCurrentIndex(index)
        self.year_box.blockSignals(False)
        self._show_dates()

    @Slot()
    def _show_dates(self) -> None:
        year_id = self.year_box.currentData()
        for semester, field in self.start_inputs.items():
            value = self._service.get(year_id, semester) if year_id is not None else None
            field.setText(value.strftime("%d.%m.%Y") if value else "")
        self.status_label.setText("Пустая дата не разрешает практики и лабораторные.")

    @Slot()
    def _save(self, semester: int) -> None:
        year_id = self.year_box.currentData()
        if year_id is None:
            self.status_label.setText("Сначала импортируйте учебный год.")
            return
        try:
            raw = self.start_inputs[semester].text().strip()
            if raw:
                try:
                    value = datetime.strptime(raw, "%d.%m.%Y").date()
                except ValueError as error:
                    raise InvalidScheduleError(
                        f"Введите дату {semester}-го семестра в формате ДД.ММ.ГГГГ."
                    ) from error
            else:
                value = None
            self._service.save(year_id, semester, value)
        except DomainError as error:
            self.status_label.setText(str(error))
            return
        self.status_label.setText(f"Дата допуска {semester}-го семестра сохранена.")
