"""Convert the private historical XLS template to a distributable XLSX asset.

Run once after converting the source .xls with LibreOffice. Only the blank
"почасовка" worksheet is retained; sample employees and other sheets are removed.
"""

import argparse
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    workbook = load_workbook(args.source)
    if "почасовка" not in workbook:
        raise ValueError("В преобразованном шаблоне нет листа «почасовка».")
    for sheet in list(workbook):
        if sheet.title != "почасовка":
            workbook.remove(sheet)
    sheet = workbook["почасовка"]
    sheet["Z5"] = "{DEPARTMENT}"
    sheet.sheet_view.showGridLines = False
    workbook.properties.creator = ""
    workbook.properties.lastModifiedBy = ""
    workbook.properties.created = datetime(2000, 1, 1)
    workbook.properties.modified = datetime(2000, 1, 1)
    workbook.properties.lastPrinted = None
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(args.destination)


if __name__ == "__main__":
    main()
