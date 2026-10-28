from collections import Counter

from ms_data_quality.clean import Proposal
from ms_data_quality.detect import Issue

TITLES = {
    "invalid_email": "Invalid emails",
    "missing_field": "Missing required fields",
    "duplicate_row": "Duplicate rows",
    "company_variant": "Company name variants",
    "suspicious_value": "Suspicious values",
}


_MARKDOWN_SPECIAL = str.maketrans(
    {
        "\\": "\\\\",
        "|": "\\|",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "<": "&lt;",
        ">": "&gt;",
        "\n": " ",
        "\r": " ",
    }
)


def _cell(text: str | None) -> str:
    """Escape user data so it cannot become a link, HTML or formatting in the report."""
    return (text or "").translate(_MARKDOWN_SPECIAL)


def scan_summary(issues: list[Issue]) -> str:
    if not issues:
        return "No problems found."
    counts = Counter(i.kind for i in issues)
    lines = [f"{len(issues)} problems found:"]
    lines += [f"  {TITLES[kind]}: {count}" for kind, count in sorted(counts.items())]
    lines.append("")
    for issue in issues:
        where = f"row {issue.row}" + (f", {issue.column}" if issue.column else "")
        fix = f"  ->  {issue.suggestion}" if issue.suggestion else ""
        value = f" '{issue.value}'" if issue.value else ""
        lines.append(f"  [{TITLES[issue.kind]}] {where}:{value} {issue.message}{fix}")
    return "\n".join(lines)


def change_report(
    source: str,
    issues: list[Issue],
    items: list[Proposal],
    rows_in: int,
    rows_out: int,
    backend: str,
    neutralised: int = 0,
) -> str:
    accepted = [i for i in items if i.accepted]
    rejected = [i for i in items if i.accepted is False]
    flagged = [i for i in issues if i.action == "flag"]
    out = [
        f"# Change report for {source}",
        "",
        f"- Rows in: {rows_in}, rows out: {rows_out}",
        f"- Problems found: {len(issues)}",
        f"- Changes accepted: {len(accepted)}, rejected: {len(rejected)}",
        f"- Left for a human (no safe automatic fix): {len(flagged)}",
        f"- Suggestion backend: {backend}",
        f"- Cells prefixed with ' on export so they cannot run as formulas: {neutralised}",
        "",
        "## Accepted changes",
        "",
    ]
    out += _change_table(accepted) or ["None."]
    out += ["", "## Rejected changes", ""]
    out += _change_table(rejected) or ["None."]
    out += ["", "## Needs a human", ""]
    if flagged:
        out += ["| Row | Column | Value | Problem |", "|---|---|---|---|"]
        out += [
            f"| {i.row} | {_cell(i.column)} | {_cell(i.value)} | {_cell(i.message)} |"
            for i in flagged
        ]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


def _change_table(items: list[Proposal]) -> list[str]:
    if not items:
        return []
    lines = ["| Rows | Type | Before | After | Source |", "|---|---|---|---|---|"]
    for item in items:
        rows = ", ".join(str(i.row) for i in item.issues)
        after = "(row removed)" if item.action == "drop_row" else _cell(item.after)
        before = _cell(item.before) or _cell(item.issues[0].message)
        source = item.issues[0].source or "rules"
        lines.append(f"| {rows} | {_cell(item.kind)} | {before} | {after} | {source} |")
    return lines
