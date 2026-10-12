from datetime import date, time
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

from hourly_pay.domain.enums import WorkType
from hourly_pay.domain.errors import InvalidDocumentExportError
from hourly_pay.domain.models import Lesson, Teacher, TimeSlot
from hourly_pay.exporters.hourly_docx import (
    DocxExportOptions,
    export_hourly_statement,
    safe_statement_filename,
)


@pytest.fixture
def statement_template(tmp_path: Path) -> Path:
    path = tmp_path / "template.docx"
    document = Document()
    document.add_paragraph("от {FIO}")
    document.add_paragraph("Степень {STEPEN}; звание {ZVANIE}; должность {DOLZNOST}")
    document.add_paragraph(
        "Родился {BIRTH_DATE}; адрес {ADDRESS}; паспорт {PASS_SERIAL} {PASS_NUM}; "
        "выдан {OTDEL} {DATE_OTDEL}; СНИЛС {STRAX_NUM}; ИНН {INN_NUM}"
    )
    table = document.add_table(rows=3, cols=6)
    for cell, text in zip(
        table.rows[0].cells,
        ("Дата", "Время", "Группа", "Дисциплина", "Вид", "Часы"),
        strict=True,
    ):
        cell.text = text
    for cell, text in zip(
        table.rows[1].cells,
        ("{DATA}", "{TIME}", "{GROUP}", "{DISCIPLINE}", "{TYPE}", "{HOURS}"),
        strict=True,
    ):
        cell.text = text
    table.rows[2].cells[-1].text = "{HOURS_SUM}"
    document.add_paragraph("«{DAY)» {MONTH} {YEAR} г.")
    document.save(path)
    return path


def _lessons() -> list[Lesson]:
    return [
        Lesson(1, 1, date(2027, 3, 2), 1, "Г-1", "Очень длинная дисциплина", kind, None)
        for kind in (WorkType.LECTURE, WorkType.LAB)
    ]


def _slots() -> list[TimeSlot]:
    return [TimeSlot(1, 1, time(8, 30), time(10, 5), "08:30-10:05")]


def _all_text(document: Document) -> str:
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        parts.extend(cell.text for row in table.rows for cell in row.cells)
    return "\n".join(parts)


def test_export_fills_lessons_total_and_teacher_without_changing_template(
    statement_template: Path, tmp_path: Path
) -> None:
    original_hash = sha256(statement_template.read_bytes()).hexdigest()
    result = export_hourly_statement(
        statement_template,
        tmp_path / "out",
        teacher=Teacher(
            "Тестов Тест Тестович", degree="к.н.", title="доцент",
            birth_date=date(1980, 4, 15), address="ул. Тестовая, 1",
            passport_series="1234", passport_number="567890",
            passport_issued_by="Отдел МВД", passport_issue_date=date(2001, 5, 6),
            snils="123-456-789 00", inn="123456789012",
        ),
        lessons=_lessons(),
        time_slots=_slots(),
        year=2027,
        month=3,
        options=DocxExportOptions(
            include_degree=True,
            include_title=True,
            statement_date=date(2027, 3, 31),
        ),
    )

    assert result.output_path.exists()
    assert result.lesson_count == 2
    assert result.hours_sum == Decimal("4")
    assert sha256(statement_template.read_bytes()).hexdigest() == original_hash
    output = Document(result.output_path)
    lesson_table = output.tables[0]
    assert len(lesson_table.rows) == 4
    assert [cell.text for cell in lesson_table.rows[1].cells] == [
        "02.03.2027",
        "08:30-10:05",
        "Г-1",
        "Очень длинная дисциплина",
        "лекционные",
        "2",
    ]
    assert lesson_table.rows[2].cells[4].text == "лабораторные"
    assert lesson_table.rows[3].cells[5].text == "4"
    assert lesson_table.rows[0]._tr.get_or_add_trPr().find(qn("w:tblHeader")) is not None

    text = _all_text(output)
    assert "Тестов Тест Тестович" in text
    assert "к.н." in text
    assert "доцент" in text
    assert "15.04.1980" in text
    assert "ул. Тестовая, 1" in text
    assert "1234 567890" in text
    assert "Отдел МВД 06.05.2001" in text
    assert "123-456-789 00" in text
    assert "123456789012" in text
    assert "31» марта 2027" in text
    assert "{PASS_SERIAL}" not in text
    assert "{PASS_NUM}" not in text
    assert "{INN_NUM}" not in text


def test_optional_teacher_fields_are_blank_by_default(
    statement_template: Path, tmp_path: Path
) -> None:
    result = export_hourly_statement(
        statement_template,
        tmp_path / "out",
        teacher=Teacher("Тестов Т.Т.", degree="секрет", title="секрет", position="секрет"),
        lessons=_lessons()[:1],
        time_slots=_slots(),
        year=2027,
        month=3,
    )
    text = _all_text(Document(result.output_path))
    assert "секрет" not in text
    assert "{STEPEN}" not in text
    assert "{ZVANIE}" not in text
    assert "{DOLZNOST}" not in text


