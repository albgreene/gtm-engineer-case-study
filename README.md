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

## n8n-Outreach-Workflow (Aufgabe 2)

Companion-Workflow zum Scraper. Er nimmt den Scraper-Output (priorisierte Unternehmen + Kontakte, in Google Sheets gepflegt), routet jeden Kontakt nach Größen-Tier auf E-Mail oder LinkedIn, personalisiert die Copy pro Segment über einen LLM-generierten Opener und protokolliert jeden Versand für Dedup + Audit. Die importierbare Datei liegt unter [`GTM Engineer Case Study/n8n/workflow.json`](./GTM%20Engineer%20Case%20Study/n8n/workflow.json).

### Was der Workflow macht

- **Channel-Routing nach Größen-Tier:** börsennotierte Unternehmen (DAX/MDAX/SDAX) erhalten eine Firmen-E-Mail (Gmail); nicht gelistete KMU/Startups landen in einer manuellen LinkedIn-Queue (Gründer + kleine Teams sind auf LinkedIn erreichbar — Cold-E-Mail an `info@` verpufft).
- **Copy-Hybrid:** deterministisches Template-Skelett pro Segment + ein LLM-generierter, personalisierter Opener pro Kontakt. 6 Templates insgesamt (3 Segmente × 2 Kanäle), alle inline im Workflow-JSON.
- **Dedup:** jeder Versand schreibt eine Zeile ins `Activity`-Sheet. Der nächste Lauf filtert alle heraus, deren E-Mail oder LinkedIn-URL dort bereits steht — idempotente Wiederholungen.
- **Throttle:** 60 Sekunden Wartezeit zwischen Versendungen (Gmail-Zustellbarkeits-Hygiene).
- **Zwei Trigger:** Manual-Trigger (Demo/Ad-hoc) und Schedule-Trigger (Mo–Fr 09:00 Europe/Berlin) für die laufende Kampagnen-Kadenz.
- **Keine Mocks:** jeder Node ist ein echter Produktions-Node — Credentials einbinden, „Execute" drücken.

### In n8n importieren

**Voraussetzungen**

| Was | Wofür |
|---|---|
| n8n (Cloud oder self-hosted) | Ausführungsumgebung |
| Google Sheet „KGS Outreach" mit 4 Tabs: `Accounts`, `Contacts`, `Outbox_LinkedIn`, `Activity` | Daten-Backbone (Targets, Kontakte, LinkedIn-Queue, Audit-Log) |
| Credential `Google Sheets OAuth2` | Sheet lesen/schreiben |
| Credential `Gmail OAuth2` | E-Mail-Versand |
| Credential `OpenAI API` | LLM-Opener-Generierung |
| Umgebungsvariable `KGS_SHEET_ID` | ID des Google Sheets (der lange String zwischen `/d/` und `/edit` in der Sheet-URL) |

**Schritte**

1. **Importieren:**
   - **n8n Cloud:** Workflows → *Import from File* → `GTM Engineer Case Study/n8n/workflow.json` auswählen.
   - **Self-hosted (CLI):** `n8n import:workflow --input="GTM Engineer Case Study/n8n/workflow.json"`
2. **Credentials binden:** Nach dem Import zeigen die Gmail-, Google-Sheets- und OpenAI-Nodes rote Badges (die Platzhalter-IDs `REPLACE_WITH_YOUR_..._CRED`). Jeden Node anklicken, an die eigenen Credentials binden, **Save**.
3. **`KGS_SHEET_ID` setzen:** self-hosted in der `.env`-Datei; n8n Cloud unter Settings → Variables.
4. **Testdaten laden (optional):** `sample-accounts.csv` und `sample-contacts.csv` (im selben Ordner) in die Tabs `Accounts` bzw. `Contacts` importieren — so lässt sich der Workflow ohne Scraper-Lauf testen.
5. **Ausführen:** Manual-Trigger starten. Mit den Sample-Daten erwartbar: 4 E-Mails via Gmail, 2 Zeilen in `Outbox_LinkedIn`, 6 Zeilen in `Activity`. Zweiter Lauf → 0 neue Zeilen (Dedup funktioniert).

> Der Workflow steht beim Import auf `active: false` und versendet erst nach manuellem Start bzw. Aktivierung des Schedule-Triggers — kein versehentlicher Versand beim Import.

## Projektstruktur

```
gtm-engineer-case-study/      (Repository-Wurzel)
├── README.md                 # diese deutsche Übersicht (GitHub-Startseite)
└── GTM Engineer Case Study/
    ├── scrape.py             # gesamte Pipeline, eine Datei, ~280 Zeilen
    ├── README.md             # englische Fassung (Scraper)
    ├── cache/                # HTTP-Response-Cache (sha256(url).html)
    ├── out/                  # CSVs, eine pro Lauf-Datum
    └── n8n/                  # Outreach-Automatisierung (Aufgabe 2)
        ├── workflow.json     # importierbarer n8n-Workflow
        ├── sample-accounts.csv
        └── sample-contacts.csv
```
