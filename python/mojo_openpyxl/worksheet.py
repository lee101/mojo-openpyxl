from __future__ import annotations

from .cell import Cell
from .utils.cell import coordinate_to_tuple, range_boundaries

INVALID_TITLE_CHARS = set(r"\\*?:/[]")


class Worksheet:
    def __init__(self, parent, title: str = "Sheet"):
        self.parent = parent
        self._cells: dict[tuple[int, int], Cell] = {}
        self._max_row = 0
        self._max_column = 0
        self._title = ""
        self.title = title

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        if not isinstance(value, str) or not value:
            raise ValueError("Title must have at least one character")
        if any(char in INVALID_TITLE_CHARS for char in value):
            raise ValueError(f"Invalid character found in sheet title")
        if len(value) > 31:
            import warnings
            warnings.warn("Title is more than 31 characters. Some applications may not be able to read the file")
        if self.parent is not None:
            base, counter = value, 1
            names = {ws.title.lower() for ws in self.parent.worksheets if ws is not self}
            while value.lower() in names:
                value = f"{base}{counter}"
                counter += 1
        self._title = value

    def cell(self, row, column, value=None):
        if row < 1 or column < 1:
            raise ValueError("Row or column values must be at least 1")
        key = (int(row), int(column))
        cell = self._cells.get(key)
        if cell is None:
            cell = self._cells[key] = Cell(self, *key)
            self._max_row = max(self._max_row, key[0])
            self._max_column = max(self._max_column, key[1])
        if value is not None:
            cell.value = value
        return cell

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.cell(key, col) for col in range(1, self.max_column + 1))
        if ":" in key:
            min_col, min_row, max_col, max_row = range_boundaries(key)
            return tuple(
                tuple(self.cell(row, col) for col in range(min_col, max_col + 1))
                for row in range(min_row, max_row + 1)
            )
        row, col = coordinate_to_tuple(key)
        return self.cell(row, col)

    def __setitem__(self, key, value):
        self[key].value = value

    def append(self, iterable):
        row = self._max_row + 1 if self._cells else 1
        values = iterable.values() if isinstance(iterable, dict) else iterable
        if isinstance(iterable, dict):
            for column, value in iterable.items():
                if isinstance(column, str):
                    from .utils.cell import column_index_from_string
                    column = column_index_from_string(column)
                self.cell(row, column, value)
        else:
            for column, value in enumerate(values, 1):
                if value is not None:
                    self.cell(row, column, value)

    @property
    def max_row(self):
        return max(self._max_row, 1)

    @property
    def max_column(self):
        return max(self._max_column, 1)

    @property
    def min_row(self):
        return min((row for row, _ in self._cells), default=1)

    @property
    def min_column(self):
        return min((column for _, column in self._cells), default=1)

    def iter_rows(
        self, min_row=None, max_row=None, min_col=None, max_col=None, values_only=False
    ):
        if not self._cells and all(
            value is None for value in (min_row, max_row, min_col, max_col)
        ):
            return
        min_row = 1 if min_row is None else min_row
        max_row = self.max_row if max_row is None else max_row
        min_col = 1 if min_col is None else min_col
        max_col = self.max_column if max_col is None else max_col
        for row in range(min_row, max_row + 1):
            cells = tuple(self.cell(row, col) for col in range(min_col, max_col + 1))
            yield tuple(cell.value for cell in cells) if values_only else cells

    def iter_cols(
        self, min_col=None, max_col=None, min_row=None, max_row=None, values_only=False
    ):
        if not self._cells and all(
            value is None for value in (min_col, max_col, min_row, max_row)
        ):
            return
        min_col = 1 if min_col is None else min_col
        max_col = self.max_column if max_col is None else max_col
        min_row = 1 if min_row is None else min_row
        max_row = self.max_row if max_row is None else max_row
        for col in range(min_col, max_col + 1):
            cells = tuple(self.cell(row, col) for row in range(min_row, max_row + 1))
            yield tuple(cell.value for cell in cells) if values_only else cells

    @property
    def rows(self):
        return self.iter_rows()

    @property
    def columns(self):
        return self.iter_cols()

    @property
    def values(self):
        return self.iter_rows(values_only=True)

    def _stored_cells(self):
        return [
            cell for _, cell in sorted(self._cells.items())
            if cell.value is not None
        ]