def test_signature_and_hours_tables_have_two_empty_paragraphs(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    document = Document()
    lessons_table = document.add_table(rows=2, cols=6)
    for cell, token in zip(
        lessons_table.rows[1].cells,
        ("{DATA}", "{TIME}", "{GROUP}", "{DISCIPLINE}", "{TYPE}", "{HOURS}"),
        strict=True,
    ):
        cell.text = token
    date_table = document.add_table(rows=1, cols=1)
    date_table.cell(0, 0).text = "«{DAY}» {MONTH} {YEAR} г. Подпись"
    document.add_paragraph()
    hours_table = document.add_table(rows=1, cols=2)
    hours_table.cell(0, 0).text = "Количество часов"
    document.save(template)

    result = export_hourly_statement(
        template,
        tmp_path / "out",
        teacher=Teacher("Тестов Т.Т."),
        lessons=_lessons()[:1],
        time_slots=_slots(),
        year=2027,
        month=3,
        options=DocxExportOptions(statement_date=date(2027, 3, 31)),
    )

    output = Document(result.output_path)
    between = []
    element = output.tables[1]._tbl.getnext()
    while element is not output.tables[2]._tbl:
        between.append(element)
        element = element.getnext()
    assert len(between) == 2
    assert all(element.tag == qn("w:p") for element in between)
    assert all(not element.attrib for element in between)
    assert all(element.find(qn("w:hyperlink")) is None for element in between)
    assert all(element.find(qn("w:fldChar")) is None for element in between)
    assert "31» марта 2027" in output.tables[1].cell(0, 0).text


def test_many_lessons_do_not_force_blank_space_before_signature(
    statement_template: Path, tmp_path: Path
) -> None:
    template = Document(statement_template)
    for index, cell in enumerate(template.tables[0].rows[1].cells, start=1):
        cell.paragraphs[0]._p.set(qn("w14:paraId"), f"{index:08X}")
    template.save(statement_template)
    result = export_hourly_statement(
        statement_template,
        tmp_path / "out",
        teacher=Teacher("Тестов Т.Т."),
        lessons=_lessons()[:1] * 8,
        time_slots=_slots(),
        year=2027,
        month=3,
        options=DocxExportOptions(statement_date=date(2027, 3, 31)),
    )
    output = Document(result.output_path)
    assert not output.element.body.findall(".//" + qn("w:pageBreakBefore"))
    assert output.tables[0].rows[1].cells[0].paragraphs[0].runs[0].font.size == Pt(10)
    paragraph_ids = [
        paragraph.get(qn("w14:paraId"))
        for paragraph in output.element.body.findall(".//" + qn("w:p"))
        if paragraph.get(qn("w14:paraId"))
    ]
    assert len(paragraph_ids) == len(set(paragraph_ids))
    assert not output.element.body.findall(".//" + qn("w:hyperlink"))
    assert not output.element.body.findall(".//" + qn("w:outlineLvl"))


def test_invalid_lesson_hours_are_rejected(statement_template: Path, tmp_path: Path) -> None:
    lesson = _lessons()[0]
    lesson.hours = Decimal("3")
    with pytest.raises(InvalidDocumentExportError, match="ровно 2 часа"):
        export_hourly_statement(
            statement_template,
            tmp_path,
            teacher=Teacher("Тестов Т.Т."),
            lessons=[lesson],
            time_slots=_slots(),
            year=2027,
            month=3,
        )


def test_safe_filename_removes_path_characters() -> None:
    filename = safe_statement_filename("Иванов/Петров Иван Иванович", 2027, 3)
    assert filename == "Почасовка_Иванов_Петров_ИИ_2027-03.docx"
    assert "/" not in filename


def test_ten_hours_are_written_as_ten(statement_template: Path, tmp_path: Path) -> None:
    result = export_hourly_statement(
        statement_template,
        tmp_path / "out",
        teacher=Teacher("Тестов Т.Т."),
        lessons=_lessons()[:1] * 5,
        time_slots=_slots(),
        year=2027,
        month=3,
    )
    document = Document(result.output_path)
    assert result.hours_sum == Decimal("10")
    assert document.tables[0].rows[-1].cells[-1].text == "10"


def test_corrupt_template_reports_clear_error_without_output(tmp_path: Path) -> None:
    template = tmp_path / "broken.docx"
    template.write_text("not a docx", encoding="utf-8")
    output = tmp_path / "out"
    with pytest.raises(InvalidDocumentExportError, match="повреждён"):
        export_hourly_statement(
            template, output, teacher=Teacher("Тестов Т.Т."),
            lessons=_lessons()[:1], time_slots=_slots(), year=2027, month=3,
        )
    assert not list(output.iterdir())
