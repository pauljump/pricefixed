"""Minimal XLSX row reader for published government snapshots.

It intentionally returns cell text only; catalog importers keep the selected source
fields unchanged in their row payload rather than relying on a spreadsheet library.
"""
from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _column_index(reference):
    letters = re.match(r"[A-Z]+", reference or "")
    if not letters:
        return 0
    result = 0
    for letter in letters.group(0):
        result = result * 26 + ord(letter) - ord("A") + 1
    return result - 1


def read_xlsx_rows(path):
    """Yield dictionaries for the first worksheet, using its first row as headers."""
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{NS}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{NS}t")))
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in archive.namelist():
            candidates = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if not candidates:
                raise ValueError("XLSX archive has no worksheet")
            sheet_name = candidates[0]
        root = ET.fromstring(archive.read(sheet_name))
        parsed_rows = []
        for row in root.findall(f".//{NS}row"):
            values = {}
            for cell in row.findall(f"{NS}c"):
                index = _column_index(cell.get("r"))
                value = cell.find(f"{NS}v")
                text = ""
                if cell.get("t") == "s" and value is not None:
                    text = shared[int(value.text)]
                elif cell.get("t") == "inlineStr":
                    text = "".join(node.text or "" for node in cell.iter(f"{NS}t"))
                elif value is not None:
                    text = value.text or ""
                values[index] = text.strip()
            parsed_rows.append(values)
    if not parsed_rows:
        return
    headers = {index: value.strip() for index, value in parsed_rows[0].items() if value.strip()}
    for row in parsed_rows[1:]:
        yield {header: row.get(index, "") for index, header in headers.items()}
