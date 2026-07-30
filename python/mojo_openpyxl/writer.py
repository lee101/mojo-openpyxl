from __future__ import annotations

import datetime as dt
import zipfile
from xml.etree.ElementTree import Element, SubElement, register_namespace, tostring

from ._lib import write_sheet
from .utils.cell import get_column_letter

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
register_namespace("r", REL)


def _xml(element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + tostring(
        element, encoding="utf-8"
    )


def _worksheet_xml(sheet) -> bytes:
    cells = sheet._stored_cells()
    if cells:
        min_row = min(cell.row for cell in cells)
        max_row = max(cell.row for cell in cells)
        min_col = min(cell.column for cell in cells)
        max_col = max(cell.column for cell in cells)
        dimension = (
            f"{get_column_letter(min_col)}{min_row}:"
            f"{get_column_letter(max_col)}{max_row}"
        )
    else:
        dimension = "A1:A1"
    prefix = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN}"><dimension ref="{dimension}"/><sheetData>'
    ).encode()
    return prefix + write_sheet(cells) + b"</sheetData></worksheet>"


def _workbook_xml(workbook) -> bytes:
    root = Element("workbook", {"xmlns": MAIN})
    SubElement(root, "workbookPr", {"date1904": "1" if workbook.epoch == "1904" else "0"})
    views = SubElement(root, "bookViews")
    SubElement(views, "workbookView", {"activeTab": str(workbook._active_sheet_index)})
    sheets = SubElement(root, "sheets")
    for index, sheet in enumerate(workbook.worksheets, 1):
        SubElement(
            sheets,
            "sheet",
            {"name": sheet.title, "sheetId": str(index), f"{{{REL}}}id": f"rId{index}"},
        )
    SubElement(root, "calcPr", {"calcId": "124519", "fullCalcOnLoad": "1"})
    return _xml(root)


def _relationships(workbook) -> bytes:
    root = Element("Relationships", {"xmlns": PKG_REL})
    for index, _ in enumerate(workbook.worksheets, 1):
        SubElement(
            root,
            "Relationship",
            {
                "Id": f"rId{index}",
                "Type": f"{REL}/worksheet",
                "Target": f"worksheets/sheet{index}.xml",
            },
        )
    SubElement(
        root,
        "Relationship",
        {"Id": f"rId{len(workbook.worksheets) + 1}", "Type": f"{REL}/styles", "Target": "styles.xml"},
    )
    return _xml(root)


def _content_types(workbook) -> bytes:
    root = Element(
        "Types",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"},
    )
    SubElement(root, "Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    SubElement(root, "Default", {"Extension": "xml", "ContentType": "application/xml"})
    SubElement(root, "Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    SubElement(root, "Override", {"PartName": "/xl/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
    for index, _ in enumerate(workbook.worksheets, 1):
        SubElement(root, "Override", {"PartName": f"/xl/worksheets/sheet{index}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
    return _xml(root)


def _root_rels() -> bytes:
    root = Element("Relationships", {"xmlns": PKG_REL})
    SubElement(root, "Relationship", {"Id": "rId1", "Type": f"{REL}/officeDocument", "Target": "xl/workbook.xml"})
    return _xml(root)


def _styles() -> bytes:
    root = Element("styleSheet", {"xmlns": MAIN})
    SubElement(root, "numFmts", {"count": "0"})
    fonts = SubElement(root, "fonts", {"count": "1"})
    SubElement(fonts, "font")
    fills = SubElement(root, "fills", {"count": "2"})
    SubElement(SubElement(fills, "fill"), "patternFill")
    SubElement(SubElement(fills, "fill"), "patternFill", {"patternType": "gray125"})
    borders = SubElement(root, "borders", {"count": "1"})
    SubElement(borders, "border")
    style_xfs = SubElement(root, "cellStyleXfs", {"count": "1"})
    SubElement(style_xfs, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"})
    cell_xfs = SubElement(root, "cellXfs", {"count": "1"})
    SubElement(cell_xfs, "xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    styles = SubElement(root, "cellStyles", {"count": "1"})
    SubElement(styles, "cellStyle", {"name": "Normal", "xfId": "0", "builtinId": "0"})
    SubElement(root, "tableStyles", {"count": "0", "defaultTableStyle": "TableStyleMedium9", "defaultPivotStyle": "PivotStyleLight16"})
    return _xml(root)


def save_workbook(workbook, filename):
    if not workbook.worksheets:
        raise IndexError("At least one sheet must be visible")
    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", _content_types(workbook))
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("xl/workbook.xml", _workbook_xml(workbook))
        archive.writestr("xl/_rels/workbook.xml.rels", _relationships(workbook))
        archive.writestr("xl/styles.xml", _styles())
        for index, sheet in enumerate(workbook.worksheets, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(sheet))
