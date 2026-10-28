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
FUZZY_THRESHOLD = 0.88


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
    return candidate if EMAIL_RE.match(candidate) and candidate != value else None


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
                issues.append(
                    Issue(
                        "duplicate_row",
                        number,
                        email_column,
                        row[email_col],
                        f"Same email as row {seen_emails[key]}",
                        "drop_row",
                    )
                )
                continue
            seen_emails[key] = number
    return issues


def company_key(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9 ]", " ", name.casefold().replace("&", " and ")).split()
    tokens = [t for t in tokens if t not in LEGAL_FORMS and t not in STOPWORDS]
    return " ".join(tokens)


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

    keys = sorted(by_key)
    parent = {k: k for k in keys}

    def root(key: str) -> str:
        while parent[key] != key:
            key = parent[key]
        return key

    for i, first in enumerate(keys):
        for second in keys[i + 1 :]:
            if SequenceMatcher(None, first, second).ratio() >= FUZZY_THRESHOLD:
                parent[root(second)] = root(first)

    merged: dict[str, Cluster] = defaultdict(Cluster)
    for key in keys:
        target = merged[root(key)]
        target.rows.extend(by_key[key].rows)
        target.variants.update(by_key[key].variants)
    return [c for c in merged.values() if len(c.variants) > 1]


def _to_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


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
        if any(h in lowered for h in NON_NEGATIVE_HINTS):
            for n, v in numeric:
                if v < 0:
                    flagged[n] = "Negative value in a column that should not be negative"
        if any(h in lowered for h in AGE_HINTS):
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
