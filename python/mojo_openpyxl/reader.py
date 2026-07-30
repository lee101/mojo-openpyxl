from __future__ import annotations

import datetime as dt
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

from .cell import Cell
from .workbook import Workbook
from .utils.exceptions import InvalidFileException

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": MAIN, "r": OFFICE_REL}
DATE_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
ROW_TAG = f"{{{MAIN}}}row"
CELL_TAG = f"{{{MAIN}}}c"
FORMULA_TAG = f"{{{MAIN}}}f"
VALUE_TAG = f"{{{MAIN}}}v"
TEXT_TAG = f"{{{MAIN}}}t"


def _number(value):
    if value in (None, ""):
        return None
    if "." in value or "e" in value or "E" in value:
        return float(value)
    try:
        return int(value)
    except ValueError:
        return float(value)


def _from_excel(value, epoch, date_only=False):
    number = float(value)
    days = int(number)
    fraction = number - days
    if epoch == "1900":
        base = dt.datetime(1899, 12, 30)
        if 0 < days < 60:
            days += 1
    else:
        base = dt.datetime(1904, 1, 1)
    result = base + dt.timedelta(days=days, seconds=round(fraction * 86400, 6))
    if date_only and fraction == 0:
        return result.date()
    return result


def _date_styles(archive):
    try:
        root = ET.fromstring(archive.read("xl/styles.xml"))
    except KeyError:
        return {}
    formats = {
        int(node.attrib["numFmtId"]): node.attrib.get("formatCode", "")
        for node in root.findall("m:numFmts/m:numFmt", NS)
    }
    result = {}
    for index, xf in enumerate(root.findall("m:cellXfs/m:xf", NS)):
        fmt_id = int(xf.attrib.get("numFmtId", 0))
        code = formats.get(fmt_id, "")
        cleaned = re.sub(r'"[^"]*"', "", code)
        cleaned = re.sub(r"\\.", "", cleaned)
        cleaned = re.sub(r"\[[^\]]*\]", "", cleaned).lower()
        if fmt_id in DATE_IDS or re.search(r"[ymdhis]", cleaned):
            time_only = (
                fmt_id in {18, 19, 20, 21, 45, 46, 47}
                or (not re.search(r"[yd]", cleaned) and re.search(r"[hs]", cleaned))
            )
            result[index] = "time" if time_only else "datetime"
    return result


def _shared_strings(archive):
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in si.iter(f"{{{MAIN}}}t")) for si in root]


def _sheet_target(target):
    target = target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return posixpath.normpath(posixpath.join("xl", target))


def _column_from_reference(reference):
    column = 0
    index = 1 if reference.startswith("$") else 0
    while index < len(reference):
        code = ord(reference[index])
        if 65 <= code <= 90:
            column = column * 26 + code - 64
        elif 97 <= code <= 122:
            column = column * 26 + code - 96
        else:
            break
        index += 1
    return column, index + (index < len(reference) and reference[index] == "$")


def _read_sheet(archive, target, sheet, shared, date_styles, epoch, data_only):
    root = ET.fromstring(archive.read(target))
    cells = sheet._cells
    max_row = 0
    max_column = 0
    for row_node in root.iter(ROW_TAG):
        row_text = row_node.attrib.get("r")
        row_index = int(row_text) if row_text else 0
        for node in row_node:
            if node.tag != CELL_TAG:
                continue
            attributes = node.attrib
            reference = attributes.get("r")
            if not reference:
                continue
            column, row_offset = _column_from_reference(reference)
            row = row_index or int(reference[row_offset:])
            kind = attributes.get("t", "n")
            style_text = attributes.get("s")
            style = int(style_text) if style_text else 0
            formula_present = False
            formula_text = None
            raw = None
            inline = None
            for child in node:
                if child.tag == VALUE_TAG:
                    raw = child.text
                elif child.tag == FORMULA_TAG:
                    formula_present = True
                    formula_text = child.text
                elif kind == "inlineStr":
                    inline = child
            if formula_present and not data_only:
                value = "=" + (formula_text or "")
            elif kind == "inlineStr":
                value = (
                    "".join(text.text or "" for text in inline.iter(TEXT_TAG))
                    if inline is not None
                    else ""
                )
            elif kind == "s":
                value = shared[int(raw)] if raw is not None else ""
            elif kind == "b":
                value = raw == "1"
            elif kind == "d":
                if "T" in raw:
                    value = dt.datetime.fromisoformat(raw)
                elif ":" in raw:
                    value = dt.time.fromisoformat(raw)
                else:
                    value = dt.date.fromisoformat(raw)
            elif kind in ("str", "e"):
                value = raw
            elif raw is None:
                value = None
            elif style in date_styles:
                converted = _from_excel(raw, epoch)
                value = converted.time() if date_styles[style] == "time" else converted
            else:
                value = _number(raw)
            cell = Cell(sheet, row, column)
            cell._value = value
            cells[(row, column)] = cell
            max_row = max(max_row, row)
            max_column = max(max_column, column)
    sheet._max_row = max_row
    sheet._max_column = max_column


def load_workbook(
    filename,
    read_only=False,
    keep_vba=False,
    data_only=False,
    keep_links=True,
    rich_text=False,
):
    if read_only:
        raise NotImplementedError("streaming read_only worksheets are not implemented")
    if keep_vba:
        raise NotImplementedError("VBA preservation is outside the xlsx-only scope")
    if rich_text:
        raise NotImplementedError("rich text preservation is not implemented")
    try:
        archive = zipfile.ZipFile(filename, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise InvalidFileException(str(exc)) from exc
    with archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        epoch = "1904" if workbook_xml.find("m:workbookPr", NS) is not None and workbook_xml.find("m:workbookPr", NS).attrib.get("date1904") in ("1", "true") else "1900"
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            rel.attrib["Id"]: _sheet_target(rel.attrib["Target"])
            for rel in rels.findall(f"{{{PKG_REL}}}Relationship")
            if rel.attrib.get("Type", "").endswith("/worksheet")
        }
        result = Workbook(write_only=True)
        result.write_only = False
        result.epoch = epoch
        shared = _shared_strings(archive)
        date_styles = _date_styles(archive)
        for sheet_node in workbook_xml.findall("m:sheets/m:sheet", NS):
            sheet = result.create_sheet(sheet_node.attrib["name"])
            rel_id = sheet_node.attrib[f"{{{OFFICE_REL}}}id"]
            _read_sheet(
                archive, targets[rel_id], sheet, shared, date_styles, epoch, data_only
            )
        view = workbook_xml.find("m:bookViews/m:workbookView", NS)
        if view is not None and result.worksheets:
            result._active_sheet_index = min(
                int(view.attrib.get("activeTab", 0)), len(result.worksheets) - 1
            )
        result.read_only = False
        return result
