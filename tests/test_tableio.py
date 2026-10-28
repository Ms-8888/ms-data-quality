import pytest
from openpyxl import load_workbook

from ms_data_quality import tableio
from ms_data_quality.tableio import TableError, read_table, sanitize_cell, write_table


def test_csv_read_pads_short_rows(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("a,b,c\n1,2\n4,5,6\n", encoding="utf-8")
    header, rows = read_table(path)
    assert header == ["a", "b", "c"]
    assert rows == [["1", "2", ""], ["4", "5", "6"]]


def test_semicolon_csv_is_detected(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("naam;stad\nAn;Gent\nBo;Brugge\n", encoding="utf-8")
    assert read_table(path)[1] == [["An", "Gent"], ["Bo", "Brugge"]]


def test_xlsx_roundtrip(tmp_path):
    path = tmp_path / "a.xlsx"
    write_table(path, ["naam", "leeftijd"], [["An", "30"], ["Bo", ""]])
    header, rows = read_table(path)
    assert header == ["naam", "leeftijd"]
    assert rows == [["An", "30"], ["Bo", ""]]


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-cmd", "@SUM(A1)", "\tx"])
def test_formula_starts_are_neutralised(value):
    assert sanitize_cell(value).startswith("'")


@pytest.mark.parametrize("value", ["-5000", "12", "3.5", "Acme", ""])
def test_normal_values_are_left_alone(value):
    assert sanitize_cell(value) == value


def test_exported_xlsx_never_contains_a_live_formula(tmp_path):
    path = tmp_path / "a.xlsx"
    write_table(path, ["x"], [['=HYPERLINK("http://evil.example","click")']])
    cell = load_workbook(path).worksheets[0]["A2"]
    assert cell.data_type != "f"


def test_exported_csv_neutralises_formulas(tmp_path):
    path = tmp_path / "a.csv"
    write_table(path, ["x"], [["=1+1"], ["-5"]])
    assert path.read_text(encoding="utf-8").splitlines() == ["x", "'=1+1", "-5"]


def test_unsupported_missing_empty_and_oversized_files_are_refused(tmp_path, monkeypatch):
    with pytest.raises(TableError, match="Unsupported"):
        read_table(tmp_path / "a.txt")
    with pytest.raises(TableError, match="not found"):
        read_table(tmp_path / "missing.csv")
    empty = tmp_path / "e.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(TableError, match="empty"):
        read_table(empty)
    big = tmp_path / "b.csv"
    big.write_text("a\n1\n2\n3\n", encoding="utf-8")
    monkeypatch.setattr(tableio, "MAX_ROWS", 2)
    with pytest.raises(TableError, match="Too many rows"):
        read_table(big)
