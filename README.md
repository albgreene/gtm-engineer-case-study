# KGS SAP-Archivierung – Target-Scraper

Ein kleiner, deterministischer Python-Scraper, der eine priorisierte Liste deutscher B2B-Accounts erzeugt, die mit hoher Wahrscheinlichkeit SAP-Archivierung benötigen — die Evidenz-Ebene hinter der Cold-E-Mail-Kampagne für **KGS Software** im Arvana-Case-Study.

> Das vollständige Projekt liegt im Verzeichnis [`GTM Engineer Case Study/`](./GTM%20Engineer%20Case%20Study).

**Output:** `out/targets_DE_<JJJJ-MM-TT>.csv` — 159 priorisierte Unternehmen mit vollständiger Score-Aufschlüsselung.

## Ausführen

```bash
cd "GTM Engineer Case Study"
python3 scrape.py
```

Keine Drittanbieter-Abhängigkeiten. Python 3.9+. Der erste Lauf dauert ca. 5 Sekunden; weitere Läufe werden aus `cache/` bedient und sind in <1 Sekunde fertig.

Daten aktualisieren: `rm -rf cache/ && python3 scrape.py`.

## Methodik — eine 4-Dimensionen-Scoring-Karte (0–12)

| Dimension | Quelle | Bereich | Logik |
|---|---|---:|---|
| **SAP-Affinität der Branche** | Wikipedia-Branchenlabel | 0–3 | Automobil, Chemie, Pharma, Fertigung → 3. Handel, Finanzen, Logistik → 2. Tech/Medien → 1. Statische Zuordnung. |
| **Einstellungsabsicht (Hiring-Signal)** | Indeed.de `?q=SAP` (siehe „Indeed-Signal" unten) | 0–3 | Klassierung nach Anzahl offener SAP-Stellen: 6+ → 3, 3–5 → 2, 1–2 → 1, 0 → 0. |
| **Compliance-Druck** | Branchenlabel | 0–3 | Pharma, Finanzen, Energie, Chemie → 3 (GoBD, Aufbewahrungs- und Audit-Pflichten machen Archivierung dringend). |
| **Größen-Proxy** | Mitgliedschaft im Börsenindex | 0–3 | DAX → 3, MDAX → 2, SDAX → 1. |

Alle Gewichte, Klassengrenzen und Branchenzuordnungen liegen in **einem CONFIG-Block am Anfang von `scrape.py`** — eine einzige Quelle der Wahrheit, in Sekunden anpassbar, in der Präsentation sichtbar.

## Warum diese Quellen

- **Wikipedia DAX/MDAX/SDAX** — 159 große börsennotierte deutsche Unternehmen mit strukturierten Branchenlabels. Die Tabellen ändern sich seltener als 1×/Quartal, sind vollständig öffentlich, ohne Auth und aus stabilem HTML parsebar. Ideale deterministische Ausgangsbasis (Seed).
- **Indeed.de `q=SAP`** — direktes Hiring-Intent-Signal (Unternehmen, die *genau jetzt* SAP-Leute brauchen). Siehe Hinweis unten.
- **Statische Branchen-/Compliance-Zuordnungen** — versionierte Konstanten, null Varianz zwischen Läufen.

**Bewusst nicht genutzt:** LinkedIn (Auth-Wall, A/B-getestetes Markup, ToS-Risiko, Gefahr der Account-Sperre, nicht deterministisch), StepStone (aggressive Bot-Erkennung), kostenpflichtige Intent-Daten (Bombora/G2 — für diesen Case außerhalb des Budgets). LinkedIn war der erste Impuls; ich habe bewusst darauf verzichtet, weil Determinismus die erklärte oberste Priorität ist.

## Determinismus-Garantien

1. **On-Disk-Response-Cache**, indexiert über `sha256(url)`. Erneute Läufe treffen den Cache, nicht das Netzwerk. Zum Zurücksetzen `cache/` löschen.
2. **Fest verdrahtete Quell-URLs** als Konstanten in `scrape.py`.
3. **Ein einziges Scoring-Config-Dictionary** am Anfang der Datei — keine umgebungsabhängigen Parameter.
4. **Stabile Sortierung** nach `score_total` absteigend, dann `company` aufsteigend als expliziter Tiebreaker.
5. **Snapshot-Datum** sowohl im Output-Dateinamen als auch als Spalte in jeder Zeile, sodass historische CSVs selbsterklärend sind.
6. **Kein Zufall, nirgends.** Kein `random`, keine zeitbasierten Seeds, keine Race-Conditions durch paralleles Laden.

Verifiziert: zwei aufeinanderfolgende Läufe erzeugen **byte-identische CSVs** (`md5` stimmt überein).

## Indeed-Signal (die optionale 4. Dimension)

Indeed.de blockiert einfache HTTP-Anfragen (403). Das Skript geht damit auf zwei Arten um:

- **Standard:** `FIRECRAWL_API_KEY` nicht gesetzt → der Indeed-Schritt wird sauber übersprungen. Der Hiring-Score ist für alle 0, das Gesamtmaximum wird zu 9. Das Ranking funktioniert weiterhin.
- **Aktiviert:** `export FIRECRAWL_API_KEY=...` → das Skript ruft das `firecrawl`-CLI auf (bereits auf Albertos Rechner vorhanden), umgeht die Bot-Sperre, parst Firmennamen aus dem gerenderten Markdown und rechnet die Zählungen in den Score ein. **Drop-in: nichts ändern, nur die Env-Variable setzen.**

Dies ist die bewusste architektonische Naht zwischen *kostenlosen, deterministischen öffentlichen Daten* und *kostenpflichtiger Scraping-Infrastruktur*. In der Produktion bei Arvana wird diese Naht an Apollo/Clay angedockt statt an Firecrawl — gleiche Form, anderer Anbieter.

## Output-Format

`out/targets_DE_<datum>.csv` mit den Spalten:

```
company, index, industry, sap_jobs_count,
score_industry, score_hiring, score_compliance, score_size, score_total,
source_urls, snapshot_date
```

Sortiert nach `score_total` absteigend, Gleichstände alphabetisch aufgelöst.

## Einschränkungen (und was man in Produktion täte)

| Einschränkung | Produktiv-Lösung |
|---|---|
| Keine Kontakt-/E-Mail-Anreicherung | Apollo oder Clay (Arvanas bestehender Stack) |
| Hiring-Signal benötigt einen Firecrawl-Key | Bereits per Env-Variable eingebunden — oder Apollos Job-Daten-Endpoint nutzen |
| Universum auf börsennotierte Unternehmen begrenzt (159) | Bundesanzeiger-/Handelsregister-Scrape für nicht gelistete Mittelständler ergänzen (KGS' Sweet Spot) |
| Branchenlabels von Wikipedia sind inkonsistent („chemistry" vs. „chemicals") | Aktuell per Substring-Matching + expliziten Aliassen gelöst. Produktion: NACE-/SIC-Code-Mapping. |
| Keine Mutter-/Tochter-Deduplizierung | Apollos Account-Graph übernimmt das |

## Wie das in den Case Study einfließt

Die Score-Aufschlüsselung des CSV lässt sich sauber auf die **Segmentierung** in Aufgabe 1 abbilden:

- **Kohorte A — Hohe Compliance + große Unternehmen (DAX Pharma/Finanzen/Energie):** Archivierung-als-Compliance-Ansatz, GoBD-/Aufbewahrungs-Messaging.
- **Kohorte B — Hohe Branchenaffinität + hohes Hiring (Fertigung/Automobil mit aktiven SAP-Stellen):** „Ihr skaliert SAP — Archivierung ist nicht länger optional" — Kosten- und Performance-Ansatz.
- **Kohorte C — MDAX/SDAX-Industriewerte:** „S/4HANA-Migrations-ROI" — größtes Bewegungspotenzial, kleinere Deal-Größen.

Drei Kohorten → drei E-Mail-Varianten → 1:1-Abbildung auf die Segmentierungsanforderung des Case Study.

## Projektstruktur

```
gtm-engineer-case-study/      (Repository-Wurzel)
├── README.md                 # diese deutsche Übersicht (GitHub-Startseite)
└── GTM Engineer Case Study/
    ├── scrape.py             # gesamte Pipeline, eine Datei, ~280 Zeilen
    ├── README.md             # englische Fassung
    ├── cache/                # HTTP-Response-Cache (sha256(url).html)
    └── out/                  # CSVs, eine pro Lauf-Datum
```
