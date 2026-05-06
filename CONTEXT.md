# SalaryCompass — LLM Developer Context

> Read this before touching any code. It captures every architectural decision,
> gotcha, and current state so you can contribute without breaking things.

---

## Resuming on a new machine or new Copilot CLI session

Session checkpoints from Copilot CLI are stored locally and do not travel with the repo.
To restore full context on a new machine, read these two files before starting:

1. **This file** (`CONTEXT.md`) — architecture, data schemas, engine API, gotchas, accuracy status
2. **`.github/copilot-instructions.md`** — project conventions, branching rules, agent coordination guidelines
3. **`CHANGELOG.md`** — chronological history of what was built and when

The `CHANGELOG.md` + `Pending improvements` section at the bottom of this file together
describe the current state and next priorities.

**Quick state summary (as of 2026-05-05):**
- All 4 Compare tab inner tabs fully implemented (Budget/Surplus, 10yr Trajectory, Negotiate ladder, Details)
- Negotiate tab: Target Salary, Move Readiness, Sign-on Bonus, Permit Timeline all live
- 11 cities, 7 countries, 197 tests, deployed on Streamlit Community Cloud
- Open work: GE single_lookup recalibration above CHF 140k

---

## Documentation rule

**After every change to `app.py`, `engine/`, or `data/`, update docs before closing the task:**

| What changed | Update |
|---|---|
| New feature / UI change | `CONTEXT.md` (UI flow, engine functions, data model) |
| New engine function or signature change | `CONTEXT.md` (Key engine functions) |
| New gotcha, known bug, or fix | `CONTEXT.md` (Known gotchas) |
| Tax accuracy changes (anchor update, new country) | `CONTEXT.md` (Tax accuracy table) |
| New city or country YAML | `CONTEXT.md` (architecture, data model) + `README.md` |
| New user-visible capability | `README.md` (feature list) |

Documentation is part of the task — not optional cleanup.

---

## What this app does

SalaryCompass is a Streamlit web app that compares **net income, cost of living,
and 10-year career trajectory** across multiple cities simultaneously.

The user enters their personal situation (gross salary per city, household,
actual monthly expenses, lifestyle) and the app produces:
- A **Income · Cost · Surplus matrix** for all scenario × city combinations
- A **budget breakdown chart** per scenario
- A **full expense table** per scenario
- A **10-year cumulative savings trajectory** with scheme expiry cliffs
- A **negotiation ladder** with exact break-even solver
- A **move readiness card** (cash needed, sign-on recommendation, permit timeline)

---

## Architecture overview

```
salary-compass/
├── app.py                    # All UI logic (Streamlit). ~2,400 lines.
├── requirements.txt          # Pinned deps — used by Streamlit Community Cloud
├── pyproject.toml            # Project metadata + dev deps (ruff, pytest, mypy)
├── runtime.txt               # Python version pin for Streamlit Cloud
├── .streamlit/config.toml    # Theme + server settings
│
├── engine/
│   ├── __init__.py           # Public API exports
│   ├── tax.py                # calculate_net(), find_target_gross(), find_gross_to_match_surplus()
│   ├── budget.py             # calculate_budget_v2(), get_budget_for_city()
│   └── trajectory.py        # 10-year savings projection
│
├── output/
│   ├── charts.py             # Plotly chart builders
│   └── excel.py              # 5-sheet Excel report generator (generate_excel_report())
│
└── data/
    ├── countries/            # Tax + scheme config (ES NL CH GE DE NOR UK)
    │                         # GE = Geneva canton (separate from CH/Zurich)
    └── cities/               # CoL estimates (11 cities)
```

---

## Running the app

```bash
uv sync                    # install all deps including dev
uv run streamlit run app.py
```

