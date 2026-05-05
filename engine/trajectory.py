"""
10-year salary and surplus trajectory engine.
Models salary growth, scheme expiry events, and cumulative savings.
"""

from __future__ import annotations

from .budget import calculate_budget, calculate_budget_v2, calculate_surplus
from .tax import calculate_net


def calculate_trajectory(
    gross_annual: float,
    country_code: str,
    city_slug: str,
    scenario: str = "comfortable",
    category_multipliers: dict | None = None,
    pax: int = 2,
    lifestyle_anchors: dict | None = None,
    partner_net_monthly_eur: float = 0.0,
    cagr: float = 0.05,
    years: int = 10,
    active_schemes: list[str] | None = None,
    scheme_expiry: dict | None = None,
    expenses_eur: float | None = None,
    col_inflation_rate: float = 0.02,
    perks_monthly_eur: float = 0.0,
    ruling_start_year: int = 2026,
) -> list[dict]:
    """
    Calculate year-by-year trajectory.

    expenses_eur: if provided, use this as the Year 1 monthly expense total (e.g. from
        get_budget_for_city so the trajectory matches the Cost·Surplus matrix exactly).
        If None, falls back to calculate_budget_v2 (category_multipliers) or calculate_budget.

    col_inflation_rate: annual growth rate applied to expenses (default 2%).
        Reflects cost-of-living inflation in the target city. Set to 0.0 to hold
        expenses flat (optimistic). Typical range: 0.02 (stable) – 0.04 (high-inflation city).

    scheme_expiry: {scheme_id: expiry_year} e.g. {"nl_30_ruling": 5}

    perks_monthly_eur: fixed monthly tax-free perks (travel allowance + meal vouchers in EUR).
        Added directly to disposable income each year. Not subject to inflation or tax.

    ruling_start_year: the calendar year corresponding to Year 1 of this trajectory.
        Used to trigger scheme rate changes at the correct point. Default 2026.
        E.g. ruling_start_year=2025 → Year 3 = calendar 2027, when NL ruling drops to 27%.

    Returns list of dicts, one per year.
    """
    active_schemes = list(active_schemes or [])
    scheme_expiry = scheme_expiry or {}
    results = []
    cumulative_savings = 0.0

    # Pre-load rate_change metadata for all active schemes
    from .tax import _find_scheme as _find_s, load_country as _load_country

    _country_data = _load_country(country_code)
    _scheme_rate_changes: dict[str, dict] = {}
    for sid in active_schemes:
        s = _find_s(_country_data, sid)
        if s and s.get("rate_change"):
            _scheme_rate_changes[sid] = s["rate_change"]

    base_expenses_eur: float
    if expenses_eur is not None:
        base_expenses_eur = expenses_eur
    elif category_multipliers is not None:
        budget = calculate_budget_v2(
            city_slug,
            category_multipliers,
            pax=pax,
            lifestyle_anchors=lifestyle_anchors,
            partner_net_monthly_eur=partner_net_monthly_eur,
        )
        base_expenses_eur = budget["total_eur"]
    else:
        budget = calculate_budget(city_slug, scenario)
        base_expenses_eur = budget["total_eur"]

    for year in range(1, years + 1):
        gross = gross_annual * ((1 + cagr) ** (year - 1))
        year_expenses_eur = round(base_expenses_eur * ((1 + col_inflation_rate) ** (year - 1)))
        calendar_year = ruling_start_year + (year - 1)

        current_schemes = []
        events = []
        scheme_overrides: dict[str, dict] = {}

        for scheme in active_schemes:
            expiry = scheme_expiry.get(scheme)
            if expiry and year > expiry:
                events.append(f"⚠ {scheme} expired after year {expiry}")
            else:
                current_schemes.append(scheme)
                # Apply rate change if calendar year threshold reached
                rc = _scheme_rate_changes.get(scheme)
                if rc and calendar_year >= rc["calendar_year"]:
                    scheme_overrides[scheme] = {"multiplier": rc["new_multiplier"]}
                    # Emit event only in the first year the change kicks in
                    prev_cal = ruling_start_year + (year - 2)
                    if year == 1 or prev_cal < rc["calendar_year"]:
                        events.append(
                            f"⚡ {scheme} rate reduced "
                            f"({int((1 - rc['new_multiplier']) * 100)}% ruling "
                            f"from {rc['calendar_year']})"
                        )

        net = calculate_net(
            gross,
            country_code,
            current_schemes,
            scheme_overrides=scheme_overrides if scheme_overrides else None,
        )
        net_mo_eur = net["net_monthly_eur"] + perks_monthly_eur

        surplus = calculate_surplus(net_mo_eur, {"total_eur": year_expenses_eur})
        monthly_saving = surplus["surplus_eur"]
        annual_saving = monthly_saving * 12
        cumulative_savings += annual_saving

        results.append(
            {
                "year": year,
                "gross_annual_local": round(gross),
                "gross_annual_eur": round(gross * net["eur_rate"]),
                "net_monthly_eur": net_mo_eur,
                "total_expenses_eur": year_expenses_eur,
                "surplus_monthly_eur": round(monthly_saving),
                "surplus_annual_eur": round(annual_saving),
                "cumulative_savings_eur": round(cumulative_savings),
                "active_schemes": current_schemes,
                "events": events,
                "effective_rate": round(net["effective_rate"] * 100, 1),
            }
        )

    return results
