from ms_data_quality.clean import scan
from ms_data_quality.detect import (
    company_key,
    detect_suspicious,
    find_company_clusters,
    fix_email,
)
from ms_data_quality.tableio import read_table


def _issues(sample_path, truth):
    header, rows = read_table(sample_path)
    return header, rows, scan(header, rows, truth["required"], None)


def test_detection_matches_every_planted_problem_with_no_extras(sample_path, truth):
    """Author-written sample: this checks the detectors work, not that they generalise."""
    _, _, issues = _issues(sample_path, truth)
    for kind in ("invalid_email", "missing_field", "suspicious_value"):
        found = {(i.row, i.column) for i in issues if i.kind == kind}
        planted = {(p["row"], p["column"]) for p in truth["problems"] if p["kind"] == kind}
        assert found == planted, kind


def test_duplicates_are_found_by_row(sample_path, truth):
    _, _, issues = _issues(sample_path, truth)
    found = {i.row for i in issues if i.kind == "duplicate_row"}
    planted = {p["row"] for p in truth["problems"] if p["kind"] == "duplicate_row"}
    assert found == planted


def test_clean_rows_are_never_flagged(sample_path, truth):
    _, _, issues = _issues(sample_path, truth)
    planted_rows = {p["row"] for p in truth["problems"]}
    cluster_rows = {r for c in truth["company_clusters"].values() for r in c["rows"]}
    unexpected = [i for i in issues if i.row not in planted_rows | cluster_rows]
    assert unexpected == []


def test_company_clusters_group_spelling_variants_only(sample_path, truth):
    header, rows, _ = _issues(sample_path, truth)
    clusters = find_company_clusters(header, rows, "company")
    found = sorted(sorted(c.rows) for c in clusters)
    expected = sorted(sorted(c["rows"]) for c in truth["company_clusters"].values())
    assert found == expected


def test_company_key_ignores_case_punctuation_legal_form_and_connectors():
    keys = {company_key(n) for n in ["Acme NV", "ACME", "acme", "Acme BVBA"]}
    assert len(keys) == 1
    assert company_key("Janssen & Zonen") == company_key("Janssen en Zonen")
    assert company_key("Orion Software") != company_key("Nordic Trade")


def test_fix_email():
    assert fix_email("marie@@orion.example") == "marie@orion.example"
    assert fix_email("wim@gmial.com") == "wim@gmail.com"
    assert fix_email(" Tom@Example.COM ") == "tom@example.com"
    assert fix_email("sofie.dewit.orion.example") is None
    assert fix_email("tom@orion") is None
    assert fix_email("pieter vermeulen@orion.example") is None


def test_suspicious_ignores_id_columns_and_text_columns():
    header = ["id", "note", "age"]
    rows = [[str(n), "x", "30"] for n in range(1, 10)] + [["1000000", "x", "31"]]
    assert detect_suspicious(header, rows) == []
    assert detect_suspicious(["note"], [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]]) == []