For non-developers using plain pip (e.g. Streamlit Cloud):
```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

---

## UI flow (two tabs)

### Tab 1 — 📋 My Setup
1. **Section A — Cities & Salaries**: multiselect cities → per-city card with:
   - Gross annual salary input
   - Bonus % and RSU inputs
   - Monthly travel allowance (local currency, tax-free)
   - Monthly meal vouchers (local currency, tax-free)
   - Active special schemes (30% ruling, Beckham Law, etc.)
   - Salary CAGR slider
   - Net income metric (live preview)
   - 🔧 Override city estimates expander (rent, utilities, health, groceries, transport, eating out)

2. **Section B — My Actual Expenses**: two modes:
   - ⚡ Quick: one total monthly number
   - 📋 Detailed: per-category table with city YAML reference column
   - Switching Quick→Detailed pre-populates categories from YAML proportions
   - Switching Detailed→Quick sums the categories

3. **Section C — Scenarios**: three scenario cards, each with:
   - Custom name
   - Global intensity slider (50–200% of your actual expenses)
   - Per-category fine-tune expanders
   - Live implied total caption e.g. `"Global: 75% → ≈ €2,800/mo"`

### Tab 2 — 📊 Compare (4 inner tabs)

#### 📊 Budget & Surplus
- Income · Cost · Surplus table: one row per scenario, multi-level column headers
  with net income in city header. Cost (grey) + Surplus (green/red bold) per city.
- Drill-down section: scenario radio → stacked budget chart → full expense table

#### 📈 10-Year Trajectory
- Cumulative savings lines for all scenario × city combos
- Year-by-year detail expander
- 5-year & 10-year summary tables
- **⚠️ Tax Scheme Expiry Cliff**: for any city with an expiring scheme (30% ruling, Beckham Law),
  shows the net drop at the cliff year and the exact gross needed post-expiry to maintain
  current net (computed via `find_target_gross`)

#### 🔢 Negotiation Ladder
- Salary range chart showing surplus at each gross level
- **Exact break-even gross** via binary search for all scenarios
- **🏦 Move Readiness**: mandatory deposits, 3-month buffer, moving costs input
- **✈️ Return travel context**: annual home visits × cost shown as monthly impact
- **💼 Sign-on bonus recommendation**: grossed-up relocation cost formula
- **🛂 Permit & Visa Timeline**: EU/EEA path vs Non-EU path, complexity rating, expert notes

#### 📋 Negotiate
The 5th inner tab. Only rendered when `has_actuals` is true and at least one destination city is selected.

**Target Salary** — calls `find_gross_to_match_surplus(home_net, home_exp, dest_exp, country_code, schemes)` per dest city.
Shows current gross, required gross to match home surplus, gap, and local-currency equivalent.

**Move Readiness** — total cash needed on day 1:
- N-month cash buffer (slider, default 3)
- 2-month rent deposit (from `rent_2bed.comfortable` in city YAML)
- One-off relocation costs (slider, default €3,000)

**Sign-on Bonus** — gross sign-on to request:
`net_needed = buffer + deposit + relocation`
`gross_needed = net_needed / (1 - effective_tax_rate)`

**Permit Timeline** — reads `permit.eu_eea` and `permit.non_eu` from city YAML. EU passport toggle.
Shows path description, steps list, timeline in weeks, complexity badge (low / medium / high), government fees, sponsor requirement.

- Per-city: country disclaimer, healthcare model, hidden costs (in local currency), permit summary
- Lifestyle anchors summary
- Household model assumptions
- Property model (if applicable)
- Expense actuals summary

---

## Data model

### City YAML (`data/cities/<slug>.yaml`)
```yaml
name: Rotterdam
country: NL          # must match a data/countries/ file
currency: EUR
cost_of_living:
  rent_2bed:      {generous: 2000, comfortable: 1700, frugal: 1700}
  utilities:      {generous: 300,  comfortable: 300,  frugal: 200}
  health_extra:   {generous: 500,  comfortable: 400,  frugal: 300}
  groceries_2pax: {generous: 800,  comfortable: 700,  frugal: 600}
  transport_2pax: {generous: 200,  comfortable: 200,  frugal: 100}
  eating_out:     {generous: 500,  comfortable: 350,  frugal: 200}
  leisure:        {generous: 200,  comfortable: 100,  frugal: 100}
  misc:           {generous: 250,  comfortable: 200,  frugal: 100}
  travel:         {generous: 350,  comfortable: 350,  frugal: 350, fixed: true}
  personal:       {generous: 700,  comfortable: 700,  frugal: 700, fixed: true}
hidden_costs:
  - {name: "Gemeentebelasting", annual: 700, mandatory: true}
  - {name: "Rental deposit", one_time: 4300, mandatory: true}
career:
  typical_cagr: 0.05
  ceiling_gross_eur: 135000
permit:
  eu_eea:
    timeline: "1–3 weeks"
    steps:
      - "Register at city hall (DigiD + BSN)"
  non_eu:
    timeline: "8–14 weeks"
    steps:
      - "Employer applies for TWV at UWV"
      - "IND processes combined residence + work permit"
  complexity: medium        # low | medium | high
  sponsor_required: true
  costs_eur: 0
  notes: "Key tips and gotchas for this city's permit process."
