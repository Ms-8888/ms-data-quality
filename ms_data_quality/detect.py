import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

EMAIL_RE = re.compile(r"^[^@\s]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")
TYPO_DOMAINS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gamil.com": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotnail.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "yaho.com": "yahoo.com",
}
LEGAL_FORMS = {
    "nv",
    "bv",
    "bvba",
    "cvba",
    "sa",
    "sprl",
    "gmbh",
    "ag",
    "ltd",
    "llc",
    "inc",
    "plc",
    "vof",
}
STOPWORDS = {"en", "and", "et", "und"}
NON_NEGATIVE_HINTS = (
    "age",
    "leeftijd",
    "quantity",
    "aantal",
    "amount",
    "price",
    "prijs",
    "revenue",
    "omzet",
    "salary",
    "loon",
    "count",
)
AGE_HINTS = ("age", "leeftijd")
FUZZY_THRESHOLD = 0.92
NAME_COLUMNS = ("name", "naam", "full_name", "fullname")


@dataclass
class Issue:
    kind: str  # invalid_email | missing_field | duplicate_row | company_variant | suspicious_value
    row: int  # 1-based data row (header not counted)
    column: str | None
    value: str
    message: str
    action: str = "flag"  # flag | replace | drop_row
    suggestion: str | None = None
    source: str | None = None  # rules | model | rules-fallback


@dataclass
class Cluster:
    rows: list[int] = field(default_factory=list)
    variants: Counter = field(default_factory=Counter)


def find_column(header: list[str], names: tuple[str, ...]) -> str | None:
    lowered = {h.lower(): h for h in header}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def _index(header: list[str], column: str) -> int:
    return header.index(column)


def fix_email(value: str) -> str | None:
    candidate = re.sub(r"@+", "@", value.strip().lower())
    local, _, domain = candidate.partition("@")
    candidate = f"{local}@{TYPO_DOMAINS.get(domain, domain)}"
    valid = EMAIL_RE.match(candidate) and ".." not in candidate
    return candidate if valid and candidate != value else None


def detect_invalid_emails(header: list[str], rows: list[list[str]], column: str) -> list[Issue]:
    col, issues = _index(header, column), []
    for number, row in enumerate(rows, start=1):
        value = row[col].strip()
        domain = value.rpartition("@")[2].lower()
        if not value or (
            EMAIL_RE.match(value) and ".." not in value and domain not in TYPO_DOMAINS
        ):
            continue
        fixed = fix_email(value)
        message = (
            "Known typo in the domain" if domain in TYPO_DOMAINS else "Not a valid email address"
        )
        issues.append(
            Issue(
                "invalid_email",
                number,
                column,
                row[col],
                message,
                "replace" if fixed else "flag",
                fixed,
                "rules" if fixed else None,
            )
        )
    return issues


def detect_missing(header: list[str], rows: list[list[str]], required: list[str]) -> list[Issue]:
    issues = []
    for column in required:
        col = _index(header, column)
        for number, row in enumerate(rows, start=1):
            if not row[col].strip():
                issues.append(
                    Issue(
                        "missing_field", number, column, "", f"Required field '{column}' is empty"
                    )
                )
    return issues


def detect_duplicates(
    header: list[str], rows: list[list[str]], email_column: str | None
) -> list[Issue]:
    issues, seen_rows, seen_emails = [], {}, {}
    email_col = _index(header, email_column) if email_column else None
    name_column = find_column(header, NAME_COLUMNS)
    name_col = _index(header, name_column) if name_column else None
    compared = [
        i
        for i, name in enumerate(header)
        if name.lower() != "id" and not name.lower().endswith("_id")
    ]
    for number, row in enumerate(rows, start=1):
        exact = tuple(row[i].strip() for i in compared)
        if exact in seen_rows:
            issues.append(
                Issue(
                    "duplicate_row",
                    number,
                    None,
                    "",
                    f"Identical to row {seen_rows[exact]} (ignoring id columns)",
                    "drop_row",
                )
            )
            continue
        seen_rows[exact] = number
        if email_col is not None and row[email_col].strip():
            key = row[email_col].strip().lower()
            if key in seen_emails:
                first = seen_emails[key]
                same_person = name_col is not None and _same_name(
                    row[name_col], rows[first - 1][name_col]
                )
                issues.append(
                    Issue(
                        "duplicate_row",
                        number,
                        email_column,
                        row[email_col],
                        f"Same email as row {first}"
                        + ("" if same_person else " but not clearly the same person"),
                        "drop_row" if same_person else "flag",
                    )
                )
                continue
            seen_emails[key] = number
    return issues


