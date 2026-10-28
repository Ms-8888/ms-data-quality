from ms_data_quality.clean import apply, proposals, review, scan
from ms_data_quality.cli import main
from ms_data_quality.detect import Issue
from ms_data_quality.tableio import read_table


def _setup(sample_path, truth):
    header, rows = read_table(sample_path)
    return header, rows, scan(header, rows, truth["required"], None)


def test_identical_changes_are_asked_once_and_flags_are_never_proposed():
    same = [
        Issue("company_variant", n, "company", "acme", "m", "replace", "Acme NV", "rules")
        for n in (1, 5, 9)
    ]
    other = Issue("company_variant", 2, "company", "ACME", "m", "replace", "Acme NV", "rules")
    flag = Issue("missing_field", 3, "email", "", "empty")
    drops = [Issue("duplicate_row", n, None, "", "dup", "drop_row") for n in (7, 8)]
    items = proposals(same + [other, flag] + drops)
    assert [len(i.issues) for i in items] == [3, 1, 1, 1]
    assert all(i.action != "flag" for i in items)


def test_review_modes():
    class P:
        accepted = None

    items = [P(), P(), P(), P()]
    answers = iter(["y", "n", "a", "n"])
    review(items, lambda item: next(answers))
    assert [i.accepted for i in items] == [True, False, True, True]
    items = [P(), P(), P()]
    answers = iter(["y", "q", "y"])
    review(items, lambda item: next(answers))
    assert [i.accepted for i in items] == [True, False, False]


def test_only_accepted_proposals_change_the_data(sample_path, truth):
    header, rows, issues = _setup(sample_path, truth)
    items = proposals(issues)
    review(items, lambda item: "n")
    same, changed, dropped = apply(header, rows, items)
    assert same == rows
    assert (changed, dropped) == (0, 0)
    review(items, lambda item: "y")
    cleaned, changed, dropped = apply(header, rows, items)
    assert dropped == 3
    assert len(cleaned) == len(rows) - 3
    assert changed >= 8


def test_cli_scan_changes_nothing_and_reports(sample_path, capsys):
    before = sample_path.read_bytes()
    assert main(["scan", str(sample_path), "--required", "name,email,company"]) == 0
    assert "23 problems found" in capsys.readouterr().out
    assert sample_path.read_bytes() == before


def test_cli_clean_yes_writes_cleaned_file_and_report(sample_path, tmp_path):
    out, report = tmp_path / "out.csv", tmp_path / "r.md"
    args = ["clean", str(sample_path), "--required", "name,email,company", "--yes"]
    assert main(args + ["--out", str(out), "--report", str(report)]) == 0
    header, rows = read_table(out)
    assert len(rows) == 37
    emails = [r[header.index("email")] for r in rows]
    assert "wim.aerts@gmail.com" in emails
    assert "marie@orion.example" in emails
    text = report.read_text(encoding="utf-8")
    assert "## Accepted changes" in text
    assert "## Needs a human" in text
    assert "sofie.dewit.orion.example" in text  # flagged, not silently changed


def test_cli_interactive_decline_keeps_every_value(sample_path, tmp_path, monkeypatch):
    out = tmp_path / "out.csv"
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    args = ["clean", str(sample_path), "--out", str(out), "--report", str(tmp_path / "r.md")]
    assert main(args) == 0
    assert read_table(out)[1] == read_table(sample_path)[1]


def test_cli_refuses_to_overwrite_the_input(sample_path, capsys):
    assert main(["clean", str(sample_path), "--yes", "--out", str(sample_path)]) == 2
    assert "refusing" in capsys.readouterr().err


def test_cli_rejects_unknown_required_column_and_bad_file(sample_path, tmp_path, capsys):
    assert main(["scan", str(sample_path), "--required", "nope"]) == 2
    assert "not in the file" in capsys.readouterr().err
    assert main(["scan", str(tmp_path / "x.txt")]) == 2


def test_missing_key_is_a_clean_error_not_a_crash(sample_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["scan", str(sample_path), "--backend", "anthropic"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
