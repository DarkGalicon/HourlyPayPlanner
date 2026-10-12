from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from hourly_pay.application.import_workload import WorkloadImportPreview
from hourly_pay.domain.enums import StudyForm
from hourly_pay.domain.rules import counts_toward_plan

HEADERS = (
    "Файл",
    "Преподаватель",
    "Тип занятости",
    "Ставка в файле",
    "Всего часов",
    "Осень",
    "Весна",
    "Заочно",
    "ИДПО",
    "Предупреждений",
)


class ImportPreviewTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._previews: tuple[WorkloadImportPreview, ...] = ()

    @property
    def previews(self) -> tuple[WorkloadImportPreview, ...]:
        return self._previews

    def set_previews(self, previews: tuple[WorkloadImportPreview, ...]) -> None:
        self.beginResetModel()
        self._previews = previews
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._previews)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> str | None:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        preview = self._previews[index.row()]
        result = preview.result
        full_time_autumn = sum(
            (
                item.hours
                for item in result.items
                if item.study_form is StudyForm.FULL_TIME
                and item.semester == 1
                and counts_toward_plan(item)
            ),
            start=Decimal("0"),
        )
        full_time_spring = sum(
            (
                item.hours
                for item in result.items
                if item.study_form is StudyForm.FULL_TIME
                and item.semester == 2
                and counts_toward_plan(item)
            ),
            start=Decimal("0"),
        )
        correspondence = sum(
            (
                item.hours
                for item in result.items
                if item.study_form is StudyForm.CORRESPONDENCE
                and counts_toward_plan(item)
            ),
            start=Decimal("0"),
        )
        values = (
            preview.path.name,
            result.teacher.full_name,
            result.source.employment_type,
            _decimal_text(result.source.reported_rate),
            _decimal_text(result.source.reported_total_hours),
            _decimal_text(full_time_autumn),
            _decimal_text(full_time_spring),
            _decimal_text(correspondence),
            _decimal_text(result.idpo_hours),
            str(len(result.warnings)),
        )
        return values[index.column()]


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "—"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