def _same_name(first: str, second: str) -> bool:
    return " ".join(first.casefold().split()) == " ".join(second.casefold().split())


def company_key(name: str) -> str:
    tokens = re.findall(r"\w+", name.casefold().replace("&", " and "))
    kept = [t for t in tokens if t not in LEGAL_FORMS and t not in STOPWORDS]
    return " ".join(kept) or " ".join(tokens) or name.casefold().strip()


def _compatible(first: str, second: str) -> bool:
    """Two keys may share a cluster only if their digits match and they are very similar."""
    if re.findall(r"\d+", first) != re.findall(r"\d+", second):
        return False
    return SequenceMatcher(None, first, second).ratio() >= FUZZY_THRESHOLD


def _legal_form_normalised(name: str) -> str:
    return re.sub(r"\b([nbs])\.([vaprl])\.?", r"\1\2", name, flags=re.IGNORECASE)


def find_company_clusters(header: list[str], rows: list[list[str]], column: str) -> list[Cluster]:
    col = _index(header, column)
    by_key: dict[str, Cluster] = defaultdict(Cluster)
    for number, row in enumerate(rows, start=1):
        raw = row[col].strip()
        if not raw:
            continue
        cluster = by_key[company_key(_legal_form_normalised(raw))]
        cluster.rows.append(number)
        cluster.variants[raw] += 1

    # Complete linkage: a key joins a group only if it is compatible with every member, so
    # chains of similar names cannot merge companies that are not similar to each other.
    groups: list[list[str]] = []
    for key in sorted(by_key, key=lambda k: (-sum(by_key[k].variants.values()), k)):
        for group in groups:
            if all(_compatible(key, other) for other in group):
                group.append(key)
                break
        else:
            groups.append([key])

    merged: list[Cluster] = []
    for group in groups:
        cluster = Cluster()
        for key in group:
            cluster.rows.extend(by_key[key].rows)
            cluster.variants.update(by_key[key].variants)
        merged.append(cluster)
    return [c for c in merged if len(c.variants) > 1]


def _to_float(text: str) -> float | None:
    text = text.strip()
    if re.fullmatch(r"-?\d+,\d+", text):
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _words(column: str) -> set[str]:
    return set(re.findall(r"[a-z]+", column.lower()))


def _has_hint(column: str, hints: tuple[str, ...]) -> bool:
    return any(w in hints or w.rstrip("s") in hints for w in _words(column))


def detect_suspicious(header: list[str], rows: list[list[str]]) -> list[Issue]:
    issues = []
    for col, column in enumerate(header):
        lowered = column.lower()
        if lowered == "id" or lowered.endswith("_id"):
            continue
        values = [
            (n, _to_float(r[col].strip())) for n, r in enumerate(rows, start=1) if r[col].strip()
        ]
        numeric = [(n, v) for n, v in values if v is not None]
        if len(values) < 5 or len(numeric) < 0.8 * len(values):
            continue
        flagged: dict[int, str] = {}
        if _has_hint(column, NON_NEGATIVE_HINTS):
            for n, v in numeric:
                if v < 0:
                    flagged[n] = "Negative value in a column that should not be negative"
        if _has_hint(column, AGE_HINTS):
            for n, v in numeric:
                if v > 120:
                    flagged[n] = "Implausible age"
        numbers = [v for _, v in numeric]
        median = statistics.median(numbers)
        mad = statistics.median(abs(v - median) for v in numbers)
        if mad > 0:
            for n, v in numeric:
                if n not in flagged and abs(0.6745 * (v - median) / mad) > 10:
                    flagged[n] = "Extreme outlier compared with the rest of the column"
        for n, message in sorted(flagged.items()):
            issues.append(Issue("suspicious_value", n, column, rows[n - 1][col], message))
    return issues
