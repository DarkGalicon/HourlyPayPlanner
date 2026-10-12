from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from hourly_pay.domain.anomalies import detect_workload_anomalies
from hourly_pay.domain.enums import (
    SessionPeriod,
    StudyForm,
    WarningCode,
    WarningSeverity,
    WorkType,
)
from hourly_pay.domain.errors import UnrecognizedFormatError
from hourly_pay.domain.models import (
    AcademicYear,
    ImportWarning,
    Teacher,
    WorkloadItem,
    WorkloadSource,
)
from hourly_pay.domain.rules import counts_toward_plan, is_idpo_group
from hourly_pay.importers.base import ImportResult, ImportTotals

PARSER_VERSION = "nagr_xlsx_v2"
_YEAR_RE = re.compile(r"\b(20\d{2})\s*[-–—/]\s*(20\d{2})\b")


@dataclass(frozen=True, slots=True)
class _ColumnMapping:
    column: int
    work_type: WorkType
    session_period: SessionPeriod | None = None
    control_column: int | None = None


_FULL_TIME_MAPPING = (
    _ColumnMapping(8, WorkType.LECTURE),
    _ColumnMapping(9, WorkType.PRACTICE),
    _ColumnMapping(10, WorkType.LAB),
    _ColumnMapping(12, WorkType.CONTROL, control_column=11),
    _ColumnMapping(13, WorkType.COURSEWORK),
    _ColumnMapping(14, WorkType.THESIS),
    _ColumnMapping(15, WorkType.STATE_EXAM),
    _ColumnMapping(16, WorkType.CONTROL_WORK),
    _ColumnMapping(17, WorkType.RGR),
    _ColumnMapping(18, WorkType.INTERNSHIP),
    _ColumnMapping(21, WorkType.EXAM_CONSULTATION),
)

_CORRESPONDENCE_MAPPING = (
    _ColumnMapping(6, WorkType.LECTURE, SessionPeriod.UST),
    _ColumnMapping(7, WorkType.LECTURE, SessionPeriod.WINTER),
    _ColumnMapping(8, WorkType.LECTURE, SessionPeriod.SUMMER),
    _ColumnMapping(9, WorkType.PRACTICE, SessionPeriod.UST),
    _ColumnMapping(10, WorkType.PRACTICE, SessionPeriod.WINTER),
    _ColumnMapping(11, WorkType.PRACTICE, SessionPeriod.SUMMER),
    _ColumnMapping(12, WorkType.LAB, SessionPeriod.UST),
    _ColumnMapping(13, WorkType.LAB, SessionPeriod.WINTER),
    _ColumnMapping(14, WorkType.LAB, SessionPeriod.SUMMER),
    _ColumnMapping(16, WorkType.CONTROL, SessionPeriod.UST, 15),
    _ColumnMapping(17, WorkType.CONTROL, SessionPeriod.WINTER, 15),
    _ColumnMapping(18, WorkType.CONTROL, SessionPeriod.SUMMER, 15),
    _ColumnMapping(19, WorkType.CONTROL, SessionPeriod.WINTER, 15),
    _ColumnMapping(20, WorkType.CONTROL, SessionPeriod.SUMMER, 15),
    _ColumnMapping(21, WorkType.COURSEWORK),
    _ColumnMapping(22, WorkType.THESIS),
    _ColumnMapping(23, WorkType.STATE_EXAM),
    _ColumnMapping(24, WorkType.RGR),
    _ColumnMapping(25, WorkType.INTERNSHIP),
    _ColumnMapping(28, WorkType.EXAM_CONSULTATION),
)


