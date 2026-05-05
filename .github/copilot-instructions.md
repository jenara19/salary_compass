# SalaryCompass — Copilot Instructions

## How to run
```bash
pip install -r requirements.txt
python -m streamlit run app.py --server.headless true
```
Use `python -m streamlit` (not `streamlit run`) — the CLI may not be on PATH.

## Project layout
- `app.py` — all UI (Streamlit). Two-tab layout: 📋 My Setup | 📊 Compare.
- `engine/tax.py` — gross-to-net calculation (bracket or lookup method)
- `engine/budget.py` — CoL aggregation, city scaling, surplus calculation
- `engine/trajectory.py` — 10-year savings projection
- `output/charts.py` — Plotly chart builders
- `data/countries/*.yaml` — tax config per country
- `data/cities/*.yaml` — cost-of-living estimates per city

## Validation
```bash
npm run validate   # from repo root if available
python -m py_compile app.py   # quick syntax check
python -m pytest tests/ -q    # run all tests
```

## Documentation — keep it current
**After every change to app.py, engine/, or data/**, update the relevant docs before considering the task done:

| What changed | Update |
|---|---|
| New feature / UI change | `CONTEXT.md` (UI flow, engine functions, data model sections) |
| New engine function or signature change | `CONTEXT.md` (Key engine functions) |
| New gotcha, known bug, or fix | `CONTEXT.md` (Known gotchas) |
| Tax accuracy changes (new country, anchor update) | `CONTEXT.md` (Tax accuracy status table) |
| New city or country YAML | `CONTEXT.md` (architecture overview, data model) + `README.md` |
| New capability visible to users | `README.md` (feature list) |

This is a **hard rule**: documentation is part of the task, not optional cleanup.

## Key conventions
- All monetary comparisons are in **EUR**. Non-EUR cities store `eur_rate` in country YAML.
- Budget baseline = user's actual monthly expenses (Section B). Scenarios are % of that.
- City overrides are stored as multipliers vs YAML `ample`: `override / ample`. They compose with scenario multipliers cleanly.
- `travel` and `personal` are **portable** categories — they don't scale by city.
- Use `pax` (1 or 2) for household size. `PAX_MULTIPLIERS` in `budget.py` defines per-category reductions for 1-person households.

## Critical gotchas
- **pandas ≥ 2.1**: `Styler.applymap()` was renamed to `.map()`. Use `.map()`.
- **Streamlit cache**: `@st.cache_data` caches by argument tuple. YAML changes require a server restart.
- **Styling with non-unique index**: use `df.iloc[i, j]` not `df.loc[label, col]` to avoid KeyErrors.
- **`st.plotly_chart`**: use `width='stretch'` not `use_container_width=True` (deprecated).
- **ES.yaml uses lookup method** (not brackets) — bracket method gives wrong effective rate for Spain due to missing deductions.

## Read CONTEXT.md first
For full architectural detail, data schemas, tax accuracy status, and original use-case context, read `CONTEXT.md` in the project root.