```

- `comfortable` is the primary baseline used for scaling and overrides.
- `travel` and `personal` are marked `fixed: true` — they are **portable** (don't scale by city).
- `hidden_costs` items can have `monthly`, `annual`, or `one_time` fields; `mandatory: true/false`.
- `permit` section is present on all 11 cities. Schema:
```yaml
permit:
  eu_eea:
    path: "EU/EEA citizens register at municipality — no work permit needed"
    timeline_weeks: 2
    steps:
      - "Register at city hall (DigiD + BSN)"
    notes: "..."
  non_eu:
    path: "Employer-sponsored work + residence permit via IND"
    timeline_weeks: 12
    steps:
      - "Employer applies for TWV at UWV"
      - "IND processes combined residence + work permit"
    complexity: medium        # low | medium | high
    sponsor_required: true
    costs_eur: 0
    notes: "Key tips and gotchas for this city's permit process."
```

### Country YAML (`data/countries/<code>.yaml`)
Two tax calculation methods:

**Bracket method** (NL, DE, UK):
```yaml
income_tax:
  method: brackets             # explicit; also the default if omitted
  personal_allowance: 0        # deducted before bracket calculation
  brackets:
    - {up_to: 38883,  rate: 0.3575}
    - {from: 38883, up_to: 78426, rate: 0.3756}
    - {from: 78426,  rate: 0.495}
  tax_credits:                 # optional — applied after brackets
    - type: phase_out_credit   # e.g. Algemene Heffingskorting (NL)
      max_credit: 3115
      phase_out_start: 29736
      phase_out_end: 78426
      phase_out_rate: 0.06398
    - type: piecewise_credit   # e.g. Arbeidskorting (NL)
      bands:
        - {from: 0,      to: 11965,  base: 0,    rate:  0.08324}
        - {from: 11965,  to: 25845,  base: 996,  rate:  0.31009}
        - {from: 25845,  to: 45592,  base: 5300, rate:  0.01950}
        - {from: 45592,  to: 132920, base: 5685, rate: -0.06510}
        - {from: 132920, to: null,   base: 0,    rate:  0.0}
social_contributions:
  employee:
    - {name: "ZVW nominal premium", monthly_flat: 159}
```

**Lookup method** (ES, CH, GE, NOR):
```yaml
income_tax:
  method: effective_rate_lookup
  marginal_retention: 0.57    # used above highest lookup point
  lookup:
    - {gross: 57500, net_monthly: 3450}
    - {gross: 70000, net_monthly: 4083}
    # ...
```

**Special schemes** (e.g. 30% ruling, Beckham Law):
```yaml
special_schemes:
  - id: nl_30_ruling
    name: "30% Ruling (expat)"
    type: taxable_multiplier
    multiplier: 0.70          # only 70% of gross is taxable
    duration_years: 5

  - id: es_beckham_law
    name: "Beckham Law"
    type: flat_rate_override
    rate: 0.24                # flat IRPF rate on all income
```

---

## Key engine functions

### `engine/tax.py`
```python
calculate_net(gross_annual, country_code, active_schemes=[],
              scheme_overrides=None) -> dict
# scheme_overrides: optional per-scheme field patches, e.g. {"nl_30_ruling": {"multiplier": 0.73}}
#   Used by trajectory to model the NL 30%→27% rate change from Jan 2027.
# Returns:
#   gross_annual, net_annual, net_monthly_local, net_monthly_eur,
#   effective_rate, tax_annual, social_annual, currency, eur_rate, country_code

find_gross_to_match_surplus(
    *, home_net_monthly_eur, home_expenses_eur, dest_expenses_eur,
    country_code, active_schemes=[], scheme_overrides=None
) -> float
# target_net = (home_net - home_exp) + dest_exp  (preserve home surplus)
# Delegates to find_target_gross() binary search.
# Returns LOCAL currency gross for the destination country.
# All monetary inputs in EUR; return value is in local currency (e.g. CHF, NOK).

find_target_gross(target_net_monthly_eur, country_code, active_schemes=[],
                  scheme_overrides=None, tolerance_eur=5.0) -> float
