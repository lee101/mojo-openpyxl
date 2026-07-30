from __future__ import annotations

import re

from .exceptions import CellCoordinatesException

_COORD = re.compile(r"^\$?([A-Za-z]{1,3})\$?([0-9]+)$")
_RANGE = re.compile(
    r"^\$?([A-Za-z]{1,3})?\$?([0-9]+)?"
    r"(?::\$?([A-Za-z]{1,3})?\$?([0-9]+)?)?$"
)
_SHEET_RANGE = re.compile(r"^(?:'((?:[^']|'')*)'|([^!]+))!(.+)$")


def get_column_letter(col_idx):
    if not isinstance(col_idx, int) or not 1 <= col_idx <= 18278:
        raise ValueError(f"Invalid column index {col_idx}")
    result = []
    while col_idx:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def column_index_from_string(col):
    if len(col) > 3 or not col.isalpha():
        raise ValueError(
            f"{col!r} is not a valid column name. Column names are from A to ZZZ"
        )
    value = 0
    for char in col.upper():
        value = value * 26 + ord(char) - 64
    if not 1 <= value <= 18278:
        raise ValueError(
            f"{col!r} is not a valid column name. Column names are from A to ZZZ"
        )
    return value


def coordinate_from_string(coord_string):
    match = _COORD.match(coord_string)
    if not match:
        raise CellCoordinatesException(f"Invalid cell coordinates ({coord_string})")
    column, row = match.groups()
    row = int(row)
    if row == 0:
        raise CellCoordinatesException("There is no row 0 (A0 is not a valid coordinate)")
    return column, row


def coordinate_to_tuple(coordinate):
    for index, char in enumerate(coordinate):
        if char.isdigit():
            return int(coordinate[index:]), column_index_from_string(coordinate[:index])
    raise ValueError(f"{coordinate} is not a valid coordinate")


def range_boundaries(range_string):
    match = _RANGE.match(range_string)
    if not match:
        raise ValueError(f"{range_string} is not a valid coordinate or range")
    min_col, min_row, max_col, max_row = match.groups()
    if max_col is None and max_row is None:
        max_col, max_row = min_col, min_row
    if (min_col is None) != (max_col is None) or (min_row is None) != (max_row is None):
        raise ValueError(f"{range_string} is not a valid coordinate or range")
    return (
        column_index_from_string(min_col) if min_col else None,
        int(min_row) if min_row else None,
        column_index_from_string(max_col) if max_col else None,
        int(max_row) if max_row else None,
    )


def range_to_tuple(range_string):
    match = _SHEET_RANGE.match(range_string)
    if not match:
        raise ValueError("Value must be of the form sheetname!A1:E4")
    quoted, plain, cells = match.groups()
    title = quoted if quoted is not None else plain
    return title, range_boundaries(cells)


def absolute_coordinate(coord_string):
    if not _RANGE.match(coord_string):
        raise ValueError(f"{coord_string} is not a valid coordinate range")
    pieces = []
    for part in coord_string.split(":"):
        match = re.match(r"^\$?([A-Za-z]{1,3})?\$?([0-9]+)?$", part)
        if not match:
            raise ValueError(f"{coord_string} is not a valid coordinate range")
        col, row = match.groups()
        pieces.append(("$" + col.upper() if col else "") + ("$" + row if row else ""))
    return ":".join(pieces)


def rows_from_range(range_string):
    min_col, min_row, max_col, max_row = range_boundaries(range_string)
    for row in range(min_row, max_row + 1):
        yield tuple(f"{get_column_letter(col)}{row}" for col in range(min_col, max_col + 1))


def cols_from_range(range_string):
    min_col, min_row, max_col, max_row = range_boundaries(range_string)
    for col in range(min_col, max_col + 1):
        letter = get_column_letter(col)
        yield tuple(f"{letter}{row}" for row in range(min_row, max_row + 1))