class NagrXlsxV1Importer:
    """Parser for the documented current export of nagr.stgau.ru."""

    def __init__(self, *, known_control_kinds: Collection[str] = ("Эк", "Зч")) -> None:
        self._known_control_kinds = {_normalized_text(value) for value in known_control_kinds}

    def import_file(
        self,
        path: Path | str,
        *,
        known_hashes: set[str] | frozenset[str] = frozenset(),
    ) -> ImportResult:
        source_path = Path(path)
        file_sha256 = calculate_sha256(source_path)
        warnings: list[ImportWarning] = []
        if file_sha256 in known_hashes:
            warnings.append(
                ImportWarning(
                    code=WarningCode.DUPLICATE_IMPORT,
                    severity=WarningSeverity.WARNING,
                    message="Этот файл уже импортирован.",
                )
            )

        try:
            workbook = load_workbook(source_path, data_only=True, read_only=True)
        except Exception as exc:
            raise UnrecognizedFormatError("не удалось открыть XLSX") from exc

        try:
            self._validate_workbook(workbook)
            teacher, academic_year, employment_type, reported_rate = self._parse_title(
                workbook["Титульный"]
            )
            totals = self._parse_summary(workbook["Summary"])
            items: list[WorkloadItem] = []
            for sheet_name, semester in (("AutumnOch", 1), ("SpringOch", 2)):
                if sheet_name not in workbook.sheetnames:
                    continue
                sheet_items, sheet_warnings = self._parse_workload_sheet(
                    workbook[sheet_name],
                    study_form=StudyForm.FULL_TIME,
                    semester=semester,
                    mapping=_FULL_TIME_MAPPING,
                    group_column=2,
                    course_column=3,
                    stream_column=4,
                    student_count_column=5,
                    faculty_column=6,
                    discipline_column=7,
                    row_total_column=19,
                )
                items.extend(sheet_items)
                warnings.extend(sheet_warnings)

            if "Zaoch" in workbook.sheetnames:
                sheet_items, sheet_warnings = self._parse_workload_sheet(
                    workbook["Zaoch"],
                    study_form=StudyForm.CORRESPONDENCE,
                    semester=None,
                    mapping=_CORRESPONDENCE_MAPPING,
                    group_column=2,
                    course_column=3,
                    stream_column=None,
                    student_count_column=4,
                    faculty_column=None,
                    discipline_column=5,
                    row_total_column=26,
                )
                items.extend(sheet_items)
                warnings.extend(sheet_warnings)

            warnings.extend(
                detect_workload_anomalies(
                    items,
                    known_control_kinds=self._known_control_kinds,
                )
            )

            for form, reported, label in (
                (StudyForm.FULL_TIME, totals.full_time, "очная форма"),
                (StudyForm.CORRESPONDENCE, totals.correspondence, "заочная форма"),
                (None, totals.overall, "вся нагрузка"),
            ):
                if reported is None:
                    continue
                parsed = sum(
                    (
                        item.hours
                        for item in items
                        if counts_toward_plan(item)
                        and (form is None or item.study_form is form)
                    ),
                    start=Decimal("0"),
                )
                if parsed != reported:
                    difference = reported - parsed
                    warnings.append(
                        ImportWarning(
                            code=WarningCode.SUMMARY_TOTAL_MISMATCH,
                            severity=WarningSeverity.WARNING,
                            message=(
                                f"Summary ({label}): план {reported} ч, "
                                f"распознано {parsed} ч, разница {difference} ч."
                            ),
                            raw_value=str(difference),
                            sheet_name="Summary",
                        )
                    )

            source = WorkloadSource(
                original_filename=source_path.name,
                file_sha256=file_sha256,
                employment_type=employment_type,
                reported_rate=reported_rate,
                reported_total_hours=totals.overall,
                parser_version=PARSER_VERSION,
            )
            return ImportResult(
                teacher=teacher,
                academic_year=academic_year,
                source=source,
                items=items,
                warnings=warnings,
                summary_totals=totals,
            )
        finally:
            workbook.close()

    parse = import_file

    def _validate_workbook(self, workbook: Workbook) -> None:
        missing = {"Титульный", "Summary"} - set(workbook.sheetnames)
        if missing:
            raise UnrecognizedFormatError(
                "отсутствуют обязательные листы: " + ", ".join(sorted(missing))
            )
        full_time_names = {"AutumnOch", "SpringOch"} & set(workbook.sheetnames)
        if not full_time_names:
            raise UnrecognizedFormatError("нет листов AutumnOch или SpringOch")
        for name in full_time_names:
            if not _has_labels(
                workbook[name], {"группа", "дисциплина", "лек", "пр", "лаб", "итого"}
            ):
                raise UnrecognizedFormatError(f"неожиданная структура листа {name}")
        if "Zaoch" in workbook.sheetnames and not _has_labels(
            workbook["Zaoch"], {"группа", "дисциплина", "лек", "пр", "лаб", "итого"}
        ):
            raise UnrecognizedFormatError("неожиданная структура листа Zaoch")

    def _parse_title(
        self, sheet: Worksheet
    ) -> tuple[Teacher, AcademicYear, str, Decimal | None]:
        texts = [
            (cell.row, cell.column, _clean_text(cell.value))
            for row in sheet.iter_rows()
            for cell in row
            if _clean_text(cell.value)
        ]
        plan_row = next(
            (row for row, _, value in texts if "индивидуальный план" in value.casefold()), None
        )
        if plan_row is None:
            raise UnrecognizedFormatError("на титульном листе нет названия документа")

        identity = next(
            (
                value
                for row, _, value in texts
                if plan_row < row <= plan_row + 6 and "," in value
            ),
            None,
        )
        if identity is None:
            raise UnrecognizedFormatError("не найдены ФИО и тип занятости")
        full_name, separator, employment_type = identity.rpartition(",")
        if not separator or not full_name.strip() or not employment_type.strip():
            raise UnrecognizedFormatError("не удалось разделить ФИО и тип занятости")

        year_match = next(
            (match for _, _, value in texts if (match := _YEAR_RE.search(value))), None
        )
        if year_match is None:
            raise UnrecognizedFormatError("не найден учебный год")
        year_name = f"{year_match.group(1)}-{year_match.group(2)}"

        degree = _labeled_value(sheet, "степень")
        title = _labeled_value(sheet, "звание")
        position = _labeled_value(sheet, "должность")
        department = next(
            (
                value
                for row, _, value in texts
                if row > plan_row and value.casefold().startswith("кафедра ")
            ),
            None,
        )
        rate = decimal_from_cell(_labeled_raw_value(sheet, "ставок"))
        teacher = Teacher(
            full_name=full_name.strip(),
            department=department,
            degree=degree,
            title=title,
            position=position,
        )
        return teacher, AcademicYear(name=year_name), employment_type.strip(), rate

    def _parse_summary(self, sheet: Worksheet) -> ImportTotals:
        for row in sheet.iter_rows():
            if _normalized_text(row[0].value) == "учебная работа":
                return ImportTotals(
                    full_time=decimal_from_cell(row[1].value),
                    correspondence=decimal_from_cell(row[3].value),
                    overall=decimal_from_cell(row[5].value),
                )
        raise UnrecognizedFormatError("в Summary нет строки «Учебная работа»")

    def _parse_workload_sheet(
        self,
        sheet: Worksheet,
        *,
        study_form: StudyForm,
        semester: int | None,
        mapping: Iterable[_ColumnMapping],
        group_column: int,
        course_column: int,
        stream_column: int | None,
        student_count_column: int,
        faculty_column: int | None,
        discipline_column: int,
        row_total_column: int,
    ) -> tuple[list[WorkloadItem], list[ImportWarning]]:
        items: list[WorkloadItem] = []
        warnings: list[ImportWarning] = []
        mappings = tuple(mapping)

        for excel_row in range(1, sheet.max_row + 1):
            source_number = _positive_int(sheet.cell(excel_row, 1).value)
            if source_number is None:
                continue
            group_raw = sheet.cell(excel_row, group_column).value
            discipline_raw = sheet.cell(excel_row, discipline_column).value
            if _looks_like_numbering_row(group_raw, discipline_raw):
                continue

            parsed_hours: list[tuple[_ColumnMapping, Decimal]] = []
            for column_mapping in mappings:
                hours = decimal_from_cell(sheet.cell(excel_row, column_mapping.column).value)
                if hours is not None and hours != 0:
                    parsed_hours.append((column_mapping, hours))
            group_name = _clean_text(group_raw) or None
            discipline = _clean_text(discipline_raw) or None
            row_total = decimal_from_cell(sheet.cell(excel_row, row_total_column).value)
            if not parsed_hours and (row_total is None or row_total == 0):
                continue
            consultation_hours = sum(
                (
                    hours
                    for column_mapping, hours in parsed_hours
                    if column_mapping.work_type is WorkType.EXAM_CONSULTATION
                ),
                start=Decimal("0"),
            )
            other_hours = sum(
                (
                    hours
                    for column_mapping, hours in parsed_hours
                    if column_mapping.work_type is not WorkType.EXAM_CONSULTATION
                ),
                start=Decimal("0"),
            )
            consultation_outside_total = (
                row_total is not None
                and consultation_hours != 0
                and other_hours == row_total
            )
            if consultation_outside_total:
                warnings.append(
                    ImportWarning(
                        code=WarningCode.OUTSIDE_ROW_TOTAL,
                        severity=WarningSeverity.INFO,
                        message=(
                            f"Консультации к экзамену ({consultation_hours} ч) указаны "
                            "вне графы «Итого» и не добавлены к плановой нагрузке."
                        ),
                        source_row_number=excel_row,
                        raw_value=str(consultation_hours),
                        sheet_name=sheet.title,
                    )
                )
            common_fields = {
                "study_form": study_form,
                "semester": semester,
                "source_row_number": excel_row,
                "group_name": group_name,
                "course": _clean_text(sheet.cell(excel_row, course_column).value) or None,
                "stream": (
                    _clean_text(sheet.cell(excel_row, stream_column).value) or None
                    if stream_column is not None
                    else None
                ),
                "student_count": _non_negative_int(
                    sheet.cell(excel_row, student_count_column).value
                ),
                "faculty": (
                    _clean_text(sheet.cell(excel_row, faculty_column).value) or None
                    if faculty_column is not None
                    else None
                ),
                "discipline": discipline,
                "row_total_hours": row_total,
                "is_idpo": is_idpo_group(group_name),
            }
            for column_mapping, hours in parsed_hours:
                control_type = None
                if column_mapping.control_column is not None:
                    control_type = (
                        _clean_text(sheet.cell(excel_row, column_mapping.control_column).value)
                        or None
                    )

                raw_context = {"sheet": sheet.title, "source_number": source_number}
                if (
                    consultation_outside_total
                    and column_mapping.work_type is WorkType.EXAM_CONSULTATION
                ):
                    raw_context["outside_row_total"] = True
                items.append(
                    WorkloadItem(
                        **common_fields,
                        session_period=column_mapping.session_period,
                        work_type=column_mapping.work_type,
                        control_type=control_type,
                        hours=hours,
                        raw_context=raw_context,
                    )
                )

            counted_hours = other_hours + (
                Decimal("0") if consultation_outside_total else consultation_hours
            )
            if row_total is not None and row_total > counted_hours:
                difference = row_total - counted_hours
                control_column = next(
                    (mapping.control_column for mapping in mappings if mapping.control_column),
                    None,
                )
                control_kind = (
                    _clean_text(sheet.cell(excel_row, control_column).value)
                    if control_column is not None
                    else ""
                )
                items.append(
                    WorkloadItem(
                        **common_fields,
                        work_type=WorkType.UNCLASSIFIED,
                        hours=difference,
                        raw_context={
                            "sheet": sheet.title,
                            "source_number": source_number,
                            "unclassified_reason": "row_total_difference",
                        },
                    )
                )
                warnings.append(
                    ImportWarning(
                        code=WarningCode.UNEXPLAINED_TOTAL_DIFF,
                        severity=WarningSeverity.WARNING,
                        message=(
                            f"Итого {row_total} ч, в колонках видов работ {counted_hours} ч: "
                            f"нерасшифровано {difference} ч. Часы учтены в плане, "
                            "но недоступны для почасовки."
                            + (
                                f" Вид контроля «{control_kind}» указан, но связь "
                                "с разницей не подтверждена."
                                if control_kind
                                else ""
                            )
                        ),
                        source_row_number=excel_row,
                        raw_value=str(difference),
                        sheet_name=sheet.title,
                    )
                )

        return items, warnings


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_from_cell(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise UnrecognizedFormatError(f"ожидалось число, получено {value!r}")
    normalized = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise UnrecognizedFormatError(f"неверное числовое значение {value!r}") from exc


def _has_labels(sheet: Worksheet, required: set[str]) -> bool:
    found: set[str] = set()
    for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 10)):
        for cell in row:
            value = _normalized_text(cell.value)
            if value in required:
                found.add(value)
    return required <= found


