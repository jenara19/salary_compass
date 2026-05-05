"""
Tax calculation engine. Supports bracket method and lookup table method.
Returns net monthly salary in LOCAL currency and EUR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

COUNTRIES_DIR = Path(__file__).parent.parent / "data" / "countries"


def load_country(code: str) -> dict[str, Any]:
    path = COUNTRIES_DIR / f"{code}.yaml"
    with open(path, encoding="utf-8") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


def calculate_net(
    gross_annual: float,
    country_code: str,
    active_schemes: list[str] | None = None,
    scheme_overrides: dict[str, dict] | None = None,
) -> dict:
    """
    Calculate net monthly salary.

    scheme_overrides: optional per-scheme field overrides applied before calculation.
        E.g. {"nl_30_ruling": {"multiplier": 0.73}} patches the ruling to 27%
        without changing the YAML. Used by trajectory for the Jan-2027 rate change.

    Returns dict with:
        gross_annual, net_annual, net_monthly_local, net_monthly_eur,
        effective_rate, tax_annual, social_annual, currency, eur_rate
    """
    country = load_country(country_code)
    currency = country["currency"]
    eur_rate = country["eur_rate"]  # 1 unit local = X EUR
    active_schemes = active_schemes or []
    scheme_overrides = scheme_overrides or {}

    method = country["income_tax"].get("method", "brackets")

    if method == "effective_rate_lookup":
        # Check for schemes that override the lookup (e.g. Beckham Law flat rate)
        for scheme_id in active_schemes:
            scheme = _find_scheme(country, scheme_id)
            if scheme and scheme.get("type") == "flat_rate_override":
                flat_rate = scheme["rate"]
                tax_annual = gross_annual * flat_rate
                social_annual = _calc_social(gross_annual, country)
                net_annual = gross_annual - tax_annual - social_annual
                net_monthly_local = net_annual / 12
                effective_rate = (tax_annual + social_annual) / gross_annual if gross_annual else 0
                net_monthly_eur = net_monthly_local * eur_rate
                return {
                    "gross_annual": gross_annual,
                    "net_annual": net_annual,
                    "net_monthly_local": round(net_monthly_local),
                    "net_monthly_eur": round(net_monthly_eur),
                    "effective_rate": effective_rate,
                    "tax_annual": tax_annual,
                    "social_annual": social_annual,
                    "currency": currency,
                    "eur_rate": eur_rate,
                    "country_code": country_code,
                }

        net_monthly_local = _lookup_net(gross_annual, country["income_tax"])
        net_annual = net_monthly_local * 12
        # For lookup method, social is already factored in — don't double-count
        social_annual = 0
        tax_annual = gross_annual - net_annual
        effective_rate = tax_annual / gross_annual if gross_annual else 0

    else:  # brackets
        taxable = gross_annual

        # Apply special schemes (with any overrides)
        for scheme_id in active_schemes:
            scheme = _find_scheme(country, scheme_id)
            if scheme_overrides.get(scheme_id):
                scheme = {**(scheme or {}), **scheme_overrides[scheme_id]}
            if scheme and scheme["type"] == "taxable_multiplier":
                taxable = gross_annual * scheme["multiplier"]

        bracket_tax = _calc_brackets(taxable, country["income_tax"])
        credits = _calc_tax_credits(taxable, country["income_tax"])
        tax_annual = max(0.0, bracket_tax - credits)
        social_annual = _calc_social(gross_annual, country)
        net_annual = gross_annual - tax_annual - social_annual
        net_monthly_local = net_annual / 12
        effective_rate = (tax_annual + social_annual) / gross_annual if gross_annual else 0

    net_monthly_eur = net_monthly_local * eur_rate

    return {
        "gross_annual": gross_annual,
        "net_annual": net_annual,
        "net_monthly_local": round(net_monthly_local),
        "net_monthly_eur": round(net_monthly_eur),
        "effective_rate": effective_rate,
        "tax_annual": tax_annual,
        "social_annual": social_annual,
        "currency": currency,
        "eur_rate": eur_rate,
        "country_code": country_code,
    }


def _lookup_net(gross: float, tax_config: dict) -> float:
    """Interpolate net monthly from lookup table."""
    lookup = sorted(tax_config["lookup"], key=lambda x: x["gross"])
    marginal = float(tax_config.get("marginal_retention", 0.65))

    if gross <= lookup[0]["gross"]:
        diff = gross - float(lookup[0]["gross"])
        return float(lookup[0]["net_monthly"]) + diff / 12 * marginal

    if gross >= lookup[-1]["gross"]:
        diff = gross - float(lookup[-1]["gross"])
        return float(lookup[-1]["net_monthly"]) + diff / 12 * marginal

    for i in range(len(lookup) - 1):
        lo, hi = lookup[i], lookup[i + 1]
        if lo["gross"] <= gross <= hi["gross"]:
            frac = (gross - float(lo["gross"])) / (float(hi["gross"]) - float(lo["gross"]))
            return float(lo["net_monthly"]) + frac * (
                float(hi["net_monthly"]) - float(lo["net_monthly"])
            )

    return float(lookup[-1]["net_monthly"])


def _calc_brackets(taxable: float, tax_config: dict) -> float:
    """Calculate income tax from bracket list."""
    pa = tax_config.get("personal_allowance", 0)
    taxable = max(0, taxable - pa)
    tax = 0.0

    brackets = tax_config.get("brackets", [])
    prev_limit = 0

    for bracket in brackets:
        rate = bracket["rate"]
        lower = bracket.get("from", prev_limit)
        upper = bracket.get("up_to", float("inf"))

        if taxable > lower:
            taxable_in_bracket = min(taxable, upper) - lower
            tax += max(0, taxable_in_bracket) * rate

        prev_limit = upper

    return tax


def _calc_tax_credits(taxable: float, tax_config: dict) -> float:
    """Calculate total tax credits (heffingskortingen) that reduce tax payable."""
    total = 0.0
    for credit in tax_config.get("tax_credits", []):
        ctype = credit.get("type")
        if ctype == "phase_out_credit":
            total += _calc_phase_out_credit(taxable, credit)
        elif ctype == "piecewise_credit":
            total += _calc_piecewise_credit(taxable, credit)
    return total


def _calc_phase_out_credit(income: float, credit: dict) -> float:
    """Linear phase-out credit (e.g. Algemene Heffingskorting)."""
    max_c = credit["max_credit"]
    start = credit["phase_out_start"]
    end = credit.get("phase_out_end", float("inf"))
    rate = credit["phase_out_rate"]
    if income <= start:
        return float(max_c)
    elif income <= end:
        return max(0.0, float(max_c) - float(rate) * (income - float(start)))
    else:
        return 0.0


def _calc_piecewise_credit(income: float, credit: dict) -> float:
    """Piecewise-linear credit (e.g. Arbeidskorting with phase-in then phase-out)."""
    for band in credit["bands"]:
        lo = band.get("from", 0)
        hi_raw = band.get("to")
        hi = hi_raw if hi_raw is not None else float("inf")
        if lo <= income < hi or (hi == float("inf") and income >= lo):
            base = band.get("base", 0.0)
            rate = band.get("rate", 0.0)
            return max(0.0, float(base) + float(rate) * (income - float(lo)))
    return 0.0


def _calc_social(gross: float, country: dict) -> float:
    """Calculate employee social contributions."""
    total = 0.0
    for contrib in country.get("social_contributions", {}).get("employee", []):
        if "monthly_flat" in contrib:
            total += contrib["monthly_flat"] * 12
        elif "rate" in contrib:
            lower = contrib.get("from", 0)
            upper = contrib.get(
                "up_to",
                country.get("social_contributions", {}).get("cap_annual", float("inf"))
                or float("inf"),
            )
            base = max(0, min(gross, upper) - lower)
            total += base * contrib["rate"]
    return total


def _find_scheme(country: dict, scheme_id: str) -> dict[str, Any] | None:
    for s in country.get("special_schemes", []):
        if s.get("id") == scheme_id:
            return dict(s)
    return None


def get_schemes(country_code: str) -> list[dict]:
    """Return list of available special schemes for a country."""
    country = load_country(country_code)
    return [s for s in country.get("special_schemes", []) if s.get("type") != "informational"]


def find_target_gross(
    target_net_monthly_eur: float,
    country_code: str,
    active_schemes: list[str] | None = None,
    scheme_overrides: dict[str, dict] | None = None,
    tolerance_eur: float = 5.0,
    max_gross: float = 2_000_000.0,
) -> float:
    """
    Binary search for the annual gross (in local currency) that produces
    at least target_net_monthly_eur after all taxes and social contributions.

    scheme_overrides: passed through to calculate_net (e.g. for 27% ruling cliff calc).
    Returns the minimum gross (local currency, annual) needed to reach the target net.
    """
    active_schemes = active_schemes or []

    def net_at(gross: float) -> float:
        return float(
            calculate_net(gross, country_code, active_schemes, scheme_overrides=scheme_overrides)[
                "net_monthly_eur"
            ]
        )

    lo, hi = 0.0, max_gross

    # Edge cases
    if net_at(hi) < target_net_monthly_eur:
        return hi  # Target unreachable even at max gross — return cap
    if net_at(lo) >= target_net_monthly_eur:
        return lo  # Target already met at zero gross

    for _ in range(60):
        mid = (lo + hi) / 2.0
        if net_at(mid) < target_net_monthly_eur:
            lo = mid
        else:
            hi = mid
        if hi - lo < tolerance_eur:
            break

    return round(hi)


def find_gross_to_match_surplus(
    *,
    home_net_monthly_eur: float,
    home_expenses_eur: float,
    dest_expenses_eur: float,
    country_code: str,
    active_schemes: list[str] | None = None,
    scheme_overrides: dict[str, dict] | None = None,
) -> float:
    """Return the gross needed in dest country so monthly surplus matches home surplus.

    Home surplus  = home_net_monthly_eur - home_expenses_eur
    Target dest net = home_surplus + dest_expenses_eur
    """
    home_surplus = home_net_monthly_eur - home_expenses_eur
    target_net = home_surplus + dest_expenses_eur
    return find_target_gross(
        target_net_monthly_eur=target_net,
        country_code=country_code,
        active_schemes=active_schemes,
        scheme_overrides=scheme_overrides,
    )
