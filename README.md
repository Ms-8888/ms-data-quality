# ms-data-quality

[![CI](https://github.com/Ms-8888/ms-data-quality/actions/workflows/ci.yml/badge.svg)](https://github.com/Ms-8888/ms-data-quality/actions/workflows/ci.yml)

A small command-line tool that finds data quality problems in a CSV or Excel file, proposes fixes, and applies only the ones you approve. It writes a cleaned copy and a change report; your original file is never touched.

All data in this repository is fictional.

## Problem

Customer lists collected from forms, imports and several people drift: "Acme NV", "ACME N.V." and "acme nv" are three companies in a report; a typo in an email domain bounces a mailing; the same person is in the list twice; an age of 212 skews an average. Cleaning this by hand is slow, and cleaning it automatically without asking silently rewrites data you may need.

## Solution

`dq scan` lists the problems and changes nothing. `dq clean` goes through the fixes one by one, asks you to approve each, and writes:

- `<name>.cleaned.csv` (or `.xlsx`): the data with only your approved changes
- `<name>.changes.md`: what changed (before and after), what you rejected, and what needs a human because there is no safe automatic fix

What it checks:

| Check | Automatic proposal |
|---|---|
| Invalid emails (no `@`, double `@`, no top-level domain, spaces) and known typo domains (`gmial.com`) | Fix when the fix is obvious (`marie@@x.be` becomes `marie@x.be`, `gmial.com` becomes `gmail.com`); otherwise flag only |
| Company name variants (case, punctuation, legal form, `&` vs `en`, small typos) | One canonical spelling per group, chosen by the backend, applied to every variant you approve |
| Duplicate rows (identical apart from an `id` column), and the same email with the same name | Remove the later row. The same email with a different name (a shared `info@` address, say) is only flagged. |
| Missing required fields (`--required name,email,company`) | Flag only: it cannot invent data |
| Suspicious numbers (negative where that makes no sense, ages over 120, extreme outliers) | Flag only |

## Use it

```bash
git clone https://github.com/Ms-8888/ms-data-quality
cd ms-data-quality
pip install -e .

dq scan data/sample_customers.csv --required name,email,company
dq clean data/sample_customers.csv --required name,email,company
```

Python 3.11 or newer. `dq clean` asks `[y]es / [n]o / [a]ccept all / [q]uit and reject rest` for every proposal. `--yes` applies everything without asking, for demos and scripts; read the change report afterwards, because it also accepts name merges you might have rejected. `--out` and `--report` choose the output paths; the tool refuses to overwrite the input file.

## Who picks the canonical company name

| `--backend` | Needs | How it chooses |
|---|---|---|
| `rules` (default) | nothing | The most frequent spelling, preferring one with a legal form and normal casing. |
| `ollama` | [Ollama](https://ollama.com) running locally (`OLLAMA_MODEL`, default `qwen2.5:7b`) | A local model picks from the spellings; nothing leaves the machine. |
| `anthropic` | `pip install ".[anthropic]"` and `ANTHROPIC_API_KEY` | Claude picks the name. **Not yet run against the real API.** |
| `claude-cli` | the `claude` CLI, logged in, on the same machine | Author's own Claude Code login. Development mode, not for deployment. |

Only the company spellings and how often each occurs are sent to a model, never the rows. A model answer is accepted only if it is (nearly) one of the real spellings, so a model cannot invent a company; an empty, invented or failed answer falls back to `rules`, and the change report records which source each change came from.

## What was measured

A 40-row fictional customer list with 16 planted problems and three company-name groups, written by the author together with a ground-truth file (`data/sample_customers.truth.json`). It is a smoke test of the detectors, not a benchmark.

- **Detection:** all 16 planted problems are found and no clean row is flagged (enforced by `tests/test_detect.py`). Because the author wrote both the data and the detectors, this shows the detectors do what they claim on known cases. It says nothing about accuracy on real data.
- **Choosing the canonical name** (3 groups, `scripts/eval_backends.py`, raw output in `results/backends.json`). One group is deliberately hard: the most common spelling is the typo (`Delta Logistiks`, 2 rows, against `Delta Logistics`, 1 row, and `Delta Logistics BVBA`, 1 row).

| Backend | Acceptable name | Delta (typo is most frequent) |
|---|---|---|
| `rules` | 2/3 | picks the typo `Delta Logistiks` |
| `ollama` (`qwen2.5:7b`) | 3/3 | `Delta Logistics` |
| `claude-cli` | 3/3 | `Delta Logistics BVBA` |

Three groups is a very small test. The point it supports is narrow: frequency alone can pick a typo, and a model reading all spellings avoided it here. The number of problems reported can differ between backends, because which spelling counts as the odd one out depends on the chosen name.

## Safety

- Nothing changes without approval; the input file is never modified or overwritten. A row with more fields than the header (usually an unquoted comma) is refused with its row number instead of being cut off, and blank lines are ignored.
- Spreadsheet formula injection: text that starts with `=`, `@`, a tab, or `+`/`-` followed by something that is not a number or phone-style digits is neutralised on export. In CSV it gets a leading `'` (this changes the stored text, so the change report says how many cells were affected); in XLSX it is stored as plain text with no visible change. Numbers and phone numbers such as `+31 6 12345678` are left alone. Tested for both formats.
- Files are limited to `.csv` and `.xlsx`, 50 MB and 100,000 rows; damaged files give a clear error. No `eval`, no network calls except the optional model backends. The change report escapes cell contents, so a hostile value cannot become a link or HTML in a Markdown viewer.
- The `claude-cli` backend runs with file, shell and web tools switched off and an empty working folder, so a company name cannot make it read files.

## Limitations

- Five simple checks, tuned on one small sample. No phone numbers, dates, addresses or cross-column rules.
- Company grouping needs names to be at least 92% similar, to have the same digits, and (complete linkage) to be similar to every other name in the group. Near-identical but different companies ("Garage Peeters" and "Garage Peters") still cannot be told from a typo by spelling alone, which is why every rename needs your approval.
- Email checks are format checks, not delivery checks.
- Duplicates are found by exact match (ignoring `id` columns) or by the same email; there is no fuzzy person matching.
- The numeric checks need at least five values in a column. The outlier check works poorly on small or heavily skewed columns, and not at all when most values are identical. Numbers written with a comma decimal (`1,5`) are understood; dates and currency symbols are not.
- Excel files lose their cell types (dates and numbers come back as text) and only the first sheet is read.

## Layout

```
ms_data_quality/  detectors, backends, cleaning flow, report, CLI
data/             fictional sample file and its ground truth
scripts/          make_sample.py, eval_backends.py
results/          recorded backend comparison
tests/            pytest suite
```

## Develop

```bash
pip install -e ".[dev]"
ruff check . && pytest
```

## Independent review

Before this was shared, four reviewers (security, claims audit, code quality, recruiter view) read it independently. They found real problems, all reproduced with a failing test and then fixed: companies with different numbers or place names were merged; chains of similar names merged unrelated companies; names made of only a legal form or in non-Latin script collapsed into one group; multi-line CSV cells were corrupted; rows with extra fields were silently cut off; column hints matched inside longer words (`page_views` flagged as an age); comma decimals disabled the numeric checks; a shared `info@` address got people deleted; and export rewrote phone numbers. The tests for each are in `tests/test_regressions.py`.
