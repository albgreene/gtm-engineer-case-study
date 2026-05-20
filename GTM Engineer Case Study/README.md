# KGS SAP-Archiving Target Scraper

A small, deterministic Python scraper that produces a ranked list of German B2B accounts most likely to need SAP archiving — the evidence layer behind the cold-email campaign for **KGS Software** in the Arvana case study.

**Output:** `out/targets_DE_<YYYY-MM-DD>.csv` — 159 ranked companies with full score breakdowns.

## Run it

```bash
python3 scrape.py
```

No third-party dependencies. Python 3.9+. First run takes ~5 seconds; subsequent runs serve from `cache/` and complete in <1 second.

To refresh data: `rm -rf cache/ && python3 scrape.py`.

## Methodology — a 4-dimension scoring card (0–12)

| Dimension | Source | Range | Logic |
|---|---|---:|---|
| **Industry SAP affinity** | Wikipedia industry label | 0–3 | Automotive, chemicals, pharma, manufacturing → 3. Retail, finance, logistics → 2. Tech/media → 1. Static map. |
| **Hiring intent** | Indeed.de `?q=SAP` (see "Indeed signal" below) | 0–3 | Bin by count of open SAP roles: 6+ → 3, 3–5 → 2, 1–2 → 1, 0 → 0. |
| **Compliance pressure** | Industry label | 0–3 | Pharma, finance, energy, chemicals → 3 (GoBD, retention, audit obligations make archiving urgent). |
| **Size proxy** | Stock index membership | 0–3 | DAX → 3, MDAX → 2, SDAX → 1. |

All weights, bin edges, and industry mappings live in **one CONFIG block at the top of `scrape.py`** — single source of truth, tunable in seconds, visible in the presentation.

## Why these sources

- **Wikipedia DAX/MDAX/SDAX** — 159 large German listed companies with structured industry labels. Tables update <1×/quarter, fully public, no auth, parseable from stable HTML. Ideal deterministic seed.
- **Indeed.de `q=SAP`** — direct hiring-intent signal (companies that need SAP people *right now*). See note below.
- **Static industry/compliance maps** — version-controlled constants, zero variance across runs.

**Explicitly not used:** LinkedIn (auth wall, A/B'd markup, ToS risk, account-ban risk, non-deterministic), StepStone (aggressive bot detection), paid intent data (Bombora/G2 — out of budget for the case). LinkedIn was the user's first instinct; I steered away because determinism is the stated highest priority.

## Determinism guarantees

1. **On-disk response cache** keyed by `sha256(url)`. Reruns hit the cache, not the network. Bust by deleting `cache/`.
2. **Pinned source URLs** as constants in `scrape.py`.
3. **Single scoring config dict** at the top of the file — no environment-dependent tunables.
4. **Stable sort** by `score_total` desc, then `company` asc as the explicit tiebreaker.
5. **Snapshot date** in both the output filename and a column on every row, so historic CSVs are self-describing.
6. **No randomness anywhere.** No `random`, no time-based seeds, no parallel-fetch race conditions.

Verified: two consecutive runs produce **byte-identical CSVs** (`md5` matches).

## Indeed signal (the optional 4th dimension)

Indeed.de blocks plain HTTP requests (403). The script handles this two ways:

- **Default:** `FIRECRAWL_API_KEY` not set → Indeed step is skipped cleanly. Hiring score is 0 for everyone, total max becomes 9. Ranking still works.
- **Enabled:** `export FIRECRAWL_API_KEY=...` → the script shells out to the `firecrawl` CLI (already on Alberto's machine), bypasses the bot wall, parses company names from rendered markdown, and folds counts into the score. **Drop-in: change nothing, just set the env var.**

This is the deliberate architectural seam between *free deterministic public data* and *paid scraping infrastructure*. In production at Arvana, this seam plugs into Apollo/Clay instead of Firecrawl — same shape, different vendor.

## Output format

`out/targets_DE_<date>.csv` with columns:

```
company, index, industry, sap_jobs_count,
score_industry, score_hiring, score_compliance, score_size, score_total,
source_urls, snapshot_date
```

Sorted by `score_total` desc, ties broken alphabetically.

## Limitations (and what you'd do in production)

| Limitation | Production fix |
|---|---|
| No contact / email enrichment | Apollo or Clay (Arvana's existing stack) |
| Hiring signal needs a Firecrawl key | Already plugged in via env var — or use Apollo's job-data endpoint |
| Universe limited to listed companies (159) | Add Bundesanzeiger / Handelsregister scrape for unlisted Mittelstand (KGS's sweet spot) |
| Industry labels from Wikipedia are inconsistent ("chemistry" vs "chemicals") | Currently handled with substring matching + explicit aliases. Production: NACE / SIC code mapping. |
| No parent/subsidiary dedup | Apollo's account graph handles this |

## How this feeds the case study

The CSV's score breakdown maps cleanly to the **Segmentierung** requirement in Aufgabe 1:

- **Cohort A — High compliance + high size (DAX pharma/finance/energy):** archiving-as-compliance angle, GoBD/retention messaging.
- **Cohort B — High industry affinity + high hiring (manufacturing/automotive with active SAP roles):** "you're scaling SAP, archiving stops being optional" — cost & performance angle.
- **Cohort C — MDAX/SDAX industrials:** "S/4HANA migration ROI" — most movement potential, smaller deal sizes.

Three cohorts → three email variants → maps 1:1 to the case study's segmentation requirement.

## Project layout

```
kgs-target-scraper/
├── scrape.py          # entire pipeline, one file, ~280 lines
├── cache/             # HTTP response cache (sha256(url).html)
├── out/               # CSVs, one per run date
└── README.md          # this file
```
