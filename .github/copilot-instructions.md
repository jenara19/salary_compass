# SalaryCompass — Copilot Instructions

## How to run
```bash
# Install all deps (runtime + dev)
uv sync --dev

# Run the app
python -m streamlit run app.py --server.headless true
```
Use `python -m streamlit` (not `streamlit run`) — the CLI may not be on PATH.

## Project layout
- `app.py` — all UI (Streamlit). Two-tab layout: 📋 My Setup | 📊 Compare.
- `engine/tax.py` — gross-to-net calculation; `calculate_net()`, `find_target_gross()`
- `engine/budget.py` — CoL aggregation, city scaling, surplus calculation
- `engine/trajectory.py` — 10-year savings projection; `calculate_trajectory()`
- `output/charts.py` — Plotly chart builders
- `output/excel.py` — 5-sheet Excel report generator; `generate_excel_report()`
- `data/countries/*.yaml` — tax config per country (NL, ES, DE, CH, GE, NOR, UK)
- `data/cities/*.yaml` — cost-of-living estimates (11 cities)

## Tooling
| Tool | Purpose | Command |
|------|---------|---------|
| `uv` | Package manager | `uv sync --dev` |
| `ruff` | Lint + format | `uv run ruff check . && uv run ruff format .` |
| `mypy` | Type checking | `uv run mypy engine/ output/` |
| `pytest` | Tests + coverage | `uv run python -m pytest` |
| `pre-commit` | Git hook checks | `uv run pre-commit install` |

## CI / CD
- **CI**: GitHub Actions (`.github/workflows/ci.yml`) runs lint → type-check → test on every push/PR to `main`
- **Releases**: Tag with `vX.Y.Z` → `.github/workflows/release.yml` creates a GitHub Release
- **Branch protection**: `main` requires `ci-passed` check and PR approval
- **Dependabot**: weekly updates for Python deps, Actions, Docker base images

## Documentation — keep it current
**After every change to app.py, engine/, or data/**, update the relevant docs before considering the task done:

| What changed | Update |
|---|---|
| New feature / UI change | `CONTEXT.md` (UI flow, engine functions, data model) |
| New engine function or signature change | `CONTEXT.md` (Key engine functions) |
| New gotcha, known bug, or fix | `CONTEXT.md` (Known gotchas) |
| Tax accuracy changes | `CONTEXT.md` (Tax accuracy status table) |
| New city or country YAML | `CONTEXT.md` (architecture, data model) + `README.md` |
| New user-facing capability | `README.md` (feature list) |
| Any release | `CHANGELOG.md` (add entry under `## [Unreleased]`) |

This is a **hard rule**: documentation is part of the task, not optional cleanup.

## Key conventions
- All monetary comparisons are in **EUR**. Non-EUR cities store `eur_rate` in country YAML.
- Budget baseline = user's actual monthly expenses. Scenarios are % of that.
- `travel` and `personal` are **portable** categories — they don't scale by city.
- Use `pax` (1 or 2) for household size. `PAX_MULTIPLIERS` in `budget.py` defines per-category reductions.

## Critical gotchas
- **pandas ≥ 2.1**: `Styler.applymap()` renamed to `.map()`. Use `.map()`.
- **Streamlit cache**: `@st.cache_data` caches by argument tuple. YAML changes require a server restart.
- **`st.plotly_chart`**: use `width='stretch'` not `use_container_width=True` (deprecated).
- **ES.yaml uses lookup method** (not brackets) — bracket method gives wrong effective rate for Spain.
- **NL 2026**: 3-bracket system (35.75% / 37.56% / 49.50%) + AHK + arbeidskorting credits.
- **NL 30%→27%**: ruling rate change from Jan 2027 is modelled via `rate_change` in NL.yaml + `scheme_overrides` in `calculate_net()`.

## Read CONTEXT.md first
For full architectural detail, data schemas, tax accuracy status, and original use-case context, read `CONTEXT.md`.
