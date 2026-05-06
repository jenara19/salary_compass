# Changelog

All notable changes to SalaryCompass are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Qualitative city data block** — all 11 city YAMLs now include a `qualitative:` block with
  `safety_score`, `english_friendliness`, `expat_community`, `climate`, `healthcare_quality`,
  `bureaucracy_complexity`, `overall_livability`, and `sources` fields for future UI display.
  Sources: Numbeo 2025, Mercer 2024, EIU Livability Index 2024. (A6)

### Fixed
- **Excel Sheet 2 (Budget Breakdown) silent zeros** — was reading `items[cat]["eur"]` but the
  correct key is `"value_eur"` (aligns with `engine/budget.py`). All budget category cells now
  show real values instead of zero. (`output/excel.py`, B1)
- **Excel Sheet 5 (Assumptions) "Meal vouchers" phantom column** — a header was written at
  column 5 but the data loop only filled column 4. Renamed column 4 header to
  "Tax-free perks/mo" and removed the orphaned "Meal vouchers" header. (`output/excel.py`, B2)
- **Excel Sheet 4 (Negotiation Targets) ignores 30%→27% rate change** — the break-even gross
  calculation now detects active schemes with a `rate_change` block and appends a dedicated
  "Post rate-change break-even" section per city, matching the in-app cliff card. (`output/excel.py`, B3)
- **`_lookup_net` can return negative net** — linear extrapolation below the first lookup
  point is now floored at 0.0 (`max(0.0, ...)`). Prevents nonsense values for very low gross
  inputs in lookup-method countries (ES, CH, GE, NOR). (`engine/tax.py`, B6)
- **Partner "Other" country silently zeroed household income** — sidebar now shows a manual
  "Partner net income (€/mo)" number input when "Other" is selected, so the partner
  contribution flows into surplus and trajectory. (`app.py`, B14)

### Added
- **`FIND_GROSS_UNREACHABLE` sentinel** (`engine/tax.py`) — module-level constant (2,000,000)
  documenting the value returned by `find_target_gross` when the target net is unachievable.
  The negotiate tab now shows a `st.warning` instead of a misleadingly large gross figure. (B5)
- **Property net wired into surplus** — `rental_income − mortgage_monthly` is now included in
  `adjusted_net_eur` for every city, so mortgage holders see accurate surpluses and trajectory
  projections. (`app.py`, A5)
- **`openpyxl`** added to dev dependencies for Excel regression testing.
- **New tests**: `TestExcelBudgetBreakdown` (B1 regression), `TestLookupNetFloor` (B6
  regression), `TestFindGrossUnreachableSentinel` (B5). (`tests/test_excel.py`,
  `tests/test_tax.py`)

### Added
- **Negotiate tab** (5th inner tab in Compare): Target Salary solver, Move Readiness calculator, Sign-on Bonus gross-up, Permit Timeline (EU/EEA and non-EU paths)
- **`find_gross_to_match_surplus()`** engine function — binary-search gross to match home monthly surplus in destination city
- **Geneva married tariff** (`married_lookup`, barème 2) in `GE.yaml`
- **Permit YAML schema** standardised to `eu_eea`/`non_eu` nested structure for all 11 cities
- **Streamlit Community Cloud** deployment config (`runtime.txt`, `requirements.txt`)

### Changed
- `CONTEXT.md` — removed duplicate second half, added Negotiate tab docs, new engine function, permit schema, session-portability guide
- `README.md` — removed duplicate second half, added Streamlit Cloud badge + deploy instructions, uv quick-start
- `.github/copilot-instructions.md` — added parallel agent coordination rules (worktree isolation, pre-flight checklist)

### Removed
- Stale "pending improvements" items that were completed (Geneva married tariff, Streamlit Cloud deploy)

---

## [1.0.0] — 2026-05-05

### Added
- **Tax engines** for NL, ES, DE, CH (Zurich), GE (Geneva), NOR, UK with validated anchor points
- **NL 2026 three-bracket system** (35.75% / 37.56% / 49.50%) with heffingskortingen (AHK + arbeidskorting)
- **NL 30% → 27% ruling** rate change from January 2027 modelled in trajectory with ⚡ cliff card
- **30% Ruling** (Netherlands) and **Beckham Law** (Spain) special tax scheme support
- **11 cities**: Amsterdam, Rotterdam, Barcelona, Madrid, Oslo, London, Manchester, Zurich, Geneva, Munich, Berlin
- **3-scenario cost model** (frugal / comfortable / generous) scaled from user's actual expenses
- **Newcomer adjustments** for rent, eating-out, and city-specific settling-in behaviours
- **10-year savings trajectory** with CoL inflation, salary CAGR, tax scheme expiry cliffs
- **Negotiation ladder**: exact break-even salary via binary search (`find_target_gross`)
- **Move readiness calculator**: mandatory deposits + 3-month buffer + sign-on recommendation
- **Permit & visa timelines** for all 11 cities (EU/EEA and non-EU paths)
- **Tax-free perks** (travel allowance + meal vouchers) per city, threaded through trajectory
- **Excel export** — 5-sheet workbook (Summary, Budget Breakdown, Trajectory, Negotiation Targets, Assumptions)
- **Profile save/load** — persist full setup across sessions as JSON
- **186 tests** across tax engine, budget, trajectory, and Excel modules

[Unreleased]: https://github.com/jenara19/salary_compass/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/jenara19/salary_compass/releases/tag/v1.0.0