def _labeled_value(sheet: Worksheet, label: str) -> str | None:
    value = _labeled_raw_value(sheet, label)
    return _clean_text(value) or None


def _labeled_raw_value(sheet: Worksheet, label: str) -> Any:
    normalized_label = _normalized_text(label)
    for row in sheet.iter_rows():
        for cell in row:
            text = _normalized_text(cell.value).removesuffix(":")
            if text != normalized_label:
                continue
            raw_text = _clean_text(cell.value)
            if ":" in raw_text and raw_text.split(":", 1)[1].strip():
                return raw_text.split(":", 1)[1].strip()
            cell_column = cell.column
            if not isinstance(cell_column, int):
                continue
            for column in range(cell_column + 1, sheet.max_column + 1):
                candidate = sheet.cell(cell.row, column).value
                if _clean_text(candidate):
                    return candidate
    return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def _normalized_text(value: Any) -> str:
    return _clean_text(value).casefold().removesuffix(":")


def _positive_int(value: Any) -> int | None:
    number = _try_decimal(value)
    if number is None:
        return None
    if number <= 0 or number != number.to_integral_value():
        return None
    return int(number)


def _non_negative_int(value: Any) -> int | None:
    number = _try_decimal(value)
    if number is None:
        return None
    if number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _looks_like_numbering_row(group: Any, discipline: Any) -> bool:
    return _try_decimal(group) is not None and _try_decimal(discipline) is not None


def _try_decimal(value: Any) -> Decimal | None:
    try:
        return decimal_from_cell(value)
    except UnrecognizedFormatError:
        return None
