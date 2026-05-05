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

## Branching workflow — ALWAYS follow this
This project uses **GitHub Flow**: one long-lived `main` branch; all work happens on short-lived feature branches.

```
main          → production-ready. Protected. No direct pushes. Ever.
feature/*     → branch from main, open PR back to main when done
hotfix/*      → branch from main for urgent fixes, PR back immediately
experiment/*  → exploratory, may never merge
```

### Every task follows these steps
1. `git checkout main && git pull` — start from latest main
2. `git checkout -b feature/<short-description>` — create a branch
3. Make changes, commit with Conventional Commits format (see below)
4. `git push -u origin feature/<short-description>`
5. Open a PR → CI must go green → merge to main
6. `git checkout main && git pull && git branch -d feature/<short-description>`

### Conventional commit format
```
feat:     new feature (calc, chart, tab, city, country)
fix:      bug fix or calculation correction
update:   modify existing behaviour (not a bug)
docs:     documentation only
refactor: restructuring without behaviour change
chore:    tooling, config, dependencies
remove:   delete obsolete files
wip:      work in progress (use on feature branch, squash before merge)
```
Example: `feat: add pension contribution modelling for DE`

**Never use `git push --force` on `main`.** Force-push is allowed only on your own feature branch.

## Parallel agent work — rules that MUST be followed

Concurrent agents sharing one git working tree cause branch/index corruption, lost work, and wasted recovery time. These rules are **mandatory** before spawning any background agent.

### Pre-flight checklist (run before spawning agents)
1. **Validate push credentials** — run `git push --dry-run origin HEAD` before spawning a single agent. If it fails with 403, resolve the credential issue first. Do not spawn any agent until pushes succeed.
2. **Verify a clean working tree** — `git status` must show `nothing to commit, working tree clean`. Stash or commit any dirty state first.
3. **Confirm main is up to date** — `git pull origin main` before creating any branches.

### One working directory per agent — use git worktrees
Never give two agents the same working directory path. Use `git worktree` to give each agent its own isolated checkout:

```powershell
# Before spawning agent for feature/X:
git worktree add C:\Personal\salary-compass-wt\feature-X feature/feature-X
# Agent works in:  C:\Personal\salary-compass-wt\feature-X
# After PR merges:
git worktree remove C:\Personal\salary-compass-wt\feature-X
```

Each worktree has its own HEAD and index — agents cannot corrupt each other's staged changes.

### Scope agents to non-overlapping files
Before spawning, list exactly which files each agent may touch. If two agents need to touch the same file, they must be **sequential** (second agent branches after the first merges), never parallel.

| ✅ Safe to parallelize | ❌ Must be sequential |
|---|---|
| Agent A: `engine/tax.py` / Agent B: `data/cities/*.yaml` | Agent A + B both touching `app.py` |
| Agent A: `docs/` / Agent B: `tests/` | Agent A + B both touching the same YAML |

### Agent prompt requirements
Every agent prompt must include:
- **Working directory**: the full absolute path (the worktree path, not the main repo)
- **Branch name**: exact name to create (`feature/X`)
- **Files in scope**: explicit list of files the agent may create/edit/delete
- **Files out of scope**: "Do NOT touch any file outside the scope list above"
- **Credential check**: "Run `git push --dry-run origin HEAD` first. If it fails, report the error and stop — do not commit any work."
- **Pre-commit validation**: exact commands to run before committing (`uv run ruff check`, `uv run mypy`, `uv run pytest`)

### Parallelism limit
- **Maximum 3 concurrent agents** on a single repo. Beyond that, coordination overhead exceeds the time saved.
- Prefer **2 well-scoped agents** over **5 loosely-scoped agents**.
- If a task takes < 15 minutes to do directly, do it yourself — don't delegate.

## CI / CD
- **CI**: GitHub Actions (`.github/workflows/ci.yml`) runs lint → type-check → test on every push/PR
- **Gate**: the `ci-passed` job is the only required check — branch protection targets this name
- **Releases**: tag with `vX.Y.Z` → `.github/workflows/release.yml` creates a GitHub Release + CHANGELOG extract
- **Dependabot**: weekly updates for Python deps, Actions, and Docker base images (auto-PRs)

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

## Design reference
When making any UI changes to `app.py` (colours, spacing, typography, component style), consult `docs/DESIGN.md` first. It defines the General Intelligence Company design system — colour tokens, type scale, spacing, shadows, and component patterns that govern visual decisions.
