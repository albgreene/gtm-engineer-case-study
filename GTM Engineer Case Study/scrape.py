#!/usr/bin/env python3
"""
KGS SAP-Archiving Target Scraper
================================
Produces a ranked CSV of German target accounts for KGS Software's
SAP archiving cold-email outreach.

Sources (Germany only, public, deterministic):
  1. Wikipedia DAX/MDAX/SDAX constituent tables — firmographics + size proxy
  2. Indeed.de "SAP" job search                  — hiring intent signal
  3. Static industry/compliance maps (below)    — affinity + regulatory pressure

Run: python3 scrape.py
Output: out/targets_DE_<YYYY-MM-DD>.csv

Determinism:
  - Every HTTP response cached to cache/<sha256-prefix>.html
  - Reruns hit the cache only; delete cache/ to refresh
  - Stable sort with explicit tiebreaker
  - All scoring tunables in the CONFIG block below
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import ssl
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# macOS system Python often lacks a usable CA bundle; we read public pages
# only, so an unverified context is a deliberate trade-off for portability.
_SSL_CTX = ssl._create_unverified_context()

# ─── CONFIG ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "cache"
OUT_DIR = ROOT / "out"

WIKIPEDIA_INDEX_URLS = {
    "DAX": "https://en.wikipedia.org/wiki/DAX",
    "MDAX": "https://en.wikipedia.org/wiki/MDAX",
    "SDAX": "https://en.wikipedia.org/wiki/SDAX",
}

INDEED_BASE = "https://de.indeed.com/jobs?q=SAP&l=Deutschland"
INDEED_PAGES = 10  # ~15 results per page

# Size proxy from index membership
SIZE_SCORE = {"DAX": 3, "MDAX": 2, "SDAX": 1}

# Industry → SAP affinity (likelihood of being a heavy SAP user)
INDUSTRY_AFFINITY = {
    "automotive": 3, "automobile": 3,
    "chemical": 3, "chemicals": 3, "chemistry": 3,
    "pharmaceutical": 3, "pharmaceuticals": 3, "pharma": 3, "biotech": 3,
    "manufacturing": 3, "industrial": 3, "industrial conglomerate": 3,
    "industrial engineering": 3, "mechanical engineering": 3, "machinery": 3,
    "electrical equipment": 3, "semiconductor": 3,
    "steel": 3, "metals": 3, "aerospace": 3, "defence": 3, "defense": 3,
    "retail": 2, "consumer goods": 2, "food": 2, "beverages": 2,
    "logistics": 2, "transportation": 2, "shipping": 2, "airline": 2,
    "energy": 2, "utilities": 2, "oil and gas": 2,
    "telecommunications": 2, "telecom": 2,
    "banking": 2, "bank": 2, "finance": 2, "insurance": 2, "financial services": 2,
    "construction": 2, "building materials": 2,
    "medical equipment": 2, "medical technology": 2, "medtech": 2,
    "e-commerce": 2, "ecommerce": 2,
    "healthcare": 1, "health care": 1, "medical": 1,
    "media": 1, "real estate": 1, "technology": 1, "software": 1,
}
DEFAULT_AFFINITY = 1

# Compliance pressure (GoBD, retention, audit obligations → archiving urgency)
COMPLIANCE_SCORE = {
    "pharmaceutical": 3, "pharmaceuticals": 3, "pharma": 3,
    "banking": 3, "bank": 3, "finance": 3, "financial services": 3, "insurance": 3,
    "energy": 3, "utilities": 3, "oil and gas": 3,
    "chemical": 3, "chemicals": 3,
    "healthcare": 2, "health care": 2, "medical": 2,
    "automotive": 2, "automobile": 2,
    "aerospace": 2, "defence": 2, "defense": 2,
    "telecommunications": 2, "telecom": 2,
    "food": 1, "beverages": 1, "transportation": 1, "logistics": 1,
}

def hiring_score(n: int) -> int:
    if n >= 6: return 3
    if n >= 3: return 2
    if n >= 1: return 1
    return 0

NAME_SUFFIXES = [
    " AG & Co. KGaA", " AG & Co KGaA", " GmbH & Co. KG", " GmbH & Co KG",
    " SE & Co. KGaA", " SE & Co KGaA",
    " AG", " SE", " GmbH", " KGaA",
    " N.V.", " NV", " S.A.", " SA", " plc", " PLC", " Group",
]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}

SNAPSHOT_DATE = date.today().isoformat()

# ─── HTTP with on-disk cache ────────────────────────────────────────────────

def fetch(url: str) -> str:
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    req = Request(url, headers=HTTP_HEADERS)
    try:
        with urlopen(req, timeout=30, context=_SSL_CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as e:
        sys.stderr.write(f"    fetch failed: {url} → {e}\n")
        body = ""
    cached.write_text(body, encoding="utf-8")
    time.sleep(0.5)
    return body

# ─── Wikipedia ingest ───────────────────────────────────────────────────────

class _WikiTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if tag == "table" and "wikitable" in cls:
            self._table = []
        elif self._table is not None and tag == "tr":
            self._row = []
        elif self._row is not None and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None
        elif tag == "tr" and self._row is not None:
            if self._row and self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            if self._row is not None:
                self._row.append(text)
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_index_components(html: str, index_name: str) -> list[dict]:
    p = _WikiTableParser()
    p.feed(html)
    target = None
    for tbl in p.tables:
        if not tbl: continue
        header = [c.lower() for c in tbl[0]]
        has_company = any("company" in c or "name" in c for c in header)
        has_industry = any("industry" in c or "sector" in c for c in header)
        if has_company and has_industry:
            target = tbl
            break
    if target is None:
        return []
    header = [c.lower() for c in target[0]]
    name_idx = next((i for i, c in enumerate(header) if "company" in c or "name" in c), None)
    ind_idx = next((i for i, c in enumerate(header) if "industry" in c or "sector" in c), None)
    rows = []
    for r in target[1:]:
        if max(name_idx or 0, ind_idx or 0) >= len(r):
            continue
        name = re.sub(r"\[\d+\]", "", r[name_idx]).strip()
        industry = re.sub(r"\[\d+\]", "", r[ind_idx]).strip().lower()
        if name:
            rows.append({"name": name, "industry": industry, "index": index_name})
    return rows


def load_wikipedia_companies() -> list[dict]:
    companies = []
    for index_name, url in WIKIPEDIA_INDEX_URLS.items():
        print(f"    fetching {index_name} ...")
        rows = parse_index_components(fetch(url), index_name)
        print(f"      parsed {len(rows)} companies")
        for r in rows:
            r["source_urls"] = [url]
        companies.extend(rows)
    return companies

# ─── Indeed.de ingest ───────────────────────────────────────────────────────

INDEED_PATTERNS = [
    re.compile(r'data-testid="company-name"[^>]*>([^<]+)<', re.I),
    re.compile(r'class="[^"]*companyName[^"]*"[^>]*>([^<]+)<', re.I),
    re.compile(r'"companyName"\s*:\s*"([^"]+)"', re.I),
]

def extract_indeed_companies(html: str) -> list[str]:
    for pat in INDEED_PATTERNS:
        hits = pat.findall(html)
        if hits:
            return [h.strip() for h in hits if h.strip()]
    return []


def _fetch_indeed_via_firecrawl(url: str) -> str:
    """Use the firecrawl CLI to bypass Indeed's bot wall.
    Requires FIRECRAWL_API_KEY in env. Caches the markdown output."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha256(("FC:" + url).encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.md"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    try:
        r = subprocess.run(
            ["firecrawl", "scrape", url, "--only-main-content", "-o", str(cached)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            sys.stderr.write(f"    firecrawl failed: {r.stderr.strip()[:200]}\n")
            cached.write_text("", encoding="utf-8")
            return ""
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        sys.stderr.write(f"    firecrawl unavailable: {e}\n")
        cached.write_text("", encoding="utf-8")
        return ""
    time.sleep(0.5)
    return cached.read_text(encoding="utf-8") if cached.exists() else ""


# Indeed job-card markdown pattern when fetched via Firecrawl:
#   "**Job title** ... [Company name](https://de.indeed.com/cmp/...)"
INDEED_MD_COMPANY = re.compile(r"\]\((https?://de\.indeed\.com/cmp/[^)]+)\)")
INDEED_MD_NAME = re.compile(r"\[([^\]]+)\]\(https?://de\.indeed\.com/cmp/")


def load_indeed_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    use_firecrawl = bool(os.environ.get("FIRECRAWL_API_KEY"))
    if not use_firecrawl:
        print("    skipping Indeed hiring signal: FIRECRAWL_API_KEY not set.")
        print("    (Indeed.de blocks direct urllib requests. Set the key to enable.)")
        return {}
    for page in range(INDEED_PAGES):
        url = f"{INDEED_BASE}&start={page * 10}"
        print(f"    fetching Indeed page {page + 1}/{INDEED_PAGES} via firecrawl ...")
        md = _fetch_indeed_via_firecrawl(url)
        names = INDEED_MD_NAME.findall(md)
        for n in names:
            counts[n.strip()] += 1
        if not names and page == 0:
            print("      WARNING: Indeed returned 0 — markup may have changed.")
            break
    return dict(counts)

# ─── Match + score ──────────────────────────────────────────────────────────

def normalize(n: str) -> str:
    n = n.strip()
    for s in NAME_SUFFIXES:
        if n.lower().endswith(s.lower()):
            n = n[: -len(s)]
            break
    return re.sub(r"\s+", " ", n).lower().strip(" .,")


def industry_score(industry: str) -> int:
    industry = (industry or "").lower()
    if industry in INDUSTRY_AFFINITY:
        return INDUSTRY_AFFINITY[industry]
    for key, val in INDUSTRY_AFFINITY.items():
        if key in industry:
            return val
    return DEFAULT_AFFINITY


def compliance_score(industry: str) -> int:
    industry = (industry or "").lower()
    if industry in COMPLIANCE_SCORE:
        return COMPLIANCE_SCORE[industry]
    for key, val in COMPLIANCE_SCORE.items():
        if key in industry:
            return val
    return 0


def merge_and_score(companies: list[dict], indeed: dict[str, int]) -> list[dict]:
    norm_counts: dict[str, int] = defaultdict(int)
    for raw, n in indeed.items():
        norm_counts[normalize(raw)] += n

    out = []
    for c in companies:
        nm = normalize(c["name"])
        jobs = norm_counts.get(nm, 0)
        if jobs == 0:
            for k, v in norm_counts.items():
                if k and (k.startswith(nm + " ") or nm.startswith(k + " ")):
                    jobs = max(jobs, v)
        s_ind = industry_score(c["industry"])
        s_hire = hiring_score(jobs)
        s_comp = compliance_score(c["industry"])
        s_size = SIZE_SCORE.get(c["index"], 0)
        out.append({
            "company": c["name"],
            "index": c["index"],
            "industry": c["industry"],
            "sap_jobs_count": jobs,
            "score_industry": s_ind,
            "score_hiring": s_hire,
            "score_compliance": s_comp,
            "score_size": s_size,
            "score_total": s_ind + s_hire + s_comp + s_size,
            "source_urls": "; ".join(c["source_urls"]),
            "snapshot_date": SNAPSHOT_DATE,
        })
    out.sort(key=lambda r: (-r["score_total"], r["company"].lower()))
    return out

# ─── Output ─────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict]) -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"targets_DE_{SNAPSHOT_DATE}.csv"
    cols = [
        "company", "index", "industry", "sap_jobs_count",
        "score_industry", "score_hiring", "score_compliance", "score_size",
        "score_total", "source_urls", "snapshot_date",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path

# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    print("→ Wikipedia DAX/MDAX/SDAX")
    companies = load_wikipedia_companies()
    print(f"  total companies: {len(companies)}")

    print("→ Indeed.de SAP hiring intent")
    indeed = load_indeed_counts()
    print(f"  companies hiring SAP roles: {len(indeed)}")

    print("→ Scoring")
    rows = merge_and_score(companies, indeed)

    path = write_csv(rows)
    print(f"→ Wrote {path}")
    print("\nTop 20:")
    for r in rows[:20]:
        print(f"  {r['score_total']:>2}  {r['index']:<5}  "
              f"{r['company'][:38]:<38}  jobs={r['sap_jobs_count']:<3}  "
              f"({r['industry'][:28]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
