from pathlib import Path

import pytest
from openpyxl import Workbook


@pytest.fixture
def synthetic_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.xlsx"
    workbook = Workbook()
    title = workbook.active
    title.title = "Титульный"
    title["E12"] = "Индивидуальный план работы преподавателя"
    title["D14"] = "Тестов Т.Т., штатный преподаватель"
    title["G16"] = "на 2026-2027 учебный год"
    title["F18"] = "Кафедра тестирования"
    title["C20"] = "Степень:"
    title["J20"] = "кандидат наук"
    title["C21"] = "Звание:"
    title["J21"] = "доцент"
    title["C22"] = "Должность:"
    title["J22"] = "доцент"
    title["C23"] = "Ставок:"
    title["J23"] = "0,5"

    summary = workbook.create_sheet("Summary")
    summary.append(["Виды работ", "Очники", None, "Заочники", None, "Всего"])
    summary.append([None, "План", "Факт", "План", "Факт", "План, Бюджет, Внебюджет"])
    summary.append(["Учебная работа", "8", 0, 0, 0, "8"])

    autumn = workbook.create_sheet("AutumnOch")
    _add_full_time_header(autumn)
    autumn.append(
        [
            1,
            "ИДПО_TEST-1",
            1,
            None,
            10,
            "Факультет",
            "Дисциплина",
            "3",
            None,
            None,
            "Неизвестно",
            "1",
            None,
            None,
            None,
            None,
            None,
            None,
            "6",
        ]
    )
    autumn.append(
        [
            2,
            None,
            1,
            None,
            10,
            "Факультет",
            None,
            "2",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "2",
        ]
    )
    spring = workbook.create_sheet("SpringOch")
    _add_full_time_header(spring)
    workbook.save(path)
    return path


def _add_full_time_header(sheet: object) -> None:
    sheet.append(
        [
            "№ строки",
            "Группа",
            "Курс",
            "Поток",
            "Студ.",
            "Факультет",
            "Дисциплина",
            "Учебная нагрузка",
        ]
    )
    sheet.append(
        [None, None, None, None, None, None, None, "Лек", "Пр", "Лаб", "Контроль", None,
         "Курсовые", "Дипломники", "ГАК и ГЭК", "Контрольные", "РГР", "Практики",
         "Итого", "Факт", "Консультации экзамен"]
    )
    sheet.append([None, None, None, None, None, None, None, None, None, None, "Вид", "Час."])
    sheet.append(list(range(1, 22)))