# Binary search (60 iterations): finds the minimum annual gross (in local currency)
# that produces at least target_net_monthly_eur after all taxes and social contributions.
# scheme_overrides passed through to calculate_net (e.g. for 27%-ruling cliff calc).
# Monotonically safe because net is strictly increasing in gross.
# Returns the local-currency gross (e.g. CHF, NOK) as a rounded float.
```

### `engine/budget.py`
```python
get_budget_for_city(
    city_slug, scenario_def, home_city_slug,
    user_expenses_by_cat, lifestyle_anchors_eur,
    pax, partner_net_eur,
    city_overrides={}     # {cat: multiplier_vs_yaml_comfortable}
    settling_factor=0.0   # 0..1, adds NEWCOMER_SENSITIVITIES bump for non-home cities
) -> dict
# Returns: items, total_local, total_eur, hidden_costs, ...

calculate_surplus(net_monthly_eur, budget) -> dict
# Returns: surplus_eur, surplus_pct
# Note: pass adjusted_net_eur = net_monthly_eur + perks_monthly_eur for full picture
```

**Budget resolution for a non-home city (4-tier model):**
1. If user has actuals (`YAML_ABSOLUTE_CATS`): rent, transport, utilities, healthcare → use YAML comfortable directly, never scaled from user's home-city actuals
2. Other categories with actuals → scale from home city via YAML `comfortable` ratios, capped [0.5×, 3.0×], with optional settling factor boost (`NEWCOMER_SENSITIVITIES`)
3. Apply `city_overrides` multipliers (manual overrides from UI)
4. Apply `scenario_def["category_multipliers"]` × `global_pct / 100`
5. Portable categories (`travel`, `personal`) never scale by city

### `engine/trajectory.py`
```python
calculate_trajectory(
    gross_annual, country_code, city_slug,
    category_multipliers, pax, lifestyle_anchors,
    partner_net_monthly_eur,
    cagr=0.05, years=10,
    active_schemes=[], scheme_expiry={},
    expenses_eur=None,          # Year 1 monthly expenses; if None uses category_multipliers
    col_inflation_rate=0.02,
    perks_monthly_eur=0.0,      # fixed monthly tax-free perks added to net each year
    ruling_start_year=2026,     # calendar year of Year 1 — used to trigger rate changes at correct point
) -> list[dict]
# Returns list of 10 dicts:
#   year, gross_annual_local, gross_annual_eur, net_monthly_eur,
#   total_expenses_eur, surplus_monthly_eur, surplus_annual_eur,
#   cumulative_savings_eur, active_schemes, events, effective_rate
# events includes ⚡ rate-change markers (e.g. NL 30%→27% from 2027) and ⚠ expiry markers
```

---

## Household model

- `pax` = 1 or 2 (number of adults in household)
- `PAX_MULTIPLIERS` in `budget.py` — 2pax is baseline (1.0), 1pax reduces each category
- `partner_net_monthly_eur` — partner income offsets shared costs
- Scenarios are expressed as % of user's **actual** monthly expenses (100% = their real spend)
- `perks_monthly_eur` = travel allowance + meal vouchers per city (tax-free, not grossed up)

---

## Known gotchas & fixed bugs

### Pandas ≥ 2.1 — `applymap` renamed to `map`
All `Styler.applymap()` calls must be `.map()`. If you see `AttributeError: 'Styler' object has no attribute 'applymap'`, this is why.

### Streamlit `@st.cache_data` and YAML changes
YAML file changes do NOT hot-reload (only `.py` files do). After any YAML edit, restart the server to clear stale cache.

### Spain tax (ES.yaml)
Uses `effective_rate_lookup` method. The bracket method was giving wrong results (~35.9% effective vs actual ~28%) because it missed three deductions: Social Security deductible from IRPF base, €5,550 mínimo personal credit, and €2,000 work expenses deduction. The lookup table is anchored to validated real-world net: **€57,500 gross → €3,450/mo net**.

### Switzerland EUR/CHF rate
`eur_rate: 0.917` → 1 CHF = 1.091 EUR. All budgets are stored in EUR for comparison.

### Switzerland health insurance — `health_kvg` vs `health_extra`
CH cities (Zurich, Geneva) have **both** keys in their YAML:
- `health_kvg` — mandatory KVG basic insurance (~CHF 500+/person) — the main cost
- `health_extra` — optional VVG supplement (~CHF 130/person)

All other cities use only `health_extra` for their mandatory insurance cost.

The UI always tracks health spend under the `health_extra` session-state key. `_resolve_health_comfortable()` in `budget.py` always returns `health_kvg` comfortable value if present (falling back to `health_extra`), ensuring CH cities' reference values are the dominant KVG cost.

### Geneva vs Zurich — separate country files
Geneva uses `country: GE` (not `CH`). `GE.yaml` contains the Geneva single-tariff (barème 1) lookup table based on LIPP Art. 41 §1 + Ville de Genève 45.5% communal surcharge. `CH.yaml` (used by `zurich.yaml`) uses the Canton ZH lookup table. Never cross the two.

### NL tax credits (2026)
NL uses the bracket method with `tax_credits` in the YAML. Two types:
- `phase_out_credit` — Algemene Heffingskorting (AHK): max €3,115, phases to zero between €29,736–€78,426
- `piecewise_credit` — Arbeidskorting: peaks at €5,685 around €45,592, phases to zero at €132,920

Credits are computed on the `taxable` income (after 30% ruling multiplier, before brackets). `tax_annual = max(0, bracket_tax - credits)`.

The `to: null` in arbeidskorting bands means `to: infinity` — code handles this via `hi_raw = band.get("to"); hi = hi_raw if hi_raw is not None else float("inf")`.

### NL 2026 brackets (3 brackets, not 2)
NL moved to 3 brackets in 2026: 35.75% / 37.56% / 49.50%. Old code used 2023 rates (37.07% / 49.50%). The anchor is now **€85,000 + 30% ruling → ~€5,620/mo net** (not the old €5,095).

### NL 30% ruling → 27% from 1 January 2027
The Dutch government legislated a reduction from 30% to 27% (taxable multiplier 0.70 → 0.73) for **all existing ruling holders** from 1 Jan 2027. This is modelled via:
- `NL.yaml` `nl_30_ruling.rate_change: {calendar_year: 2027, new_multiplier: 0.73}`
- `calculate_net(scheme_overrides={"nl_30_ruling": {"multiplier": 0.73}})` — patches multiplier at call time
- `calculate_trajectory(ruling_start_year=2026)` — triggers the override automatically when `calendar_year >= 2027`
- App shows a separate **⚡ Tax Scheme Rate Change** card (before the expiry cliff) with the negotiation gross needed to compensate
- The `ruling_start_year` input in the city form lets users set their exact start year to get the correct Year N alignment

### `use_container_width` deprecation (Streamlit)
Use `width='stretch'` or `width='content'` for `st.plotly_chart()`, `st.dataframe()`, and `st.button()`. Do NOT pass `use_container_width=True`.

### Non-unique DataFrame index in styling
When applying `.style.apply()` with `axis=None`, use `df.iloc[i, j]` for positional access (not `.loc[label]`) to avoid issues with duplicate or non-unique index values.

### find_target_gross — binary search bounds
Upper bound is 2,000,000 (local currency). Convergence is guaranteed because `calculate_net` is monotonically increasing in gross. Tolerance: 5 EUR. If the target is unreachable (e.g. asking for more than max-gross net), the function returns the upper bound.

---

## Tax accuracy status

| Country | Method  | Status |
|---------|---------|--------|
| ES      | Lookup  | ✅ Validated (€57.5k → €3,450/mo) |
| NL      | Brackets + credits | ✅ Validated 2026 (€85k + 30% ruling → ~€5,620/mo; 3-bracket system + AHK + arbeidskorting) |
| CH (ZH) | Lookup  | ⚠️ Directional only — Canton Zurich rates |
| GE      | Lookup  | ⚠️ Directional — CHF 80k–130k from official LIPP barème 1; CHF 140k+ extrapolated at 60% marginal retention (likely undertaxed ~5–13pp vs real outcomes). `married_lookup` (barème 2) added. Recalibration of CHF 140k+ single lookup recommended — requires official LIPP tariff source from ge.ch. |
| DE      | Lookup  | ✅ Recalculated 2025 (progressive formula, Steuerklasse 1, GKV, no church tax) |
| NOR     | Lookup  | ✅ Recalculated 2025 (Skatteetaten-verified trinnskatt brackets) |
| UK      | Lookup  | ✅ Recalculated 2025/26 (income tax + NI, PA taper captured) |

---

## Profile persistence

Profiles are stored as JSON in `config/profiles/`. Session-state keys included in a save:
- **Exact keys** defined in `_PROFILE_EXACT_KEYS` (see `app.py`)
- **Prefix-matched keys**: `city_*`, `exp_*`, `anchor_*`, `scen_*`, `override_*`

New keys added: `city_travel_<slug>` (travel allowance) and `city_meals_<slug>` (meal vouchers). These are automatically included in profiles because they start with `city_`.

---

## Pending improvements (not yet built)

- **Geneva single_lookup recalibration** — CHF 140k–200k values extrapolated at 60% marginal retention; likely undertaxed vs real outcomes (see GE.yaml disclaimer + tax accuracy table). Requires official LIPP tariff data from ge.ch Quellensteuer tables.

---

## Original use case (context for calibration)

This tool was built for a real decision:
- Current: Madrid, Spain, €57,500 gross (~€3,450/mo net)
- Offer A: Rotterdam, Netherlands, €85,000 + 30% ruling (~€5,620/mo net with 2026 credits)
- Offer B: Zurich, Switzerland, ~CHF 120k (under negotiation)
- User: 30yo, Spanish, cohabiting, sole earner, 2-bed needed, no car

Rotterdam flip-point vs Zurich: ~CHF 115-120k without RSUs.



---

## Household model

- `pax` = 1 or 2 (number of adults in household)
- `PAX_MULTIPLIERS` in `budget.py` — 2pax is baseline (1.0), 1pax reduces each category
- `partner_net_monthly_eur` — partner income offsets shared costs
- Scenarios are expressed as % of user's **actual** monthly expenses (100% = their real spend)

---

## Known gotchas & fixed bugs

### Pandas ≥ 2.1 — `applymap` renamed to `map`
All `Styler.applymap()` calls must be `.map()`. If you see `AttributeError: 'Styler' object has no attribute 'applymap'`, this is why.

### Streamlit `@st.cache_data` and YAML changes
YAML file changes do NOT hot-reload (only `.py` files do). After any YAML edit, restart the server to clear stale cache.

### Spain tax (ES.yaml)
Uses `effective_rate_lookup` method. The bracket method was giving wrong results (~35.9% effective vs actual ~28%) because it missed three deductions: Social Security deductible from IRPF base, €5,550 mínimo personal credit, and €2,000 work expenses deduction. The lookup table is anchored to validated real-world net: **€57,500 gross → €3,450/mo net**.

### Switzerland EUR/CHF rate
`eur_rate: 0.917` → 1 CHF = 1.091 EUR. All budgets are stored in EUR for comparison.

### Switzerland health insurance — `health_kvg` vs `health_extra`
CH cities (Zurich, Geneva) have **both** keys in their YAML:
- `health_kvg` — mandatory KVG basic insurance (~CHF 500+/person) — the main cost
- `health_extra` — optional VVG supplement (~CHF 130/person)

All other cities use only `health_extra` for their mandatory insurance cost.

The UI always tracks health spend under the `health_extra` session-state key. `_resolve_health_comfortable()` in `budget.py` always returns `health_kvg` comfortable value if present (falling back to `health_extra`), ensuring CH cities' reference values are the dominant KVG cost. `distribute_total_to_categories()` absorbs `health_kvg` into the `health_extra` weight bucket — `health_kvg` never appears as a separate key in distribution output.

### `use_container_width` deprecation (Streamlit)
Use `width='stretch'` or `width='content'` for `st.plotly_chart()`. Do NOT pass `use_container_width=True`.

### Non-unique DataFrame index in styling
When applying `.style.apply()` with `axis=None`, use `df.iloc[i, j]` for positional access (not `.loc[label]`) to avoid issues with duplicate or non-unique index values.

---

## Tax accuracy status

| Country | Method       | Status |
|---------|-------------|--------|
| ES      | Lookup      | ✅ Validated (€57.5k → €3,450/mo) |
| NL      | Brackets    | ✅ Validated (€85k + 30% ruling → ~€5,095/mo) |
| CH      | Lookup      | ⚠️ Directional only — canton varies |
| DE      | Lookup      | ✅ Recalculated 2025 (progressive formula, Steuerklasse 1, GKV, no church tax) |
| NOR     | Lookup      | ✅ Recalculated 2025 (Skatteetaten-verified trinnskatt brackets) |
| UK      | Lookup      | ✅ Recalculated 2025/26 (income tax + NI, PA taper captured) |

---

## Pending improvements (not yet built)

- **Push to GitHub + Streamlit Community Cloud** — for sharing via URL

---

## Original use case (context for calibration)

This tool was built for a real decision:
- Current: Madrid, Spain, €57,500 gross (~€3,450/mo net)
- Offer A: Rotterdam, Netherlands, €85,000 + 30% ruling (~€5,095/mo net)
- Offer B: Zurich, Switzerland, ~CHF 120k (under negotiation)
- User: 30yo, Spanish, cohabiting, sole earner, 2-bed needed, no car

Rotterdam flip-point vs Zurich: ~CHF 115-120k without RSUs.
