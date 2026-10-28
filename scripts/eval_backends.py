"""Checks which canonical company name each backend picks for the planted clusters.

Usage: python scripts/eval_backends.py rules claude-cli ollama
Writes results/backends.json. Uses data/sample_customers.csv and its truth file.
"""

import json
import sys
import time
from pathlib import Path

from ms_data_quality.detect import find_company_clusters
from ms_data_quality.suggest import choose_canonical, get_backend
from ms_data_quality.tableio import read_table

ROOT = Path(__file__).resolve().parent.parent
header, rows = read_table(ROOT / "data" / "sample_customers.csv")
truth = json.loads((ROOT / "data" / "sample_customers.truth.json").read_text(encoding="utf-8"))
clusters = find_company_clusters(header, rows, "company")

results = {}
for name in sys.argv[1:]:
    backend = get_backend(name)
    entries = []
    for cluster in clusters:
        label = next(
            key
            for key, spec in truth["company_clusters"].items()
            if sorted(spec["rows"]) == sorted(cluster.rows)
        )
        started = time.time()
        choice, source = choose_canonical(cluster.variants, backend)
        accepted = truth["company_clusters"][label]["accepted"]
        entries.append(
            {
                "cluster": label,
                "variants": dict(cluster.variants),
                "chosen": choice,
                "source": source,
                "acceptable": choice in accepted,
                "seconds": round(time.time() - started, 1),
            }
        )
    results[name] = entries
    ok = sum(e["acceptable"] for e in entries)
    print(f"{name}: {ok}/{len(entries)} acceptable")
    for e in entries:
        verdict = "OK" if e["acceptable"] else "WRONG"
        print(f"   {e['cluster']:8} -> {e['chosen']!r} [{e['source']}] {verdict}")

out = ROOT / "results"
out.mkdir(exist_ok=True)
(out / "backends.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), "utf-8")
