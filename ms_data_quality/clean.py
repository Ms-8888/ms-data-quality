from collections.abc import Callable
from dataclasses import dataclass

from ms_data_quality.detect import (
    Issue,
    detect_duplicates,
    detect_invalid_emails,
    detect_missing,
    detect_suspicious,
    find_column,
    find_company_clusters,
)
from ms_data_quality.suggest import Backend, choose_canonical

EMAIL_NAMES = ("email", "e-mail", "mail", "emailadres")
COMPANY_NAMES = ("company", "bedrijf", "organisation", "organization", "bedrijfsnaam")


@dataclass
class Proposal:
    """One change the user is asked to approve (may cover several rows)."""

    kind: str
    action: str
    before: str
    after: str | None
    issues: list[Issue]
    accepted: bool | None = None  # None = not decided


def scan(
    header: list[str],
    rows: list[list[str]],
    required: list[str],
    backend: Backend | None,
) -> list[Issue]:
    email = find_column(header, EMAIL_NAMES)
    company = find_column(header, COMPANY_NAMES)
    issues: list[Issue] = []
    if email:
        issues += detect_invalid_emails(header, rows, email)
    issues += detect_missing(header, rows, [c for c in required if c in header])
    issues += detect_duplicates(header, rows, email)
    if company:
        col = header.index(company)
        for cluster in find_company_clusters(header, rows, company):
            canonical, source = choose_canonical(cluster.variants, backend)
            for number in sorted(cluster.rows):
                current = rows[number - 1][col].strip()
                if current != canonical:
                    issues.append(
                        Issue(
                            "company_variant",
                            number,
                            company,
                            current,
                            f"Spelling differs from '{canonical}'",
                            "replace",
                            canonical,
                            source,
                        )
                    )
    issues += detect_suspicious(header, rows)
    return sorted(issues, key=lambda i: (i.row, i.kind))


def proposals(issues: list[Issue]) -> list[Proposal]:
    """Group actionable issues so identical changes are asked once."""
    grouped: dict[tuple, Proposal] = {}
    for issue in issues:
        if issue.action == "flag":
            continue
        key = (issue.kind, issue.action, issue.column, issue.value, issue.suggestion)
        if issue.action == "drop_row":
            key = (issue.kind, issue.action, issue.row)
        if key not in grouped:
            grouped[key] = Proposal(issue.kind, issue.action, issue.value, issue.suggestion, [])
        grouped[key].issues.append(issue)
    return list(grouped.values())


def review(items: list[Proposal], ask: Callable[[Proposal], str]) -> None:
    """ask returns y, n, a (accept this and all remaining) or q (reject this and all remaining)."""
    mode = None
    for item in items:
        if mode == "a":
            item.accepted = True
        elif mode == "q":
            item.accepted = False
        else:
            answer = ask(item).strip().lower()[:1]
            if answer in ("a", "q"):
                mode = answer
            item.accepted = answer in ("y", "a")


def apply(
    header: list[str], rows: list[list[str]], items: list[Proposal]
) -> tuple[list[list[str]], int, int]:
    """Return (new rows, values changed, rows dropped) using only accepted proposals."""
    new_rows = [list(row) for row in rows]
    drop: set[int] = set()
    changed = 0
    for item in items:
        if not item.accepted:
            continue
        for issue in item.issues:
            if item.action == "replace" and issue.column and item.after is not None:
                new_rows[issue.row - 1][header.index(issue.column)] = item.after
                changed += 1
            elif item.action == "drop_row":
                drop.add(issue.row)
    kept = [row for number, row in enumerate(new_rows, start=1) if number not in drop]
    return kept, changed, len(drop)
