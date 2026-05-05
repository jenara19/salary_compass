"""
SalaryCompass v3 — Net income & cost-of-living comparison across countries.
Two-tab UX: 📋 My Setup | 📊 Compare
"""
import json
import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from engine import calculate_net, calculate_budget, calculate_trajectory
from engine.budget import (
    calculate_budget_v2, calculate_surplus, list_cities, load_city,
    DISPLAY_LABELS, scale_expenses_to_city, distribute_total_to_categories,
    _resolve_health_comfortable,
)
from engine.tax import load_country, get_schemes, find_target_gross
from output.charts import (
    surplus_bar_chart, trajectory_line_chart,
    budget_breakdown_chart, negotiation_ladder_chart,
)

st.set_page_config(
    page_title="SalaryCompass",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design system injection ────────────────────────────────────────────────────

def _inject_css() -> None:
    css_path = Path(__file__).parent / "assets" / "style.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

_inject_css()

# ── Profile persistence ────────────────────────────────────────────────────────

PROFILE_DIR = Path(__file__).parent / "config" / "profiles"

# Exact session-state keys to include in a saved profile
_PROFILE_EXACT_KEYS = {
    "selected_cities",
    "expense_mode", "user_total_expenses", "col_inflation_pct", "settling_pct",
    "partner_country", "partner_gross_local", "partner_employed",
    "own_property", "mortgage_monthly", "rental_income",
    "user_age", "current_country", "user_relationship", "user_children",
}
# Session-state key prefixes to include
_PROFILE_PREFIXES = ("city_", "exp_", "anchor_", "scen_", "override_")


def _profile_state_snapshot() -> dict:
    """Collect all saveable session-state keys into a plain dict."""
    state = {}
    for k, v in st.session_state.items():
        if k in _PROFILE_EXACT_KEYS or any(k.startswith(p) for p in _PROFILE_PREFIXES):
            try:
                json.dumps(v)  # only keep JSON-serialisable values
                state[k] = v
            except (TypeError, ValueError):
                pass
    return state


def _profile_filename(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "- _" else "_" for c in name).strip("_")
    return PROFILE_DIR / f"{safe}.json"


def _list_profiles() -> list[str]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profiles = []
    for p in sorted(PROFILE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            profiles.append(data.get("name", p.stem))
        except Exception:
            pass
    return profiles


def _save_profile(name: str) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile = {
        "version": 1,
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "state": _profile_state_snapshot(),
    }
    _profile_filename(name).write_text(json.dumps(profile, indent=2), encoding="utf-8")


def _load_profile(name: str) -> dict | None:
    path = _profile_filename(name)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Fallback: scan all files for matching name field
    for p in PROFILE_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("name") == name:
                return data
        except Exception:
            pass
    return None


def _delete_profile(name: str) -> bool:
    path = _profile_filename(name)
    if path.exists():
        path.unlink()
        return True
    return False


# ── Apply pending profile (must run before any widget renders) ─────────────────
# When the user clicks "Load", we store the profile state under _pending_profile
# and rerun. On the very next run this block fires before any widget, so all
# session-state keys are set before their widgets are drawn.

if "_pending_profile" in st.session_state:
    _profile_data = st.session_state.pop("_pending_profile")
    # Guard: only keep city names that still exist in CITY_OPTIONS (loaded below)
    # We do the city filtering after CITY_OPTIONS is defined; store temporarily.
    st.session_state["_profile_to_apply"] = _profile_data


UI_CAT_KEYS = [
    "rent_2bed", "utilities", "health_extra",
    "groceries_2pax", "transport_2pax", "eating_out",
    "leisure", "misc", "travel", "personal",
]

CITY_VAR_CATS = [
    "rent_2bed", "utilities", "health_extra",
    "groceries_2pax", "transport_2pax", "eating_out",
    "leisure", "misc",
]

PORTABLE_CATS = ["travel", "personal"]

CAT_EMOJIS = {
    "rent_2bed":      "🏠",
    "utilities":      "⚡",
    "health_extra":   "🏥",
    "health_kvg":     "🏥",
    "groceries_2pax": "🛒",
    "transport_2pax": "🚌",
    "eating_out":     "🍽️",
    "leisure":        "🎭",
    "misc":           "🧾",
    "travel":         "✈️",
    "personal":       "👤",
}

UI_CAT_LABELS = {
    "rent_2bed":      "Rent",
    "utilities":      "Utilities",
    "health_extra":   "Health",
    "groceries_2pax": "Groceries",
    "transport_2pax": "Transport",
    "eating_out":     "Eating out",
    "leisure":        "Leisure",
    "misc":           "Misc",
    "travel":         "Travel",
    "personal":       "Personal",
}

SCENARIO_DEFAULTS = [
    {"name": "Frugal",      "global": 75},
    {"name": "Comfortable", "global": 100},
    {"name": "Generous",    "global": 130},
]

SUPPORTED_COUNTRIES = ["NL", "DE", "CH", "ES", "UK", "NOR", "Other"]

# ── Cache helpers ──────────────────────────────────────────────────────────────

@st.cache_data
def get_cities():
    return list_cities()

@st.cache_data
def get_city_options():
    cities = get_cities()
    return {f"{c['name']} ({c['country']})": c["slug"] for c in cities}

@st.cache_data
def get_city_data(city_slug):
    return load_city(city_slug)

@st.cache_data
def get_country_data(code):
    return load_country(code)

@st.cache_data
def get_available_schemes(country_code):
    return get_schemes(country_code)

@st.cache_data
def cached_calculate_net(gross, country_code, active_schemes_tuple):
    return calculate_net(gross, country_code, list(active_schemes_tuple))

@st.cache_data
def cached_budget_v2(city_slug, cat_mults_tuple, pax, anchors_tuple, partner_net):
    return calculate_budget_v2(
        city_slug, dict(cat_mults_tuple), pax, dict(anchors_tuple), partner_net
    )

@st.cache_data
def cached_trajectory(
    gross, country_code, city_slug,
    cat_mults_tuple, pax, anchors_tuple, partner_net,
    cagr, active_schemes_tuple, scheme_expiry_tuple,
    expenses_eur=None,
    col_inflation_rate=0.02,
    perks_monthly_eur=0.0,
    ruling_start_year=2026,
):
    return calculate_trajectory(
        gross_annual=gross,
        country_code=country_code,
        city_slug=city_slug,
        category_multipliers=dict(cat_mults_tuple),
        pax=pax,
        lifestyle_anchors=dict(anchors_tuple),
        partner_net_monthly_eur=partner_net,
        cagr=cagr,
        active_schemes=list(active_schemes_tuple),
        scheme_expiry=dict(scheme_expiry_tuple),
        expenses_eur=expenses_eur,
        col_inflation_rate=col_inflation_rate,
        perks_monthly_eur=perks_monthly_eur,
        ruling_start_year=ruling_start_year,
    )

@st.cache_data
def cached_scale_expenses(user_expenses_tuple, home_city_slug, target_city_slug, pax, settling_factor):
    return scale_expenses_to_city(
        dict(user_expenses_tuple), home_city_slug, target_city_slug, {},
        pax=pax, settling_factor=settling_factor,
    )

@st.cache_data
def cached_distribute(total_eur, city_slug, pax):
    return distribute_total_to_categories(total_eur, city_slug, pax)

CITY_OPTIONS = get_city_options()

# Apply pending profile (deferred from the top-of-script block above)
if "_profile_to_apply" in st.session_state:
    _pdata = st.session_state.pop("_profile_to_apply")
    _city_states = _pdata.get("selected_cities", [])
    _pdata["selected_cities"] = [c for c in _city_states if c in CITY_OPTIONS]
    for _k, _v in _pdata.items():
        st.session_state[_k] = _v

# ── Session-state init ─────────────────────────────────────────────────────────

def _init_ss():
    for i, d in enumerate(SCENARIO_DEFAULTS):
        if f"scen_name_{i}" not in st.session_state:
            st.session_state[f"scen_name_{i}"] = d["name"]
        if f"scen_global_{i}" not in st.session_state:
            st.session_state[f"scen_global_{i}"] = d["global"]
        for cat in UI_CAT_KEYS:
            if f"scen_cat_{i}_{cat}" not in st.session_state:
                st.session_state[f"scen_cat_{i}_{cat}"] = d["global"]

_init_ss()

# ── Callbacks ──────────────────────────────────────────────────────────────────

def _sync_cats(idx: int):
    new_global = st.session_state[f"scen_global_{idx}"]
    for cat in UI_CAT_KEYS:
        st.session_state[f"scen_cat_{idx}_{cat}"] = new_global

# ── Scenario builder ───────────────────────────────────────────────────────────

def _build_scenarios() -> list[dict]:
    result = []
    for i in range(3):
        cat_mults = {}
        for cat in UI_CAT_KEYS:
            scen_val = st.session_state.get(f"scen_cat_{i}_{cat}", 100) / 100
            cat_mults[cat] = round(scen_val, 4)
        if "health_extra" in cat_mults:
            cat_mults["health_kvg"] = cat_mults["health_extra"]
        result.append({
            "idx": i,
            "name": st.session_state.get(f"scen_name_{i}") or SCENARIO_DEFAULTS[i]["name"],
            "global_pct": st.session_state.get(f"scen_global_{i}", SCENARIO_DEFAULTS[i]["global"]),
            "category_multipliers": cat_mults,
        })
    return result

# ── Budget builder from user actuals ──────────────────────────────────────────

def _build_actuals_budget(
    city_slug: str,
    user_expenses_eur: dict,
    lifestyle_anchors_eur: dict,
    pax: int,
    partner_net_eur: float,
) -> dict:
    """Build a budget dict from pre-computed per-city EUR expenses."""
    city    = get_city_data(city_slug)
    country = get_country_data(city["country"])
    eur_rate = country["eur_rate"]

    items = {}
    total_eur = 0.0

    for cat, eur_val in user_expenses_eur.items():
        label = DISPLAY_LABELS.get(cat, cat.replace("_", " ").title())
        items[cat] = {
            "label": label,
            "value_local": round(eur_val / eur_rate if eur_rate != 1.0 else eur_val),
            "value_eur": round(eur_val),
            "fixed": cat in PORTABLE_CATS,
            "note": "Portable (user actuals)" if cat in PORTABLE_CATS else "User actuals (scaled)",
        }
        total_eur += eur_val

    lifestyle_total_eur = 0.0
    for anchor_name, eur_amount in lifestyle_anchors_eur.items():
        if eur_amount > 0:
            local_amount = eur_amount / eur_rate
            items[f"lifestyle_{anchor_name.lower()}"] = {
                "label": f"🎯 {anchor_name}",
                "value_local": round(local_amount),
                "value_eur": round(eur_amount),
                "fixed": True,
                "note": "Lifestyle anchor (portable expense)",
            }
            total_eur += eur_amount
            lifestyle_total_eur += eur_amount

    partner_contrib_eur = 0.0
    if partner_net_eur > 0:
        partner_contrib_eur = partner_net_eur / 2
        partner_local = partner_contrib_eur / eur_rate
        items["partner_contribution"] = {
            "label": "💑 Partner contribution (−)",
            "value_local": round(-partner_local),
            "value_eur": round(-partner_contrib_eur),
            "fixed": False,
            "note": "Partner covers half of shared household costs",
        }
        total_eur -= partner_contrib_eur

    total_local = total_eur / eur_rate if eur_rate != 1.0 else total_eur
    return {
        "city": city["name"],
        "country": city["country"],
        "currency": city["currency"],
        "eur_rate": eur_rate,
        "scenario": "user_actuals",
        "items": items,
        "total_local": round(total_local),
        "total_eur": round(total_eur),
        "hidden_costs": city.get("hidden_costs", []),
        "lifestyle_total_eur": round(lifestyle_total_eur),
        "partner_contrib_eur": round(partner_contrib_eur),
    }


def get_budget_for_city(
    city_slug: str,
    scenario_def: dict,
    home_city_slug,
    user_expenses_by_cat: dict,
    lifestyle_anchors_eur: dict,
    pax: int,
    partner_net_eur: float,
    city_overrides: dict = None,
    settling_factor: float = 0.5,
) -> dict:
    """Get budget for a city. Uses actuals when available, falls back to YAML.
    city_overrides: {cat: multiplier_vs_yaml_comfortable} — e.g. {"rent_2bed": 1.18} means
    the user set rent to 118% of the YAML ample value.
    """
    from engine.budget import YAML_ABSOLUTE_CATS, _resolve_health_comfortable

    city_overrides = city_overrides or {}
    anchors_tuple  = tuple(sorted(lifestyle_anchors_eur.items()))

    # Merge city overrides into scenario multipliers so they apply to YAML-based path
    base_mults  = scenario_def["category_multipliers"]
    global_mult = scenario_def["global_pct"] / 100
    all_cats    = set(list(base_mults.keys()) + list(city_overrides.keys()))
    effective_mults = {
        cat: base_mults.get(cat, global_mult) * city_overrides.get(cat, 1.0)
        for cat in all_cats
    }
    cat_mults_t = tuple(sorted(effective_mults.items()))

    has_actuals = bool(home_city_slug and sum(user_expenses_by_cat.values()) > 0)
    if not has_actuals:
        return cached_budget_v2(city_slug, cat_mults_t, pax, anchors_tuple, partner_net_eur)

    if city_slug == home_city_slug:
        # Home city: actuals are the baseline, city overrides not needed
        scaled_eur = {
            cat: val * base_mults.get(cat, global_mult)
            for cat, val in user_expenses_by_cat.items()
        }
    else:
        base = cached_scale_expenses(
            tuple(sorted(user_expenses_by_cat.items())),
            home_city_slug, city_slug, pax, settling_factor,
        )
        city_data    = get_city_data(city_slug)
        country_data = get_country_data(city_data["country"])
        eur_rate     = country_data["eur_rate"]
        city_col     = city_data["cost_of_living"]
        scaled_eur = {}
        for cat, item in base["items"].items():
            s_mult = base_mults.get(cat, global_mult)

            # Resolve override key: health_extra ↔ health_kvg are aliases
            override_key = cat
            if cat not in city_overrides:
                alias = "health_kvg" if cat == "health_extra" else (
                    "health_extra" if cat == "health_kvg" else None
                )
                if alias and alias in city_overrides:
                    override_key = alias

            if override_key in city_overrides:
                # User explicitly overrode this category: YAML ample × override × scenario
                yaml_comfortable = (
                    city_col.get(cat, {}).get("comfortable", 0) or
                    city_col.get(override_key, {}).get("comfortable", 0) or 0
                )
                scaled_eur[cat] = yaml_comfortable * eur_rate * city_overrides[override_key] * s_mult
            else:
                scaled_eur[cat] = item["value_eur"] * s_mult

    return _build_actuals_budget(city_slug, scaled_eur, lifestyle_anchors_eur, pax, partner_net_eur)

# ── Color helper ───────────────────────────────────────────────────────────────

def _color_surplus(val):
    if isinstance(val, (int, float)):
        color = "#d4edda" if val >= 0 else "#f8d7da"
        return f"background-color: {color}"
    return ""

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(
        """
        <div class="sc-brand">
          <div class="sc-brand-icon">🧭</div>
          <div>
            <div class="sc-brand-text">SalaryCompass</div>
            <div class="sc-brand-sub">Net income · Cost of living</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("**👤 About You**")
    age              = st.number_input("Age", min_value=22, max_value=65, value=st.session_state.get("user_age", 30), key="user_age")
    current_country  = st.selectbox("Current country of residence", SUPPORTED_COUNTRIES, key="current_country")
    relationship     = st.radio(
        "Relationship status",
        ["Single", "Cohabiting", "Married/Civil partnership"],
        horizontal=True,
        key="user_relationship",
    )
    children = st.number_input("Dependent children", min_value=0, max_value=10, value=st.session_state.get("user_children", 0), key="user_children")
    pax = 2 if relationship in ("Cohabiting", "Married/Civil partnership") else 1
    st.caption(f"Budget for **{pax} {'person' if pax == 1 else 'people'}**")

    st.divider()

    with st.expander("🏠 Property & Partner"):
        own_property = st.checkbox("I own property", key="own_property")
        if own_property:
            mortgage_monthly = st.number_input(
                "Monthly mortgage (€/mo)", min_value=0, step=50, value=0,
                key="mortgage_monthly",
            )
            rental_income = st.number_input(
                "Expected rental income if you relocate (€/mo)",
                min_value=0, step=50, value=0,
                help="Leave 0 if you'd keep the property empty or sell.",
                key="rental_income",
            )
        else:
            mortgage_monthly = 0
            rental_income    = 0

        partner_net_monthly = 0.0
        if pax == 2:
            partner_employed = st.checkbox("Partner is employed", key="partner_employed")
            if partner_employed:
                partner_country = st.selectbox(
                    "Partner's work country", SUPPORTED_COUNTRIES, key="partner_country",
                )
                if partner_country != "Other":
                    try:
                        _pdata = get_country_data(partner_country)
                        _pccy  = _pdata["currency"]
                        _prate = _pdata["eur_rate"]  # 1 local = X EUR
                    except Exception:
                        _pccy, _prate = "EUR", 1.0

                    _pgross_local = st.number_input(
                        f"Partner gross salary ({_pccy}/yr)",
                        min_value=0, step=1000,
                        value=int(50000 / _prate) if _prate else 50000,
                        key="partner_gross_local",
                    )
                    if _pccy != "EUR":
                        st.caption(
                            f"≈ €{_pgross_local * _prate:,.0f}/yr equivalent "
                            f"(1 {_pccy} = €{_prate:.3f})"
                        )
                    try:
                        pnet = cached_calculate_net(_pgross_local, partner_country, ())
                        partner_net_monthly = pnet["net_monthly_eur"]
                        if _pccy == "EUR":
                            st.caption(f"Partner net: ≈ **€{partner_net_monthly:,.0f}/month**")
                        else:
                            st.caption(
                                f"Partner net: ≈ **{_pccy} {pnet['net_monthly_local']:,}/month** "
                                f"(€{partner_net_monthly:,.0f}/month)"
                            )
                    except Exception:
                        st.caption("Could not calculate partner net — check country.")

    st.divider()

    extra_context = st.text_area(
        "💬 Anything else to consider?",
        placeholder="e.g. pre-IPO equity, visa concerns, career pivot, specific worries...",
        height=80,
    )

    st.divider()
    st.caption("📋 All figures are directional estimates. Consult a tax adviser before making decisions.")

    # ── Profiles ──────────────────────────────────────────────────────────────
    st.divider()
    with st.expander("💾 Profiles", expanded=False):
        _profiles = _list_profiles()

        st.markdown("**Load a profile**")
        if _profiles:
            _sel = st.selectbox(
                "Saved profiles",
                _profiles,
                key="_profile_selector",
                label_visibility="collapsed",
            )
            _c1, _c2 = st.columns(2)
            with _c1:
                if st.button("▶ Load", width="stretch", key="_btn_load_profile"):
                    _prof = _load_profile(_sel)
                    if _prof:
                        st.session_state["_pending_profile"] = _prof.get("state", {})
                        st.rerun()
                    else:
                        st.error("Profile file not found.")
            with _c2:
                if st.button("🗑 Delete", width="stretch", key="_btn_delete_profile"):
                    _delete_profile(_sel)
                    st.rerun()
        else:
            st.caption("No saved profiles yet.")

        st.markdown("**Save current setup**")
        _new_name = st.text_input(
            "Profile name",
            key="_new_profile_name",
            placeholder='e.g. "My Europe comparison"',
        )
        if st.button("💾 Save", width="stretch", key="_btn_save_profile"):
            _name_to_save = st.session_state.get("_new_profile_name", "").strip()
            if _name_to_save:
                _save_profile(_name_to_save)
                st.rerun()
            else:
                st.warning("Enter a profile name first.")

# ── Main title ─────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div class="sc-hero">
      <div class="sc-hero-badge"><span>&#x1F30D; Salary Intelligence</span></div>
      <div class="sc-hero-title">SalaryCompass</div>
      <p class="sc-hero-sub">
        Compare net income, cost of living, and 10-year savings trajectories
        across European cities — before you sign anything.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Top-level tabs ─────────────────────────────────────────────────────────────

tab_setup, tab_compare = st.tabs(["📋 My Setup", "📊 Compare"])

# Initialise shared variables — both tab blocks run every render, so variables
# defined inside tab_setup are available when tab_compare executes below.
city_inputs:          dict = {}
selected_city_slugs:  list = []
home_city_slug              = None
user_total:           int   = 0
user_expenses_by_cat: dict  = {}
lifestyle_anchors_eur: dict = {}

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: MY SETUP
# ═══════════════════════════════════════════════════════════════════════════════

with tab_setup:

    # ── Section A: Cities & Salaries ──────────────────────────────────────────

    st.header("🌍 Cities & Salaries")

    _default_cities = [k for k in ["Madrid (ES)", "Rotterdam (NL)"] if k in CITY_OPTIONS]
    selected_city_displays = st.multiselect(
        "Select cities to compare",
        options=list(CITY_OPTIONS.keys()),
        default=_default_cities,
        key="selected_cities",
    )
    selected_city_slugs = [CITY_OPTIONS[d] for d in selected_city_displays]
    home_city_slug      = selected_city_slugs[0] if selected_city_slugs else None

    if selected_city_slugs:
        _chunks = [selected_city_slugs[i:i+4] for i in range(0, len(selected_city_slugs), 4)]
        for chunk in _chunks:
            city_cols = st.columns(len(chunk))
            for j, (city_slug, col) in enumerate(zip(chunk, city_cols)):
                city_data    = get_city_data(city_slug)
                country_code = city_data["country"]
                country_data = get_country_data(country_code)
                currency     = country_data["currency"]
                default_cagr = float(city_data.get("career", {}).get("typical_cagr", 0.05)) * 100
                is_home      = (city_slug == home_city_slug)

                with col:
                    home_badge = "  📍" if is_home else ""
                    st.markdown(f"**{city_data['name']}** `{currency}`{home_badge}")
                    if is_home:
                        st.caption("📍 Home city — expenses scale from here")
                    if city_data.get("career", {}).get("company"):
                        st.caption(city_data["career"]["company"])

                    gross = st.number_input(
                        f"Gross salary ({currency}/yr)",
                        min_value=10_000, max_value=1_000_000,
                        value=[57_500, 85_000, 120_000, 130_000][j % 4],
                        step=1_000,
                        key=f"city_gross_{city_slug}",
                    )
                    bonus_pct = st.number_input(
                        "Bonus %", min_value=0, max_value=100, value=0,
                        key=f"city_bonus_{city_slug}",
                    )
                    rsu = st.number_input(
                        f"Annual RSU ({currency})", min_value=0, max_value=500_000,
                        value=0, step=1_000,
                        key=f"city_rsu_{city_slug}",
                        help="RSU/equity vest added to effective gross for tax.",
                    )

                    available_schemes = get_available_schemes(country_code)
                    active_schemes    = []
                    for scheme in available_schemes:
                        if st.checkbox(
                            f"✓ {scheme['name']}",
                            key=f"city_scheme_{city_slug}_{scheme['id']}",
                            help=scheme.get("description", ""),
                        ):
                            active_schemes.append(scheme["id"])

                    scheme_expiry = {}
                    ruling_start_year = 2026
                    if "nl_30_ruling" in active_schemes:
                        expiry_yr = st.slider(
                            "Ruling expires after year", 1, 8, 5,
                            key=f"city_ruling_{city_slug}",
                        )
                        scheme_expiry["nl_30_ruling"] = expiry_yr
                        ruling_start_year = st.number_input(
                            "Ruling start (calendar year)",
                            min_value=2020, max_value=2035, value=2026, step=1,
                            key=f"city_ruling_start_{city_slug}",
                            help="Calendar year you started (or will start) the 30% ruling. "
                                 "Determines when the 2027 rate cut (27%) takes effect in the projection.",
                        )

                    cagr = st.slider(
                        "Salary CAGR %/yr",
                        min_value=0.0, max_value=15.0,
                        value=round(default_cagr, 1), step=0.5,
                        key=f"city_cagr_{city_slug}",
                    ) / 100

                    company = st.text_input(
                        "Company (optional)", key=f"city_company_{city_slug}",
                        placeholder="e.g. Booking.com",
                    )

                    travel_allowance = st.number_input(
                        f"Travel allowance ({currency}/mo, tax-free)",
                        min_value=0, max_value=round(5000 / max(country_data["eur_rate"], 0.001)),
                        value=st.session_state.get(f"city_travel_{city_slug}", 0),
                        step=25,
                        key=f"city_travel_{city_slug}",
                        help=(
                            "Monthly travel reimbursement (OV card, km allowance). "
                            "Tax-free — added directly to disposable income. "
                            "NL: €0.23/km or full OV card. DE: up to €4,500/yr."
                        ),
                    )
                    meal_vouchers = st.number_input(
                        f"Meal vouchers / allowance ({currency}/mo, tax-free)",
                        min_value=0, max_value=round(2000 / max(country_data["eur_rate"], 0.001)),
                        value=st.session_state.get(f"city_meals_{city_slug}", 0),
                        step=25,
                        key=f"city_meals_{city_slug}",
                        help=(
                            "Lunch/meal allowance or vouchers (e.g. Ticket Restaurant, Edenred). "
                            "Tax-free benefit — added directly to disposable income."
                        ),
                    )
                    perks_monthly_eur = (travel_allowance + meal_vouchers) * country_data["eur_rate"]

                    effective_gross = gross * (1 + bonus_pct / 100) + rsu

                    # ── Net income preview ──────────────────────────────────
                    _net = cached_calculate_net(effective_gross, country_code, tuple(active_schemes))
                    _net_mo = _net["net_monthly_eur"]
                    _net_local = _net["net_monthly_local"]
                    _eff = round(_net["effective_rate"] * 100, 1)
                    if currency == "EUR":
                        st.metric("Net / month", f"€{_net_mo:,}", help=f"Effective rate: {_eff}%")
                    else:
                        st.metric("Net / month",
                                  f"{currency} {_net_local:,}",
                                  delta=f"≈ €{_net_mo:,}",
                                  help=f"Effective rate: {_eff}%")

                    # ── Override city cost estimates ─────────────────────────
                    with st.expander("🔧 Override city cost estimates"):
                        st.caption(
                            "Check ✅ a category to lock in a custom value. "
                            "Unchecked rows use the app's computed estimate (YAML-based or actuals-scaled). "
                            "Health insurance always uses the YAML estimate — it reflects the local system."
                        )
                        _col = city_data.get("cost_of_living", {})
                        _eur_rate = country_data["eur_rate"]  # 1 local = X EUR
                        _override_cats = [
                            ("rent_2bed",      "🏠 Rent (2-bed)", 0, round(10000 / _eur_rate)),
                            ("utilities",      "⚡ Utilities",     0, round(2000  / _eur_rate)),
                            ("health_extra",   "🏥 Health ins.",   0, round(4000  / _eur_rate)),
                            ("groceries_2pax", "🛒 Groceries",     0, round(3000  / _eur_rate)),
                            ("transport_2pax", "🚌 Transport",      0, round(1000  / _eur_rate)),
                            ("eating_out",     "🍽️ Eating out",    0, round(3000  / _eur_rate)),
                        ]
                        city_overrides = {}
                        for _cat, _lbl, _lo, _hi in _override_cats:
                            # health_kvg is CH cities' alias for health_extra — try both keys
                            _alias = "health_kvg" if _cat == "health_extra" else None
                            _yaml_val = (
                                _col.get(_cat, {}).get("comfortable", 0)
                                or (_alias and _col.get(_alias, {}).get("comfortable", 0))
                                or 0
                            )
                            # Which key is actually in the YAML (for storing the override)
                            _effective_cat = (
                                _cat if _col.get(_cat)
                                else (_alias if _alias and _col.get(_alias) else _cat)
                            )
                            if _yaml_val == 0:
                                continue
                            _lock_key = f"override_lock_{city_slug}_{_effective_cat}"
                            _val_key  = f"override_{city_slug}_{_effective_cat}"
                            _c1, _c2 = st.columns([1, 6])
                            with _c1:
                                _locked = st.checkbox(
                                    "Lock", key=_lock_key, label_visibility="collapsed",
                                    help="Check to use your custom value instead of the app estimate",
                                )
                            with _c2:
                                _ov = st.number_input(
                                    f"{_lbl} ({currency}/mo)",
                                    min_value=_lo, max_value=_hi,
                                    value=st.session_state.get(_val_key, _yaml_val),
                                    step=25,
                                    key=_val_key,
                                    disabled=not _locked,
                                    label_visibility="visible",
                                )
                                st.caption(f"YAML estimate: {currency} {_yaml_val:,}/mo")
                            if _locked:
                                city_overrides[_effective_cat] = _ov / _yaml_val  # multiplier vs ample

                    city_inputs[city_slug] = {
                        "slug":              city_slug,
                        "name":              city_data["name"],
                        "country_code":      country_code,
                        "currency":          currency,
                        "eur_rate":          country_data["eur_rate"],
                        "gross":             gross,
                        "effective_gross":   effective_gross,
                        "bonus_pct":         bonus_pct,
                        "rsu":               rsu,
                        "active_schemes":    active_schemes,
                        "scheme_expiry":     scheme_expiry,
                        "ruling_start_year": ruling_start_year,
                        "cagr":              cagr,
                        "company":           company,
                        "city_overrides":    city_overrides,
                        "perks_monthly_eur": perks_monthly_eur,
                    }
    else:
        st.info("👆 Select at least one city above to add salaries and see the comparison.")

    st.divider()

    # ── Section B: My Actual Expenses ─────────────────────────────────────────

    st.header("💰 My Actual Expenses")

    if not selected_city_slugs:
        st.info("👆 Select cities above first — your expenses will be scaled to each one.")
    else:
        home_city_data = get_city_data(home_city_slug)
        home_col       = home_city_data["cost_of_living"]
        home_country_d = get_country_data(home_city_data["country"])
        home_eur_rate  = home_country_d["eur_rate"]

        st.markdown(
            f"What do you **actually spend today**, in EUR? "
            f"Home city reference: **{home_city_data['name']}**. "
            f"Expenses for other cities are scaled using cost-of-living ratios."
        )

        # ── Mode-switch detection ──────────────────────────────────────────────
        expense_mode = st.radio(
            "Input mode",
            ["⚡ Quick (total only)", "📋 Detailed (by category)"],
            horizontal=True,
            key="expense_mode",
        )
        prev_mode = st.session_state.get("_prev_expense_mode")

        # Quick → Detailed: pre-populate per-category inputs from last total
        if expense_mode == "📋 Detailed (by category)" and prev_mode == "⚡ Quick (total only)":
            _seed_total = st.session_state.get("user_total_expenses", 3500)
            if home_city_slug and _seed_total > 0:
                try:
                    _dist = cached_distribute(float(_seed_total), home_city_slug, pax)
                    for cat in UI_CAT_KEYS:
                        if cat in _dist:
                            st.session_state[f"exp_{cat}"] = int(_dist[cat])
                except Exception:
                    pass

        # Detailed → Quick: sync total from sum of detailed inputs
        if expense_mode == "⚡ Quick (total only)" and prev_mode == "📋 Detailed (by category)":
            _detail_sum = sum(st.session_state.get(f"exp_{cat}", 0) for cat in UI_CAT_KEYS)
            if _detail_sum > 0:
                st.session_state["user_total_expenses"] = _detail_sum

        st.session_state["_prev_expense_mode"] = expense_mode

        # ── Quick mode ─────────────────────────────────────────────────────────
        if expense_mode == "⚡ Quick (total only)":
            user_total = st.number_input(
                "Total monthly expenses (€/mo)",
                min_value=0, max_value=20000, step=50,
                value=st.session_state.get("user_total_expenses", 3500),
                key="user_total_expenses",
                help="Everything: rent, food, transport, insurance, going out — your full monthly spend",
            )
            st.caption("This total will be scaled to other cities using cost-of-living ratios.")

            if user_total > 0:
                try:
                    _dist_all = cached_distribute(float(user_total), home_city_slug, pax)
                    user_expenses_by_cat = {
                        cat: v for cat, v in _dist_all.items() if cat in UI_CAT_KEYS
                    }
                except Exception:
                    user_expenses_by_cat = {}

                if user_expenses_by_cat:
                    with st.expander("See how this distributes across categories"):
                        _dist_rows = [
                            {
                                "Category": f"{CAT_EMOJIS.get(cat, '')} {UI_CAT_LABELS.get(cat, cat)}",
                                "EUR/mo": f"€{v:,}",
                                "Type": "Portable ✈️" if cat in PORTABLE_CATS else "City-variable 🏙️",
                            }
                            for cat, v in user_expenses_by_cat.items()
                        ]
                        st.dataframe(pd.DataFrame(_dist_rows), hide_index=True, width="stretch")

        # ── Detailed mode ──────────────────────────────────────────────────────
        else:
            st.markdown("**City-variable expenses** *(scaled to each city)*")
            _header_cols = st.columns([3, 2, 2, 1])
            with _header_cols[0]: st.caption("Category")
            with _header_cols[1]: st.caption("Your spend (€/mo)")
            with _header_cols[2]: st.caption("City estimate")
            with _header_cols[3]: st.caption("Diff")

            _var_total = 0
            for cat in CITY_VAR_CATS:
                label       = UI_CAT_LABELS.get(cat, cat)
                emoji       = CAT_EMOJIS.get(cat, "")
                # For health categories, resolve the alias (health_kvg for CH cities)
                # so the reference correctly shows KVG mandatory cost, not the small VVG supplement.
                if cat in ("health_extra", "health_kvg"):
                    comfortable_local = _resolve_health_comfortable(home_col, cat)
                else:
                    comfortable_local = home_col.get(cat, {}).get("comfortable", 0) or 0
                comfortable_eur   = round(comfortable_local * home_eur_rate)

                if f"exp_{cat}" not in st.session_state:
                    st.session_state[f"exp_{cat}"] = comfortable_eur

                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.markdown(f"{emoji} **{label}**")
                with cols[1]:
                    val = st.number_input(
                        label, min_value=0, max_value=10000, step=10,
                        key=f"exp_{cat}", label_visibility="collapsed",
                    )
                with cols[2]:
                    st.caption(f"City est: €{comfortable_eur:,}")
                with cols[3]:
                    diff = val - comfortable_eur
                    st.caption(f"{'+'if diff>=0 else ''}{diff:,}")
                _var_total += val

            st.caption(f"City-variable subtotal: **€{_var_total:,}/mo**")
            st.markdown("---")
            st.markdown("**Portable expenses** *(same in every city)*")

            _port_total = 0
            for cat in PORTABLE_CATS:
                label       = UI_CAT_LABELS.get(cat, cat)
                emoji       = CAT_EMOJIS.get(cat, "")
                comfortable_local = home_col.get(cat, {}).get("comfortable", 0) or 0
                comfortable_eur   = round(comfortable_local * home_eur_rate)

                if f"exp_{cat}" not in st.session_state:
                    st.session_state[f"exp_{cat}"] = comfortable_eur

                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.markdown(f"{emoji} **{label}**")
                with cols[1]:
                    val = st.number_input(
                        label, min_value=0, max_value=10000, step=10,
                        key=f"exp_{cat}", label_visibility="collapsed",
                    )
                with cols[2]:
                    st.caption(f"City est: €{comfortable_eur:,}")
                with cols[3]:
                    diff = val - comfortable_eur
                    st.caption(f"{'+'if diff>=0 else ''}{diff:,}")
                _port_total += val

            st.caption(f"Portable subtotal: **€{_port_total:,}/mo**")
            user_total = _var_total + _port_total
            st.markdown(f"**Grand total: €{user_total:,}/mo**")
            user_expenses_by_cat = {cat: st.session_state.get(f"exp_{cat}", 0) for cat in UI_CAT_KEYS}

        # ── Lifestyle anchors ──────────────────────────────────────────────────
        with st.expander("🎯 Lifestyle anchors — portable expenses"):
            gym       = st.number_input("Monthly gym / fitness (€)",              min_value=0, step=10, value=0,  key="anchor_gym")
            hobbies   = st.number_input("Monthly hobbies (€)",                    min_value=0, step=10, value=0,  key="anchor_hobbies")
            pets      = st.number_input("Monthly pets (€)",                       min_value=0, step=10, value=0,  key="anchor_pets")
            streaming = st.number_input("Monthly streaming / subscriptions (€)",  min_value=0, step=5,  value=30, key="anchor_streaming")
            other_pa  = st.number_input("Monthly other personal recurring (€)",   min_value=0, step=10, value=0,  key="anchor_other")
            _anchor_total = gym + hobbies + pets + streaming + other_pa
            st.metric("Total lifestyle anchors", f"€{_anchor_total}/month")

        lifestyle_anchors_eur = {k: v for k, v in {
            "Gym": gym, "Hobbies": hobbies, "Pets": pets,
            "Streaming": streaming, "Personal": other_pa,
        }.items() if v > 0}

    st.divider()

    # ── Section C: Scenario Calibration ───────────────────────────────────────

    st.header("📐 Scenario Calibration")

    _lifestyle_total = sum(lifestyle_anchors_eur.values()) if lifestyle_anchors_eur else 0
    _baseline_total  = user_total + _lifestyle_total

    if not selected_city_slugs:
        st.info("Select cities and enter your actual expenses above to calibrate scenarios.")
    elif user_total == 0:
        st.info("Enter your actual monthly expenses in Section B to calibrate scenarios against your real spend.")
    else:
        _anchor_note = f"  ·  Lifestyle anchors: **€{_lifestyle_total:,}**  ·  Total baseline: **€{_baseline_total:,}**" if _lifestyle_total else ""
        st.markdown(f"Your actual monthly spend: **€{user_total:,}**{_anchor_note}")

    scen_cols = st.columns(3)
    for i, scol in enumerate(scen_cols):
        with scol:
            scen_default = SCENARIO_DEFAULTS[i]["name"]
            st.text_input(
                "Scenario name", key=f"scen_name_{i}",
                label_visibility="collapsed", placeholder=scen_default,
            )
            scen_label = st.session_state.get(f"scen_name_{i}") or scen_default
            st.markdown(f"**{scen_label}**")

            st.slider(
                "Global intensity (%)",
                min_value=50, max_value=200, step=5,
                key=f"scen_global_{i}",
                on_change=_sync_cats, args=(i,),
                help="Scales all budget categories together. Fine-tune per category below.",
            )
            global_pct = st.session_state[f"scen_global_{i}"]

            if user_total > 0:
                implied = user_total * global_pct / 100
                st.metric(
                    label=f"{global_pct}% of your spend",
                    value=f"€{implied:,.0f}/mo",
                    help="Implied monthly expenses at this scenario intensity (excl. lifestyle anchors)",
                )
            else:
                st.caption(f"Global: {global_pct}%")

            with st.expander("🔧 Fine-tune per category"):
                for cat in UI_CAT_KEYS:
                    cat_label = UI_CAT_LABELS[cat]
                    pct_val   = st.session_state.get(f"scen_cat_{i}_{cat}", global_pct)

                    user_cat_eur = user_expenses_by_cat.get(cat, 0)
                    eur_hint = ""
                    if user_cat_eur > 0:
                        eur_hint = f"  ≈ €{user_cat_eur * pct_val / 100:,.0f}/mo"

                    st.slider(
                        f"{cat_label}{eur_hint}",
                        min_value=50, max_value=200, step=5,
                        key=f"scen_cat_{i}_{cat}",
                    )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: COMPARE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_compare:
    if not city_inputs:
        st.info("👆 Go to **📋 My Setup** and select at least one city to see comparisons.")
    else:
        scenarios_def = _build_scenarios()
        scen_names    = [s["name"] for s in scenarios_def]
        city_names    = {slug: city_inputs[slug]["name"] for slug in city_inputs}
        anchors_tuple = tuple(sorted(lifestyle_anchors_eur.items()))
        has_actuals   = bool(home_city_slug and sum(user_expenses_by_cat.values()) > 0)

        # ── CoL inflation assumption (used for trajectory only) ────────────────
        _slider_col1, _slider_col2 = st.columns(2)
        with _slider_col1:
            col_inflation_pct = st.slider(
                "📈 CoL inflation (trajectory only)",
                min_value=0.0, max_value=5.0, value=2.0, step=0.5,
                key="col_inflation_pct",
                help=(
                    "Annual cost-of-living inflation applied to expenses in the trajectory. "
                    "0% = expenses stay flat. 2% = typical stable city. "
                    "3–4% = high-inflation market (London, Zurich). "
                    "Does NOT affect the Cost·Surplus matrix (year 0 snapshot)."
                ),
            )
        with _slider_col2:
            settling_pct = st.slider(
                "🏡 Settling-in phase",
                min_value=0, max_value=100, value=50, step=10,
                key="settling_pct",
                help=(
                    "How settled are you in the destination city?\n\n"
                    "**0% = Just arrived** — newcomer premiums fully applied: "
                    "eating out +25%, misc +20%, leisure +15%, groceries +10%.\n\n"
                    "**100% = Fully settled** — pure ratio scaling, no premium.\n\n"
                    "**50% (default)** — realistic average across a first year.\n\n"
                    "Affects non-home cities only. Rent, transport and utilities always "
                    "use city YAML rates regardless of this setting."
                ),
            )
        col_inflation_rate = col_inflation_pct / 100.0
        settling_factor    = settling_pct / 100.0

        # ── Build results matrix ───────────────────────────────────────────────
        results_matrix: dict[str, dict[str, dict]] = {}
        for city_slug, ci in city_inputs.items():
            results_matrix[city_slug] = {}
            net = cached_calculate_net(
                ci["effective_gross"], ci["country_code"], tuple(ci["active_schemes"])
            )
            perks_eur = ci.get("perks_monthly_eur", 0.0)
            adjusted_net_eur = net["net_monthly_eur"] + perks_eur
            for scen in scenarios_def:
                cat_mults_t  = tuple(sorted(scen["category_multipliers"].items()))
                scheme_exp_t = tuple(sorted(ci["scheme_expiry"].items()))
                budget = get_budget_for_city(
                    city_slug, scen, home_city_slug,
                    user_expenses_by_cat, lifestyle_anchors_eur, pax,
                    partner_net_monthly,
                    city_overrides=ci.get("city_overrides", {}),
                    settling_factor=settling_factor,
                )
                surplus = calculate_surplus(adjusted_net_eur, budget)
                trajectory = cached_trajectory(
                    gross=ci["effective_gross"],
                    country_code=ci["country_code"],
                    city_slug=city_slug,
                    cat_mults_tuple=cat_mults_t,
                    pax=pax,
                    anchors_tuple=anchors_tuple,
                    partner_net=partner_net_monthly,
                    cagr=ci["cagr"],
                    active_schemes_tuple=tuple(ci["active_schemes"]),
                    scheme_expiry_tuple=scheme_exp_t,
                    expenses_eur=budget["total_eur"],
                    col_inflation_rate=col_inflation_rate,
                    perks_monthly_eur=perks_eur,
                    ruling_start_year=ci.get("ruling_start_year", 2026),
                )
                results_matrix[city_slug][scen["name"]] = {
                    "net":        net,
                    "budget":     budget,
                    "surplus":    surplus,
                    "trajectory": trajectory,
                }

        if has_actuals:
            st.caption(
                f"💡 Expenses based on your actual spend, scaled per city. "
                f"Trajectory applies {col_inflation_pct:.0f}% CoL inflation/year."
            )

        # ── Download button ────────────────────────────────────────────────────
        try:
            from output.excel import generate_excel_report as _gen_excel
            _excel_bytes = _gen_excel(
                city_inputs=city_inputs,
                results_matrix=results_matrix,
                scenarios_def=scenarios_def,
                city_names=city_names,
                home_city_slug=home_city_slug,
                scen_names=scen_names,
                col_inflation_rate=col_inflation_rate,
            )
            st.download_button(
                label="⬇️ Download Excel report",
                data=_excel_bytes,
                file_name=f"salary_compass_{date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Download a full Excel workbook with Summary, Budget Breakdown, "
                     "Trajectory, Negotiation Targets, and Assumptions sheets.",
            )
        except Exception as _exc:
            st.warning(f"Excel export unavailable: {_exc}")

        # ── 4 inner result tabs ────────────────────────────────────────────────
        r_tab1, r_tab2, r_tab3, r_tab4 = st.tabs([
            "📊 Budget & Surplus",
            "📈 10-Year Trajectory",
            "🔢 Negotiation Ladder",
            "ℹ️ Details & Caveats",
        ])

        # ── r_tab1: Budget & Surplus ───────────────────────────────────────────
        with r_tab1:
            # ── All scenarios × all cities: one row per scenario ──────────────
            st.subheader("📊 Cost · Surplus — all scenarios × all cities")

            # Build MultiIndex columns: (city_label, "Cost") and (city_label, "Surplus")
            col_tuples = []
            for slug in city_inputs:
                r_first   = results_matrix[slug][scenarios_def[0]["name"]]
                net_mo    = r_first["net"]["net_monthly_eur"]
                ccy       = r_first["net"]["currency"]
                net_local = r_first["net"]["net_monthly_local"]
                label     = city_names[slug]
                if ccy == "EUR":
                    city_header = f"{label}\n€{net_mo:,.0f}/mo"
                else:
                    city_header = f"{label}\n{ccy} {net_local:,.0f} / €{net_mo:,.0f}/mo"
                col_tuples += [(city_header, "Cost"), (city_header, "Surplus")]

            mi = pd.MultiIndex.from_tuples(col_tuples)
            data_rows: list[list] = []
            idx_labels: list[str] = []

            for scen in scenarios_def:
                sname = scen["name"]
                row   = []
                for slug in city_inputs:
                    r = results_matrix[slug][sname]
                    row += [r["budget"]["total_eur"], r["surplus"]["surplus_eur"]]
                data_rows.append(row)
                idx_labels.append(sname)

            overview_df = pd.DataFrame(data_rows, index=idx_labels, columns=mi)
            overview_df.index.name = "Scenario"

            surplus_positions = [i for i, (_, m) in enumerate(col_tuples) if m == "Surplus"]

            def _style_overview(df: pd.DataFrame) -> pd.DataFrame:
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for row_i in range(len(df)):
                    for col_i, (_, metric) in enumerate(col_tuples):
                        if metric == "Cost":
                            styles.iloc[row_i, col_i] = "color:#888888"
                        else:
                            v = df.iloc[row_i, col_i]
                            styles.iloc[row_i, col_i] = (
                                "font-weight:700;color:#27ae60" if v >= 0
                                else "font-weight:700;color:#e74c3c"
                            )
                return styles

            st.dataframe(
                overview_df.style
                    .apply(_style_overview, axis=None)
                    .format("€{:,.0f}"),
                width="stretch",
            )

            st.divider()

            # ── Per-scenario drill-down ───────────────────────────────────────
            sel_scen = st.radio(
                "Drill down into scenario",
                options=scen_names,
                horizontal=True,
                key="tab1_scen",
            )
            st.subheader(f"Monthly breakdown — *{sel_scen}*")

            budget_data = [
                {
                    "label": city_names[s],
                    "items": {
                        k: v for k, v in results_matrix[s][sel_scen]["budget"]["items"].items()
                        if not k.startswith("lifestyle_") and k != "partner_contribution"
                    },
                }
                for s in city_inputs
            ]
            st.plotly_chart(budget_breakdown_chart(budget_data), width="stretch")

            st.subheader("📋 Full expense breakdown")
            all_item_keys = []
            for slug in city_inputs:
                for k in results_matrix[slug][sel_scen]["budget"]["items"]:
                    if k not in all_item_keys:
                        all_item_keys.append(k)

            rows = []
            for key in all_item_keys:
                first_slug = list(city_inputs)[0]
                row = {
                    "Category": results_matrix[first_slug][sel_scen]["budget"]["items"]
                                .get(key, {}).get("label", key)
                }
                for slug in city_inputs:
                    item = results_matrix[slug][sel_scen]["budget"]["items"].get(key)
                    ccy  = results_matrix[slug][sel_scen]["budget"]["currency"]
                    if item:
                        lv = item["value_local"]
                        ev = item["value_eur"]
                        row[city_names[slug]] = f"{ccy} {lv:,}" + (f" (€{ev:,})" if ccy != "EUR" else "")
                    else:
                        row[city_names[slug]] = "—"
                rows.append(row)

            total_row = {"Category": "**TOTAL**"}
            for slug in city_inputs:
                b   = results_matrix[slug][sel_scen]["budget"]
                ccy = b["currency"]
                total_row[city_names[slug]] = f"**{ccy} {b['total_local']:,}** (€{b['total_eur']:,})"
            rows.append(total_row)
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        # ── r_tab2: 10-Year Trajectory ─────────────────────────────────────────
        with r_tab2:
            st.subheader("10-Year Cumulative Savings")

            traj_traces = []
            for city_idx, city_slug in enumerate(city_inputs):
                for scen_idx, scen in enumerate(scenarios_def):
                    traj_data = results_matrix[city_slug][scen["name"]]["trajectory"]
                    traj_traces.append({
                        "label":        f"{city_names[city_slug]} · {scen['name']}",
                        "data":         traj_data,
                        "city_idx":     city_idx,
                        "scenario_idx": scen_idx,
                    })
            st.plotly_chart(trajectory_line_chart(traj_traces), width="stretch")

            with st.expander("📋 Year-by-year detail"):
                for city_slug in city_inputs:
                    st.markdown(f"**{city_names[city_slug]}**")
                    _ccy = city_inputs[city_slug]["currency"]
                    for scen in scenarios_def:
                        st.caption(f"*{scen['name']}*")
                        traj = results_matrix[city_slug][scen["name"]]["trajectory"]
                        df   = pd.DataFrame(traj)[[
                            "year", "gross_annual_local", "net_monthly_eur", "total_expenses_eur",
                            "surplus_monthly_eur", "cumulative_savings_eur", "effective_rate",
                        ]]
                        df.columns = [
                            "Year", f"Gross {_ccy}/yr", "Net EUR/mo", "Expenses EUR/mo",
                            "Surplus EUR/mo", "Cumulative EUR", "Eff. rate %",
                        ]
                        st.dataframe(df, width="stretch", hide_index=True)

            st.subheader("5-year & 10-year summary")
            for horizon, yr_idx in [("5-Year", 4), ("10-Year", 9)]:
                st.markdown(f"**{horizon} cumulative savings (EUR)**")
                tbl_rows = []
                for scen in scenarios_def:
                    row = {"Scenario": scen["name"]}
                    for slug in city_inputs:
                        traj = results_matrix[slug][scen["name"]]["trajectory"]
                        idx  = min(yr_idx, len(traj) - 1)
                        row[city_names[slug]] = traj[idx]["cumulative_savings_eur"]
                    tbl_rows.append(row)
                tbl_df = pd.DataFrame(tbl_rows).set_index("Scenario")
                st.dataframe(
                    tbl_df.style.map(_color_surplus).format("€{:,.0f}"),
                    width="stretch",
                )

            for city_slug in city_inputs:
                for scen in scenarios_def:
                    traj       = results_matrix[city_slug][scen["name"]]["trajectory"]
                    all_events = [e for yr in traj for e in yr.get("events", [])]
                    for ev in set(all_events):
                        st.warning(f"{city_names[city_slug]} · {scen['name']}: {ev}")

            # ── 30% Ruling / Beckham Law cliff analysis ──────────────────────
            cliff_entries = []
            rate_change_entries = []
            for city_slug, ci in city_inputs.items():
                country_code = ci["country_code"]
                ruling_start = ci.get("ruling_start_year", 2026)
                for scheme_id in ci["active_schemes"]:
                    expiry_yr = ci["scheme_expiry"].get(scheme_id)
                    traj_scen = scen_names[min(1, len(scen_names)-1)]
                    traj = results_matrix[city_slug][traj_scen]["trajectory"]

                    # ── Rate-change cliff (e.g. NL 30%→27% from 2027) ──────
                    from engine.tax import load_country as _lc, _find_scheme as _fs
                    _cd = _lc(country_code)
                    _s  = _fs(_cd, scheme_id)
                    rc  = _s.get("rate_change") if _s else None
                    if rc:
                        change_cal_yr = rc["calendar_year"]
                        change_traj_yr = change_cal_yr - ruling_start + 1  # 1-based
                        if 1 <= change_traj_yr <= len(traj) and (not expiry_yr or change_traj_yr <= expiry_yr):
                            yr_before = traj[change_traj_yr - 2] if change_traj_yr > 1 else None
                            yr_after  = traj[change_traj_yr - 1]
                            if yr_before:
                                rc_drop = yr_before["net_monthly_eur"] - yr_after["net_monthly_eur"]
                                if rc_drop > 0:
                                    new_mult = rc["new_multiplier"]
                                    target_gross_rc = find_target_gross(
                                        yr_before["net_monthly_eur"],
                                        country_code,
                                        active_schemes=[scheme_id],
                                        scheme_overrides={scheme_id: {"multiplier": new_mult}},
                                    )
                                    old_pct = int((1 - _s["multiplier"]) * 100)
                                    new_pct = int((1 - new_mult) * 100)
                                    rate_change_entries.append({
                                        "city_name":    city_names[city_slug],
                                        "scheme_id":    scheme_id,
                                        "old_pct":      old_pct,
                                        "new_pct":      new_pct,
                                        "change_cal_yr": change_cal_yr,
                                        "traj_yr":      change_traj_yr,
                                        "net_before":   yr_before["net_monthly_eur"],
                                        "net_after":    yr_after["net_monthly_eur"],
                                        "rc_drop":      rc_drop,
                                        "gross_needed": target_gross_rc,
                                        "currency":     ci["currency"],
                                    })

                    # ── Expiry cliff ────────────────────────────────────────
                    if not expiry_yr:
                        continue
                    if len(traj) < expiry_yr + 1:
                        continue
                    yr_with    = traj[expiry_yr - 1]   # last year with scheme
                    yr_without = traj[expiry_yr]        # first year without
                    net_drop   = yr_with["net_monthly_eur"] - yr_without["net_monthly_eur"]
                    if net_drop <= 0:
                        continue
                    # Find gross needed without scheme to maintain the same net
                    target_gross_no_scheme = find_target_gross(
                        yr_with["net_monthly_eur"],
                        country_code,
                        active_schemes=[],
                    )
                    cliff_entries.append({
                        "city_name":     city_names[city_slug],
                        "scheme_id":     scheme_id,
                        "expiry_yr":     expiry_yr,
                        "net_with":      yr_with["net_monthly_eur"],
                        "net_without":   yr_without["net_monthly_eur"],
                        "net_drop":      net_drop,
                        "gross_needed":  target_gross_no_scheme,
                        "currency":      ci["currency"],
                    })

            if rate_change_entries:
                st.divider()
                st.subheader("⚡ Tax Scheme Rate Change")
                for rc_e in rate_change_entries:
                    scheme_label = {
                        "nl_30_ruling": "🇳🇱 30% Ruling",
                    }.get(rc_e["scheme_id"], rc_e["scheme_id"])
                    ccy = rc_e["currency"]
                    with st.container():
                        st.markdown(
                            f"**{rc_e['city_name']} · {scheme_label}** — "
                            f"rate reduced from **{rc_e['old_pct']}%** to **{rc_e['new_pct']}%** "
                            f"from **{rc_e['change_cal_yr']}** (trajectory Year {rc_e['traj_yr']})"
                        )
                        c1, c2, c3 = st.columns(3)
                        c1.metric(f"Net in Year {rc_e['traj_yr']-1} ({rc_e['old_pct']}% ruling)",
                                  f"€{rc_e['net_before']:,}/mo")
                        c2.metric(f"Net in Year {rc_e['traj_yr']} ({rc_e['new_pct']}% ruling)",
                                  f"€{rc_e['net_after']:,}/mo",
                                  delta=f"-€{rc_e['rc_drop']:,}/mo", delta_color="inverse")
                        c3.metric("Gross needed to keep Year N net",
                                  f"{ccy} {rc_e['gross_needed']:,}/yr",
                                  help=f"Annual gross at {rc_e['new_pct']}% ruling to match your pre-{rc_e['change_cal_yr']} net.")
                        st.caption(
                            f"📌 Negotiate a **{ccy} {rc_e['gross_needed']:,}/yr** package before "
                            f"{rc_e['change_cal_yr']} to absorb the {rc_e['old_pct']}%→{rc_e['new_pct']}% ruling cut "
                            f"(**-€{rc_e['rc_drop']:,}/mo**)."
                        )
                        st.divider()

            if cliff_entries:
                st.divider()
                st.subheader("⚠️ Tax Scheme Expiry Cliff")
                for cliff in cliff_entries:
                    scheme_label = {
                        "nl_30_ruling":    "🇳🇱 30% Ruling",
                        "beckham_law":     "🇪🇸 Beckham Law",
                        "es_impatriados":  "🇪🇸 Régimen de Impatriados",
                    }.get(cliff["scheme_id"], cliff["scheme_id"])
                    ccy  = cliff["currency"]
                    with st.container():
                        st.markdown(
                            f"**{cliff['city_name']} · {scheme_label}** — "
                            f"expires after **Year {cliff['expiry_yr']}**"
                        )
                        c1, c2, c3 = st.columns(3)
                        c1.metric(
                            f"Net in Year {cliff['expiry_yr']} (last with scheme)",
                            f"€{cliff['net_with']:,}/mo",
                        )
                        c2.metric(
                            f"Net in Year {cliff['expiry_yr']+1} (first without)",
                            f"€{cliff['net_without']:,}/mo",
                            delta=f"-€{cliff['net_drop']:,}/mo",
                            delta_color="inverse",
                        )
                        c3.metric(
                            "Gross needed (without scheme) to match",
                            f"{ccy} {cliff['gross_needed']:,}/yr",
                            help="The annual gross salary that produces the same net as Year "
                                 f"{cliff['expiry_yr']}, without the tax scheme active.",
                        )
                        st.caption(
                            f"📌 Negotiate a raise to at least **{ccy} {cliff['gross_needed']:,}/yr** "
                            f"before Year {cliff['expiry_yr'] + 1} to avoid a "
                            f"**€{cliff['net_drop']:,}/month** income shock."
                        )
                        st.divider()

        # ── r_tab3: Negotiation Ladder ─────────────────────────────────────────
        with r_tab3:
            st.subheader("Negotiation Salary Ladder")
            st.caption(
                "Select a reference city + scenario and a target city. "
                "The ladder shows at what gross salary each scenario breaks even."
            )

            if len(city_inputs) < 2:
                st.info("Select at least 2 cities to use the negotiation ladder.")
            else:
                city_name_list = [city_names[s] for s in city_inputs]

                ref_city_name    = st.selectbox("Reference city",    city_name_list, index=0, key="ref_city")
                ref_scen_name    = st.selectbox("Reference scenario", scen_names,    index=1, key="ref_scen")
                target_city_name = st.selectbox(
                    "Target city (to ladder)",
                    [n for n in city_name_list if n != ref_city_name],
                    key="target_city",
                )

                ref_slug    = next(s for s in city_inputs if city_names[s] == ref_city_name)
                target_slug = next(s for s in city_inputs if city_names[s] == target_city_name)

                ref_surplus = results_matrix[ref_slug][ref_scen_name]["surplus"]["surplus_eur"]
                target_ci   = city_inputs[target_slug]

                target_gross = target_ci["gross"]
                step         = max(5_000, int(target_gross * 0.05 / 5_000) * 5_000)
                ladder_grosses = list(range(
                    max(30_000, int(target_gross * 0.7 // step) * step),
                    int(target_gross * 1.5 // step + 1) * step,
                    step,
                ))

                scen_ladders: dict[str, list] = {}
                for scen in scenarios_def:
                    # Budget is constant across gross levels — compute once
                    scen_budget = get_budget_for_city(
                        target_slug, scen, home_city_slug,
                        user_expenses_by_cat, lifestyle_anchors_eur, pax,
                        partner_net_monthly,
                        city_overrides=city_inputs.get(target_slug, {}).get("city_overrides", {}),
                        settling_factor=settling_factor,
                    )
                    ladder = []
                    for g in ladder_grosses:
                        n = cached_calculate_net(g, target_ci["country_code"], tuple(target_ci["active_schemes"]))
                        s = calculate_surplus(n["net_monthly_eur"], scen_budget)
                        ladder.append({
                            "gross":          g,
                            "currency":       target_ci["currency"],
                            "net_monthly_eur":n["net_monthly_eur"],
                            "surplus_eur":    s["surplus_eur"],
                        })
                    scen_ladders[scen["name"]] = ladder

                comfortable_ladder = scen_ladders.get(scen_names[1], scen_ladders[scen_names[0]])
                fig = negotiation_ladder_chart(comfortable_ladder, ref_surplus)
                st.plotly_chart(fig, width="stretch")

                # ── Exact break-even (binary search) ──────────────────────
                st.markdown("**Exact break-even gross** (binary search)")
                target_perks = city_inputs.get(target_slug, {}).get("perks_monthly_eur", 0.0)
                for scen in scenarios_def:
                    scen_budget_total = get_budget_for_city(
                        target_slug, scen, home_city_slug,
                        user_expenses_by_cat, lifestyle_anchors_eur, pax,
                        partner_net_monthly,
                        city_overrides=city_inputs.get(target_slug, {}).get("city_overrides", {}),
                        settling_factor=settling_factor,
                    )["total_eur"]
                    # Target: net + perks - expenses = ref_surplus
                    target_net = ref_surplus + scen_budget_total - target_perks
                    ccy = target_ci["currency"]
                    breakeven_exact = find_target_gross(
                        target_net,
                        target_ci["country_code"],
                        active_schemes=list(target_ci["active_schemes"]),
                    )
                    perks_note = (
                        f" (including €{target_perks:,.0f}/mo perks)" if target_perks > 0 else ""
                    )
                    st.success(
                        f"**{scen['name']}** — ask for at least "
                        f"**{ccy} {breakeven_exact:,}/yr gross** "
                        f"to match €{ref_surplus:+,.0f}/mo surplus in {ref_city_name}"
                        f"{perks_note}"
                    )

                st.divider()

                # ── Move Readiness ─────────────────────────────────────────
                st.subheader("🏦 Move Readiness — Cash You Need Before Day 1")

                moving_costs_input = st.number_input(
                    f"Your estimated moving costs ({target_ci['currency']})",
                    min_value=0,
                    max_value=200_000,
                    value=0,
                    step=500,
                    key=f"moving_costs_{target_slug}",
                    help="Professional movers, van hire, flights, shipping containers, etc.",
                )
                return_visits = st.number_input(
                    "Annual home visits (for context)",
                    min_value=0, max_value=20,
                    value=3, step=1,
                    key=f"return_visits_{target_slug}",
                    help="Estimated number of return trips to home country per year.",
                )
                cost_per_visit = st.number_input(
                    "Avg. cost per home visit (EUR round-trip)",
                    min_value=0, max_value=3000,
                    value=300, step=50,
                    key=f"cost_per_visit_{target_slug}",
                )

                target_city_data = get_city_data(target_slug)
                target_country_d = get_country_data(target_ci["country_code"])
                eur_rate_t = target_country_d["eur_rate"]  # 1 local = X EUR
                hidden = target_city_data.get("hidden_costs", [])

                # Compute mandatory one-time costs in EUR
                mandatory_one_time_eur = 0.0
                optional_one_time_eur = 0.0
                mandatory_recurring_eur = 0.0
                one_time_rows = []

                for hc_item in hidden:
                    if "one_time" not in hc_item:
                        continue
                    ot_local = hc_item.get("one_time", 0)
                    ot_eur = round(ot_local * eur_rate_t)
                    is_mandatory = hc_item.get("mandatory", False)
                    one_time_rows.append({
                        "Item":      hc_item.get("name", ""),
                        "Mandatory": "✅" if is_mandatory else "◻️",
                        f"{target_ci['currency']}": f"{ot_local:,}",
                        "≈ EUR":     f"€{ot_eur:,}",
                    })
                    if is_mandatory:
                        mandatory_one_time_eur += ot_eur
                    else:
                        optional_one_time_eur += ot_eur

                for hc_item in hidden:
                    if "monthly" not in hc_item and "annual" not in hc_item:
                        continue
                    if not hc_item.get("mandatory", False):
                        continue
                    if "monthly" in hc_item:
                        mandatory_recurring_eur += hc_item["monthly"] * eur_rate_t * 12
                    elif "annual" in hc_item:
                        mandatory_recurring_eur += hc_item["annual"] * eur_rate_t

                comfortable_budget_eur = results_matrix[target_slug][scen_names[min(1, len(scen_names)-1)]]["budget"]["total_eur"]
                buffer_3m = round(comfortable_budget_eur * 3)
                moving_costs_eur = round(moving_costs_input * eur_rate_t)
                total_cash_needed = round(mandatory_one_time_eur + buffer_3m + moving_costs_eur)
                total_cash_with_optional = round(total_cash_needed + optional_one_time_eur)
                annual_return_cost = return_visits * cost_per_visit

                if one_time_rows:
                    st.markdown("**One-time costs from the YAML data:**")
                    st.dataframe(pd.DataFrame(one_time_rows), width="stretch", hide_index=True)

                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Mandatory deposits & fees", f"€{mandatory_one_time_eur:,.0f}")
                col_b.metric("3-month comfortable buffer", f"€{buffer_3m:,.0f}")
                col_c.metric("Moving costs", f"€{moving_costs_eur:,.0f}")

                st.markdown(
                    f"### 💶 Have at least **€{total_cash_needed:,}** liquid before accepting "
                    f"(€{total_cash_with_optional:,} if you add optional one-time costs)"
                )

                if annual_return_cost > 0:
                    st.info(
                        f"✈️ **Annual home travel:** {return_visits} visits × €{cost_per_visit:,} "
                        f"= **€{annual_return_cost:,}/year** (€{annual_return_cost//12:,}/mo) — "
                        f"factor this into your portable expenses."
                    )

                # ── Sign-on bonus recommendation ───────────────────────────
                st.markdown("---")
                st.markdown("**💼 Sign-on Bonus Recommendation**")
                target_net_result = cached_calculate_net(
                    target_ci["effective_gross"], target_ci["country_code"], tuple(target_ci["active_schemes"])
                )
                effective_rate_t = target_net_result["effective_rate"]
                sign_on_gross = round(total_cash_needed / max(1 - effective_rate_t, 0.01))
                sign_on_ccy   = round(sign_on_gross / max(eur_rate_t, 0.01))
                st.markdown(
                    f"To cover your move costs after tax, ask for a **sign-on bonus of at least "
                    f"{target_ci['currency']} {sign_on_ccy:,} gross** "
                    f"(≈ €{sign_on_gross:,} gross · effective rate {effective_rate_t*100:.0f}% → "
                    f"nets ~€{total_cash_needed:,})."
                )

                st.divider()

                # ── Permit Timeline ────────────────────────────────────────
                st.subheader("🛂 Permit & Visa Timeline")
                permit = target_city_data.get("permit", {})
                if permit:
                    user_is_eu = target_country_d.get("currency") == "EUR" or True  # show both paths
                    pcol1, pcol2 = st.columns(2)
                    with pcol1:
                        eu_info = permit.get("eu_eea", {})
                        st.markdown(f"**🇪🇺 EU/EEA path** — ⏱ {eu_info.get('timeline', 'n/a')}")
                        for step in eu_info.get("steps", []):
                            st.markdown(f"  {step}")
                    with pcol2:
                        non_eu = permit.get("non_eu", {})
                        st.markdown(f"**🌍 Non-EU path** — ⏱ {non_eu.get('timeline', 'n/a')}")
                        for step in non_eu.get("steps", []):
                            st.markdown(f"  {step}")

                    complexity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
                        permit.get("complexity", ""), "⚪"
                    )
                    cost_note = (
                        f" · Approx. fees: €{permit['costs_eur']:,}"
                        if permit.get("costs_eur", 0) > 0 else ""
                    )
                    st.caption(
                        f"{complexity_emoji} Complexity: **{permit.get('complexity', 'n/a')}**"
                        f" · Sponsor required: {'yes' if permit.get('sponsor_required') else 'no'}"
                        f"{cost_note}"
                    )
                    if permit.get("notes"):
                        st.info(f"📌 {permit['notes']}")
                else:
                    st.info("Permit data not yet available for this city.")

        # ── r_tab4: Details & Caveats ──────────────────────────────────────────
        with r_tab4:
            st.subheader("Country & City Details")

            for city_slug in city_inputs:
                ci = city_inputs[city_slug]
                with st.expander(f"📍 {city_names[city_slug]}"):
                    country = get_country_data(ci["country_code"])
                    city    = get_city_data(city_slug)

                    st.markdown(f"**Country disclaimer:** {country.get('disclaimer', 'Directional estimates only.')}")

                    if country.get("warnings"):
                        for w in country["warnings"]:
                            st.warning(w)

                    hc = country.get("healthcare", {})
                    st.markdown(f"**Healthcare model:** {hc.get('model', 'Unknown')} — {hc.get('note', '')}")

                    if city.get("hidden_costs"):
                        st.markdown("**Hidden costs to budget for:**")
                        for hc_item in city["hidden_costs"]:
                            _name = hc_item.get("name", "")
                            _ccy_local = country.get("currency", "€")
                            if "monthly" in hc_item:
                                st.markdown(f"- {_name}: **{_ccy_local} {hc_item['monthly']}/month**")
                            elif "annual" in hc_item:
                                st.markdown(f"- {_name}: **{_ccy_local} {hc_item['annual']}/year**")
                            elif "one_time" in hc_item:
                                st.markdown(f"- {_name}: **{_ccy_local} {hc_item['one_time']} one-time**")
                            else:
                                st.markdown(f"- {_name}: {hc_item.get('note', '')}")

                    if city.get("permit"):
                        st.markdown("**Permit / Visa:**")
                        _p = city["permit"]
                        _cx_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(_p.get("complexity",""), "⚪")
                        st.markdown(
                            f"Complexity: {_cx_emoji} **{_p.get('complexity','n/a')}** · "
                            f"EU/EEA: {_p.get('eu_eea',{}).get('timeline','n/a')} · "
                            f"Non-EU: {_p.get('non_eu',{}).get('timeline','n/a')}"
                        )
                        if _p.get("notes"):
                            st.caption(_p["notes"])

            if lifestyle_anchors_eur:
                st.subheader("🎯 Lifestyle Anchors")
                anchor_df = pd.DataFrame(
                    [{"Category": k, "EUR/month": v} for k, v in lifestyle_anchors_eur.items()]
                    + [{"Category": "**Total**", "EUR/month": sum(lifestyle_anchors_eur.values())}]
                )
                st.dataframe(anchor_df, width="stretch", hide_index=True)
                st.caption(
                    "Lifestyle anchors are added as fixed line items converted to local currency in each city. "
                    "They do not scale with scenario intensity."
                )

            st.subheader("🏘 Household Model Assumptions")
            st.markdown(f"- **Household size:** {pax} {'person' if pax == 1 else 'people'}")
            st.markdown(f"- **Relationship:** {relationship}")
            if partner_net_monthly > 0:
                st.markdown(
                    f"- **Partner contribution:** ≈ €{partner_net_monthly / 2:,.0f}/month "
                    f"(half of partner net €{partner_net_monthly:,.0f}/month)"
                )
            if lifestyle_anchors_eur:
                st.markdown(f"- **Lifestyle anchors total:** €{sum(lifestyle_anchors_eur.values()):,.0f}/month")

            if own_property:
                st.subheader("🏠 Property")
                st.markdown(f"- **Monthly mortgage:** €{mortgage_monthly:,.0f}/month")
                if rental_income > 0:
                    net_property = rental_income - mortgage_monthly
                    st.markdown(
                        f"- **Expected rental income:** €{rental_income:,.0f}/month  "
                        f"→ net property P&L: **€{net_property:+,.0f}/month**"
                    )
                else:
                    st.markdown("- No rental income entered (property stays vacant or sold).")

            if has_actuals:
                st.subheader("📌 Expense Actuals Summary")
                actuals_rows = [
                    {
                        "Category": f"{CAT_EMOJIS.get(cat, '')} {UI_CAT_LABELS.get(cat, cat)}",
                        "Your spend (€/mo)": f"€{v:,}",
                        "Type": "Portable" if cat in PORTABLE_CATS else "City-variable",
                    }
                    for cat, v in user_expenses_by_cat.items()
                ]
                st.dataframe(pd.DataFrame(actuals_rows), width="stretch", hide_index=True)
                st.caption(f"Total entered: **€{sum(user_expenses_by_cat.values()):,}/mo** · Home city: **{home_city_data['name']}**")

            if extra_context:
                st.subheader("💬 Your context notes")
                st.info(extra_context)

            st.divider()
            st.markdown("""
### ⚠️ Important disclaimers
- All tax figures are **directional estimates**. Effective rates may differ based on individual deductions, allowances, and regional variations.
- This tool does **not** constitute tax or financial advice. Consult a qualified tax adviser in each country before making decisions.
- Exchange rates are fixed at build time. Update `eur_rate` in country YAML files for current rates.
- Visa and immigration requirements are not modelled. Consult an immigration lawyer for eligibility.
- Cost of living figures are based on published data and personal estimates. Individual circumstances vary significantly.
- Bonus and RSU figures are added to gross before tax; vesting schedules and cliff periods are not modelled.
- Trajectory calculations use YAML cost-of-living estimates; your entered actuals apply to the monthly snapshots only.
""")
