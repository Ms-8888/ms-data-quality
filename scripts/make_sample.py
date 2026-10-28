"""Writes data/sample_customers.csv and data/sample_customers.truth.json (fictional people and companies).

Each planted problem is listed in the truth file so detection can be measured. Row numbers are
1-based data rows (the header is not counted).
"""

import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

HEADER = ["id", "name", "email", "company", "country", "age", "revenue"]

# (id, name, email, company, country, age, revenue, planted problems as (kind, column))
ROWS = [
    (1, "Jan Peeters", "jan.peeters@acme.example", "Acme NV", "BE", 34, 12000, []),
    (2, "Sofie De Wit", "sofie.dewit@acme.example", "ACME N.V.", "BE", 41, 15500, []),
    (3, "Pieter Maes", "pieter.maes@acme.example", "Acme n.v", "BE", 29, 9800, []),
    (4, "Lien Claes", "lien.claes@acme.example", "acme nv", "BE", 38, 11200, []),
    (5, "Tom Janssens", "tom.janssens@janssen.example", "Janssen & Zonen BV", "NL", 52, 30500, []),
    (6, "Eva Jacobs", "eva.jacobs@janssen.example", "Janssen en Zonen BV", "NL", 47, 28000, []),
    (7, "Koen Willems", "koen.willems@janssen.example", "Janssen & Zonen", "NL", 33, 26400, []),
    (8, "An Goossens", "an.goossens@delta.example", "Delta Logistics", "BE", 45, 41000, []),
    (9, "Bart Mertens", "bart.mertens@delta.example", "Delta Logistics BVBA", "BE", 36, 39500, []),
    (10, "Nele Hermans", "nele.hermans@delta.example", "Delta Logistiks", "BE", 31, 38200, []),
    (
        11,
        "Wim Aerts",
        "wim.aerts@gmial.com",
        "Orion Software",
        "BE",
        39,
        22000,
        [("invalid_email", "email")],
    ),
    (
        12,
        "Marie Smets",
        "marie@@orion.example",
        "Orion Software",
        "BE",
        27,
        21000,
        [("invalid_email", "email")],
    ),
    (
        13,
        "Pieter Vermeulen",
        "pieter vermeulen@orion.example",
        "Orion Software",
        "BE",
        44,
        23500,
        [("invalid_email", "email")],
    ),
    (
        14,
        "Sofie Dewit",
        "sofie.dewit.orion.example",
        "Orion Software",
        "BE",
        35,
        20500,
        [("invalid_email", "email")],
    ),
    (
        15,
        "Tom Pauwels",
        "tom@orion",
        "Orion Software",
        "BE",
        50,
        24000,
        [("invalid_email", "email")],
    ),
    (16, "Hanne Bogaert", "hanne.bogaert@vandamme.example", "Van Damme Bouw", "BE", 42, 18700, []),
    (17, "Luc Desmet", "luc.desmet@vandamme.example", "Van Damme Bouw", "BE", 55, 19900, []),
    (18, "Ine Wouters", "ine.wouters@lumen.example", "Lumen Studio", "NL", 30, 8700, []),
    (19, "Joris Peeters", "joris.peeters@lumen.example", "Lumen Studio", "NL", 28, 9100, []),
    (20, "Fien Lambert", "fien.lambert@nordic.example", "Nordic Trade", "BE", 37, 33300, []),
    (21, "Dries Michiels", "dries.michiels@nordic.example", "Nordic Trade", "BE", 46, 31800, []),
    (22, "Anke Verhulst", "anke.verhulst@bakker.example", "Bakkerij Bakker", "BE", 40, 7400, []),
    (23, "Stijn Carlier", "stijn.carlier@bakker.example", "Bakkerij Bakker", "BE", 32, 6900, []),
    (24, "Charlotte Vos", "charlotte.vos@helix.example", "Helix Medical", "NL", 43, 52000, []),
    (25, "Maarten Smits", "maarten.smits@helix.example", "Helix Medical", "NL", 49, 51200, []),
    (26, "Elke Dupont", "elke.dupont@mosaic.example", "Mosaic Design", "BE", 26, 6200, []),
    (27, "Gert Lemmens", "gert.lemmens@mosaic.example", "Mosaic Design", "BE", 58, 6800, []),
    (
        28,
        "Isabelle Moens",
        "isabelle.moens@vanguard.example",
        "Vanguard Retail",
        "BE",
        36,
        27700,
        [],
    ),
    (29, "Raf Cools", "raf.cools@vanguard.example", "Vanguard Retail", "BE", 41, 28900, []),
    (30, "Kim Declercq", "", "Orion Software", "BE", 34, 22200, [("missing_field", "email")]),
    (31, "Yves Thys", "", "Nordic Trade", "BE", 45, 30100, [("missing_field", "email")]),
    (
        32,
        "Sara Martens",
        "sara.martens@helix.example",
        "",
        "NL",
        38,
        50100,
        [("missing_field", "company")],
    ),
    (
        33,
        "Bram Lenaerts",
        "bram.lenaerts@vanguard.example",
        "",
        "BE",
        29,
        26500,
        [("missing_field", "company")],
    ),
    (
        34,
        "Femke Hoste",
        "femke.hoste@lumen.example",
        "Lumen Studio",
        "NL",
        -3,
        9400,
        [("suspicious_value", "age")],
    ),
    (
        35,
        "Rik Dhondt",
        "rik.dhondt@mosaic.example",
        "Mosaic Design",
        "BE",
        212,
        6400,
        [("suspicious_value", "age")],
    ),
    (
        36,
        "Lotte Fierens",
        "lotte.fierens@bakker.example",
        "Bakkerij Bakker",
        "BE",
        35,
        -5000,
        [("suspicious_value", "revenue")],
    ),
    (
        37,
        "Hugo Van Acker",
        "hugo.vanacker@delta.example",
        "Delta Logistiks",
        "BE",
        48,
        9999999,
        [("suspicious_value", "revenue")],
    ),
    (
        38,
        "Jan Peeters",
        "jan.peeters@acme.example",
        "Acme NV",
        "BE",
        34,
        12000,
        [("duplicate_row", "*")],
    ),
    (
        39,
        "Eva Jacobs",
        "eva.jacobs@janssen.example",
        "Janssen en Zonen BV",
        "NL",
        47,
        28000,
        [("duplicate_row", "*")],
    ),
    (
        40,
        "LIEN CLAES",
        "lien.claes@acme.example",
        "Acme NV",
        "BE",
        38,
        11200,
        [("duplicate_row", "email")],
    ),
]

# Company-name clusters that are the same company written differently (row numbers, 1-based).
CLUSTERS = {
    "Acme": {"rows": [1, 2, 3, 4, 38, 40], "accepted": ["Acme NV"]},
    "Janssen": {"rows": [5, 6, 7, 39], "accepted": ["Janssen & Zonen BV", "Janssen en Zonen BV"]},
    "Delta": {"rows": [8, 9, 10, 37], "accepted": ["Delta Logistics", "Delta Logistics BVBA"]},
}


def main() -> None:
    DATA.mkdir(exist_ok=True)
    with (DATA / "sample_customers.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in ROWS:
            writer.writerow(row[:7])
    problems = [
        {"kind": kind, "row": index, "column": column}
        for index, row in enumerate(ROWS, start=1)
        for kind, column in row[7]
    ]
    truth = {
        "problems": problems,
        "company_clusters": CLUSTERS,
        "required": ["name", "email", "company"],
    }
    (DATA / "sample_customers.truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"{len(ROWS)} rows, {len(problems)} planted problems")


if __name__ == "__main__":
    main()
