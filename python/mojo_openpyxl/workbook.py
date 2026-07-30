from __future__ import annotations

from .worksheet import Worksheet


class Workbook:
    def __init__(self, write_only=False, iso_dates=False):
        self.write_only = write_only
        self.iso_dates = iso_dates
        self._sheets: list[Worksheet] = []
        self._active_sheet_index = 0
        self.epoch = "1900"
        if not write_only:
            self.create_sheet()

    @property
    def worksheets(self):
        return list(self._sheets)

    @property
    def sheetnames(self):
        return [sheet.title for sheet in self._sheets]

    @property
    def active(self):
        if not self._sheets:
            return None
        return self._sheets[self._active_sheet_index]

    @active.setter
    def active(self, value):
        if isinstance(value, Worksheet):
            if value not in self._sheets:
                raise ValueError("Worksheet is not in this workbook")
            value = self._sheets.index(value)
        if not isinstance(value, int) or not 0 <= value < len(self._sheets):
            raise IndexError("At least one sheet must be visible")
        self._active_sheet_index = value

    def create_sheet(self, title=None, index=None):
        title = title or "Sheet"
        sheet = Worksheet(self, title)
        if index is None:
            self._sheets.append(sheet)
        else:
            self._sheets.insert(index, sheet)
        return sheet

    def remove(self, worksheet):
        index = self._sheets.index(worksheet)
        self._sheets.remove(worksheet)
        if self._sheets:
            self._active_sheet_index = min(self._active_sheet_index, len(self._sheets) - 1)
        elif index == 0:
            self._active_sheet_index = 0

    def remove_sheet(self, worksheet):
        return self.remove(worksheet)

    def move_sheet(self, sheet, offset=0):
        if isinstance(sheet, str):
            sheet = self[sheet]
        old = self._sheets.index(sheet)
        self._sheets.pop(old)
        self._sheets.insert(max(0, min(old + offset, len(self._sheets))), sheet)

    def __getitem__(self, key):
        for sheet in self._sheets:
            if sheet.title == key:
                return sheet
        raise KeyError(f"Worksheet {key} does not exist.")

    def __iter__(self):
        return iter(self._sheets)

    def get_sheet_by_name(self, name):
        return self[name]

    def index(self, worksheet):
        return self._sheets.index(worksheet)

    def save(self, filename):
        from .writer import save_workbook
        save_workbook(self, filename)

    def close(self):
        pass
