import argparse
import sys
from pathlib import Path

from ms_data_quality.clean import Proposal, apply, proposals, review, scan
from ms_data_quality.report import change_report, scan_summary
from ms_data_quality.suggest import BACKENDS, get_backend
from ms_data_quality.tableio import TableError, read_table, write_table


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", type=Path, help="CSV or XLSX file")
    parser.add_argument(
        "--required", default="", help="comma-separated columns that must not be empty"
    )
    parser.add_argument("--backend", choices=BACKENDS, default="rules")


def _describe(item: Proposal) -> str:
    rows = ", ".join(str(i.row) for i in item.issues)
    if item.action == "drop_row":
        return f"Remove row {rows}: {item.issues[0].message}"
    return f"Change '{item.before}' -> '{item.after}' ({item.kind}, rows {rows})"


def _ask(item: Proposal) -> str:
    return input(
        f"{_describe(item)}\n  Apply? [y]es / [n]o / [a]ccept all / [q]uit and reject rest: "
    )


def _auto_yes(item: Proposal) -> str:
    print(f"{_describe(item)}\n  Applied (--yes)")
    return "y"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dq", description="Find and fix data quality problems.")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_parser = sub.add_parser("scan", help="report problems, change nothing")
    _common(scan_parser)
    clean_parser = sub.add_parser(
        "clean", help="propose fixes, ask for approval, write a cleaned file"
    )
    _common(clean_parser)
    clean_parser.add_argument(
        "--out", type=Path, help="cleaned file (default: <name>.cleaned.<ext>)"
    )
    clean_parser.add_argument(
        "--report", type=Path, help="change report (default: <name>.changes.md)"
    )
    clean_parser.add_argument(
        "--yes", action="store_true", help="apply every proposal without asking"
    )
    args = parser.parse_args(argv)

    required = [c.strip() for c in args.required.split(",") if c.strip()]
    try:
        header, rows = read_table(args.path)
        missing = [c for c in required if c not in header]
        if missing:
            raise TableError(f"Required column(s) not in the file: {', '.join(missing)}")
        backend = get_backend(args.backend)
    except (TableError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    issues = scan(header, rows, required, backend)
    if args.command == "scan":
        print(scan_summary(issues))
        return 0

    out = args.out or args.path.with_name(f"{args.path.stem}.cleaned{args.path.suffix}")
    report = args.report or args.path.with_name(f"{args.path.stem}.changes.md")
    if out.resolve() == args.path.resolve() or report.resolve() == args.path.resolve():
        print("Error: refusing to overwrite the input file.", file=sys.stderr)
        return 2

    items = proposals(issues)
    review(items, _auto_yes if args.yes else _ask)
    new_rows, changed, dropped = apply(header, rows, items)
    neutralised = write_table(out, header, new_rows)
    report.write_text(
        change_report(
            args.path.name, issues, items, len(rows), len(new_rows), args.backend, neutralised
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out} ({changed} values changed, {dropped} rows removed) and {report}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
