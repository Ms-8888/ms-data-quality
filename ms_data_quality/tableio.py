import csv
from pathlib import Path

from openpyxl import Workbook, load_workbook

MAX_ROWS = 100_000
SUPPORTED = {".csv", ".xlsx"}
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


class TableError(Exception):
    """Raised for input the tool refuses to process."""


def _check_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise TableError(f"Unsupported file type '{path.suffix}'. Use .csv or .xlsx.")
    return suffix


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    suffix = _check_suffix(path)
    if not path.is_file():
        raise TableError(f"File not found: {path}")
    if suffix == ".csv":
        raw = path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        records = list(csv.reader(raw.splitlines(), dialect))
    else:
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        records = [
            ["" if v is None else str(v) for v in row] for row in sheet.iter_rows(values_only=True)
        ]
        workbook.close()
    if not records:
        raise TableError("The file is empty.")
    header, rows = [h.strip() for h in records[0]], records[1:]
    if len(rows) > MAX_ROWS:
        raise TableError(f"Too many rows ({len(rows)}); the limit is {MAX_ROWS}.")
    width = len(header)
    return header, [(row + [""] * width)[:width] for row in rows]


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def sanitize_cell(value: str) -> str:
    """Stop spreadsheet programs from running a cell as a formula (CSV/formula injection)."""
    if value.startswith(_FORMULA_STARTS) and not _is_number(value):
        return "'" + value
    return value


def write_table(path: Path, header: list[str], rows: list[list[str]]) -> None:
    suffix = _check_suffix(path)
    safe_header = [sanitize_cell(h) for h in header]
    safe_rows = [[sanitize_cell(cell) for cell in row] for row in rows]
    if suffix == ".csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(safe_header)
            writer.writerows(safe_rows)
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(safe_header)
        for row in safe_rows:
            sheet.append(row)
        workbook.save(path)
