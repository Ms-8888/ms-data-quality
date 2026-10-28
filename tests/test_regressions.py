"""Cases found by an independent code review of the first release."""

import pytest
from openpyxl import load_workbook

from ms_data_quality.clean import Proposal, apply, scan
from ms_data_quality.detect import (
    Issue,
    detect_duplicates,
    detect_suspicious,
    find_company_clusters,
    fix_email,
)
from ms_data_quality.report import change_report
from ms_data_quality.tableio import TableError, read_table, write_table


def clusters_for(names: list[str]) -> list[list[str]]:
    rows = [[n] for n in names]
    found = find_company_clusters(["company"], rows, "company")
    return sorted(sorted(c.variants) for c in found)


def test_numbered_company_names_are_never_merged():
    assert clusters_for(["Vision 2000", "Vision 2001", "Vision 2002"]) == []


def test_similar_but_different_place_names_are_not_merged():
    assert clusters_for(["Stad Gent", "Stad Genk"]) == []


def test_chains_of_similar_names_do_not_merge_the_ends():
    names = ["Acme Systems", "Acme Systemz", "Acme Systemzz", "Acme Systemzzz"]
    for group in clusters_for(names):
        assert not ({"Acme Systems", "Acme Systemzzz"} <= set(group))


def test_names_made_only_of_legal_forms_are_not_collapsed_together():
    assert clusters_for(["NV", "BV", "SA", "Inc"]) == []


def test_non_latin_names_are_not_collapsed_together():
    assert clusters_for(["Газпром", "Лукойл", "東京商事", "大阪物産"]) == []


def test_real_spelling_variants_still_merge():
    assert clusters_for(["Acme NV", "ACME N.V.", "acme"]) == [["ACME N.V.", "Acme NV", "acme"]]
    assert clusters_for(["Delta Logistics", "Delta Logistiks"]) != []


def test_multiline_quoted_cell_survives(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text('name,note\nAn,"line1\nline2"\nBo,ok\n', encoding="utf-8")
    assert read_table(path)[1] == [["An", "line1\nline2"], ["Bo", "ok"]]


def test_unicode_line_separators_do_not_split_records(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("name,note\nAn,a b\nBo,ok\n", encoding="utf-8")
    assert read_table(path)[1] == [["An", "a b"], ["Bo", "ok"]]


def test_blank_lines_are_not_rows(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("name,city\nAn,Gent\n\n\nBo,Brugge\n", encoding="utf-8")
    assert read_table(path)[1] == [["An", "Gent"], ["Bo", "Brugge"]]


def test_a_row_wider_than_the_header_is_refused_not_truncated(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("a,b,c\n1,2,3\n4,5,6,EXTRA\n", encoding="utf-8")
    with pytest.raises(TableError, match="row 2"):
        read_table(path)


def test_broken_files_give_a_clean_error(tmp_path):
    bad_xlsx = tmp_path / "a.xlsx"
    bad_xlsx.write_bytes(b"not a zip file")
    with pytest.raises(TableError):
        read_table(bad_xlsx)
    huge_field = tmp_path / "b.csv"
    huge_field.write_text("a\n" + "x" * 200_000 + "\n", encoding="utf-8")
    with pytest.raises(TableError):
        read_table(huge_field)


def test_column_hints_match_whole_words_only():
    rows = [[str(v)] for v in (200, 250, 300, 350, 400)] + [["-1"]]
    assert detect_suspicious(["page_views"], rows) == []
    assert detect_suspicious(["average"], rows) == []
    assert detect_suspicious(["revenue"], rows) != []


def test_comma_decimals_are_understood_and_non_finite_values_ignored():
    rows = [[v] for v in ("1,5", "2,0", "2,5", "3,0", "2,2", "100000,0")]
    assert [i.row for i in detect_suspicious(["score"], rows)] == [6]
    rows = [["nan"]] + [[str(v)] for v in (1, 2, 3, 4, 5, 6, 7, 8)] + [["9000"]]
    assert [i.row for i in detect_suspicious(["score"], rows)] == [10]


def test_same_email_with_a_different_name_is_flagged_not_dropped():
    header = ["name", "email"]
    rows = [["Ann Peeters", "info@acme.example"], ["Bob Janssens", "info@acme.example"]]
    issues = detect_duplicates(header, rows, "email")
    assert [(i.row, i.action) for i in issues] == [(2, "flag")]


def test_same_email_and_same_name_is_still_a_drop():
    header = ["name", "email"]
    rows = [["Ann Peeters", "ann@x.example"], ["ANN PEETERS", "ann@x.example"]]
    assert [(i.row, i.action) for i in detect_duplicates(header, rows, "email")] == [
        (2, "drop_row")
    ]


def test_fix_email_never_suggests_an_invalid_address():
    assert fix_email("A..B@x.com") is None


def test_replacement_on_a_dropped_row_is_not_counted():
    header, rows = ["name"], [["a"], ["b"]]
    replace = Proposal(
        "x", "replace", "b", "B", [Issue("x", 2, "name", "b", "m", "replace", "B")], True
    )
    drop = Proposal("duplicate_row", "drop_row", "", None, [Issue("d", 2, None, "", "m")], True)
    kept, changed, dropped = apply(header, rows, [replace, drop])
    assert kept == [["a"]]
    assert (changed, dropped) == (0, 1)


def test_phone_numbers_are_not_rewritten_on_export(tmp_path):
    path = tmp_path / "a.csv"
    write_table(path, ["tel"], [["+31 6 12345678"], ["-"], ["=1+1"], ["@x"]])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["tel", "+31 6 12345678", "-", "'=1+1", "'@x"]


def test_xlsx_formula_like_text_is_a_plain_string_without_a_visible_apostrophe(tmp_path):
    path = tmp_path / "a.xlsx"
    write_table(path, ["x"], [["=1+1"], ["+31 6 12345678"]])
    sheet = load_workbook(path).worksheets[0]
    assert sheet["A2"].value == "=1+1"
    assert sheet["A2"].data_type == "s"
    assert sheet["A3"].value == "+31 6 12345678"


def test_write_reports_how_many_cells_were_neutralised(tmp_path):
    assert write_table(tmp_path / "a.csv", ["x"], [["=1"], ["ok"], ["@y"]]) == 2
    assert write_table(tmp_path / "a.xlsx", ["x"], [["=1"], ["ok"]]) == 1


def test_markdown_in_cells_cannot_inject_links_or_html():
    issue = Issue("invalid_email", 1, "email", "[x](http://evil.example) <b>hi</b>", "bad")
    report = change_report("f.csv", [issue], [], 1, 1, "rules")
    assert "<b>" not in report
    assert "](http://evil.example)" not in report


def test_scan_finds_nothing_in_a_table_without_problems():
    header = ["name", "email", "company"]
    rows = [["An Peeters", "an@acme.example", "Acme NV"], ["Bo Claes", "bo@delta.example", "Delta"]]
    assert scan(header, rows, ["name", "email", "company"], None) == []
