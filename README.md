# 🧭 SalaryCompass

Compare net income, cost of living, and 10-year career trajectory across European cities.

## Countries supported
🇪🇸 Spain · 🇳🇱 Netherlands · 🇨🇭 Switzerland · 🇩🇪 Germany · 🇳🇴 Norway · 🇬🇧 United Kingdom

## Cities
Madrid, Barcelona, Rotterdam, Amsterdam, Zurich, Geneva, Berlin, Munich, Oslo, London, Manchester

## What it does

- **Net income calculator** with validated country-specific tax engines (brackets, credits, lookup tables)
- **Special tax schemes**: 30% Ruling (NL), Beckham Law (ES), with expiry modelling
- **NL 30%→27% ruling change**: Jan-2027 rate reduction modelled in trajectory with ⚡ cliff card and compensation gross
- **Cost-of-living comparison** scaled from your actual expenses, with newcomer adjustments for rent, transport, and healthcare
- **3-scenario model** (frugal / comfortable / generous) with per-category fine-tuning
- **10-year savings trajectory** with salary growth, CoL inflation, and scheme expiry cliff analysis
- **Negotiation tools**: exact break-even salary via binary search, salary ladder chart
- **Move readiness**: mandatory upfront costs, 3-month buffer, sign-on bonus recommendation
- **Permit & visa timeline** for all 11 cities (EU/EEA and non-EU paths)
- **Profile save/load** — persist your setup across sessions
- **Tax-free perks** — travel allowance and meal vouchers per city (threaded through trajectory)
- **Excel export** — ⬇️ Download a 5-sheet workbook (Summary, Budget Breakdown, Trajectory, Negotiation Targets, Assumptions)

## Quick start

```bash
# Python 3.10+ required
pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501 in your browser.

👉 **New to Python or setting this up on a fresh machine? Read [SETUP.md](SETUP.md) for full step-by-step instructions.**

> Use `python -m streamlit` rather than `streamlit run` — the CLI shortcut may not be on PATH.

## For developers / LLMs
Read **[CONTEXT.md](CONTEXT.md)** first. It covers architecture, data schemas, tax engine details, known gotchas, and current state of the app.

## Adding a new city
Create `data/cities/<slug>.yaml` following the schema of any existing city file (including a `permit` section). No code changes needed — the app discovers cities automatically.

## Adding a new country
1. Create `data/countries/XX.yaml` with tax brackets or lookup table
2. Create city YAMLs referencing `country: XX`
3. Restart the app to clear cache

## Design System
UI design tokens, color palette, typography, and component guidelines live in [`docs/DESIGN.md`](docs/DESIGN.md).

## Disclaimer
Directional estimates only. Not financial or tax advice.

Compare net income, cost of living, and 10-year career trajectory across countries.

## Countries supported
🇪🇸 Spain · 🇳🇱 Netherlands · 🇨🇭 Switzerland · 🇩🇪 Germany · 🇳🇴 Norway · 🇬🇧 United Kingdom

## Cities
Madrid, Barcelona, Rotterdam, Amsterdam, Zurich, Geneva, Berlin, Munich, Oslo, London, Manchester

## Quick start

```bash
# Python 3.10+ required
pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501 in your browser.

👉 **New to Python or setting this up on a fresh machine? Read [SETUP.md](SETUP.md) for full step-by-step instructions.**

> Use `python -m streamlit` rather than `streamlit run` — the CLI shortcut may not be on PATH.

## For developers / LLMs
Read **[CONTEXT.md](CONTEXT.md)** first. It covers architecture, data schemas, tax engine details, known gotchas, and current state of the app.

## Adding a new city
Create `data/cities/<slug>.yaml` following the schema of any existing city file. No code changes needed — the app discovers cities automatically.

## Adding a new country
1. Create `data/countries/XX.yaml` with tax brackets or lookup table
2. Create city YAMLs referencing `country: XX`
3. Restart the app to clear cache

## Disclaimer
Directional estimates only. Not financial or tax advice.
