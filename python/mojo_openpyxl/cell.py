from __future__ import annotations

import datetime as dt
import math
import numbers
import re

from .utils.cell import get_column_letter
from .utils.exceptions import IllegalCharacterError

_ILLEGAL = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")
ERROR_CODES = {
    "#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A", "#GETTING_DATA",
}


class Cell:
    __slots__ = ("parent", "row", "column", "_value")

    def __init__(self, worksheet, row: int, column: int, value=None):
        self.parent = worksheet
        self.row = row
        self.column = column
        self._value = None
        if value is not None:
            self.value = value

    @property
    def coordinate(self) -> str:
        return f"{get_column_letter(self.column)}{self.row}"

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if isinstance(value, str):
            if _ILLEGAL.search(value):
                raise IllegalCharacterError(f"{value} cannot be used in worksheets.")
            value = value[:32767]
        elif value is not None and not isinstance(
            value, (numbers.Number, bool, dt.datetime, dt.date, dt.time)
        ):
            raise ValueError(f"Cannot convert {value!r} to Excel")
        self._value = value

    @property
    def data_type(self) -> str:
        value = self._value
        if value is None:
            return "n"
        if isinstance(value, bool):
            return "b"
        if isinstance(value, str):
            if value.startswith("="):
                return "f"
            if value in ERROR_CODES:
                return "e"
            return "s"
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return "d"
        return "n"

    def _encoded(self) -> tuple[int, bytes]:
        value = self._value
        data_type = self.data_type
        if data_type == "s":
            return 1, value.encode("utf-8")
        if data_type == "n":
            if isinstance(value, float):
                raw = "" if not math.isfinite(value) else repr(value)
            else:
                raw = str(value)
            return 2, raw.encode("ascii")
        if data_type == "b":
            return 3, b"1" if value else b"0"
        if data_type == "f":
            return 4, value[1:].encode("utf-8")
        if data_type == "d":
            return 5, value.isoformat().encode("ascii")
        return 6, value.encode("ascii")

    def __repr__(self):
        return f"<Cell {self.parent.title}.{self.coordinate}>"
