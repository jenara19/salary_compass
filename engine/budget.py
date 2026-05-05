"""
Cost of living aggregation engine.
Returns total monthly expenses and surplus for a given city + scenario.
"""

from __future__ import annotations
import yaml
from pathlib import Path

CITIES_DIR = Path(__file__).parent.parent / "data" / "cities"
COUNTRIES_DIR = Path(__file__).parent.parent / "data" / "countries"

DISPLAY_LABELS = {
    "rent_2bed": "Rent / Housing",
    "utilities": "Utilities",
    "health_extra": "Health insurance (extra)",
    "health_kvg": "Health insurance (KVG mandatory)",
    "groceries_2pax": "Groceries (2 people)",
    "transport_2pax": "Transport (2 people)",
    "eating_out": "Eating out",
    "leisure": "Leisure / Ocio",
    "misc": "Misc / Expat buffer",
    "travel": "Travel (flights)",
    "personal": "Personal spending",
}

# Per-category pax multipliers (2pax = 1.0 baseline, 1pax = reduced)
PAX_MULTIPLIERS = {
    "rent_2bed": {1: 1.0, 2: 1.0},
    "utilities": {1: 0.85, 2: 1.0},
    "health_extra": {1: 0.5, 2: 1.0},
    "health_kvg": {1: 0.5, 2: 1.0},
    "groceries_2pax": {1: 0.60, 2: 1.0},
    "transport_2pax": {1: 0.65, 2: 1.0},
    "eating_out": {1: 0.55, 2: 1.0},
    "leisure": {1: 0.70, 2: 1.0},
    "misc": {1: 0.75, 2: 1.0},
    "travel": {1: 0.70, 2: 1.0},
    "personal": {1: 0.5, 2: 1.0},
}


PORTABLE_CATEGORIES = {"travel", "personal"}  # don't scale by city — follow the user

# Categories where the DESTINATION city's cost is used directly from YAML, regardless
# of what the user currently spends at home.  Rationale:
#
#   Health (health_extra / health_kvg): set by the destination country's healthcare
#     system (e.g. free SNS vs mandatory ZVW vs mandatory KVG).  Cannot be ratio-scaled.
#
#   Infrastructure (utilities / transport_2pax): city-determined baseline costs that
#     exist independent of lifestyle choices.  A Zurich monthly transit pass costs
#     CHF 100+ whether you "prefer" public transport or not; Rotterdam utilities are
#     set by Dutch energy markets.  Scaling a user's €10 Madrid transport spend would
#     produce misleadingly low numbers for cities with objectively higher infrastructure
#     costs — the same problem we already fixed for health insurance.
#
#   Rent (rent_2bed): moving to a new city you reliably pay at or above the
#     "comfortable" market tier — furnished-apartment premium, lack of neighbourhood
#     knowledge, short-term-contract premium, and no time to search properly.
#     The YAML comfortable value is calibrated for exactly this newcomer profile.
YAML_ABSOLUTE_CATS = {
    "health_extra",
    "health_kvg",  # healthcare system (Tier 1)
    "utilities",
    "transport_2pax",  # city infrastructure (Tier 1)
    "rent_2bed",  # market anchored (Tier 2)
}

# Settling-in sensitivity per category.
# A value of 0.25 means: at 0% settled, this category costs 25% MORE than the
# pure ratio-scaled figure.  At 100% settled the multiplier collapses to 1.0.
# Applied only to non-home (destination) cities; home city is always unchanged.
#
# Formula:  cost = ratio_scaled × (1 + sensitivity × (1 − settling_factor))
#
#   eating_out  0.25 — strong exploration: restaurants, cafes, discovering the city
#   misc        0.20 — convenience tax + home-setup costs spread over first months
#   leisure     0.15 — cultural exploration: museums, gym memberships, events
#   groceries   0.10 — mild: you find the cheap supermarket within a few weeks
NEWCOMER_SENSITIVITIES: dict[str, float] = {
    "eating_out": 0.25,
    "misc": 0.20,
    "leisure": 0.15,
    "groceries_2pax": 0.10,
}


def _get_yaml_comfortable(col: dict, cat: str) -> float:
    """Return the comfortable cost for *cat* from a city's cost_of_living dict."""
    return (col.get(cat) or {}).get("comfortable", 0) or 0


def _resolve_health_comfortable(col: dict, primary_key: str) -> float:
    """
    Get ample value for the primary health insurance category in a city.
    Always prefers health_kvg (mandatory CH KVG system) over health_extra,
    because health_kvg is exclusively used for mandatory insurance while
    health_extra may be optional supplement (e.g. VVG in Zurich = CHF 130).
    """
    # health_kvg is always mandatory — prefer it as the "cost of healthcare here"
    v = col.get("health_kvg", {}).get("comfortable", 0) or 0
    if v == 0:
        v = col.get("health_extra", {}).get("comfortable", 0) or 0
    return v


def load_city(city_slug: str) -> dict:
    path = CITIES_DIR / f"{city_slug}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_country(code: str) -> dict:
    path = COUNTRIES_DIR / f"{code}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_cat_mult(key: str, category_multipliers: dict) -> float:
    """Get category multiplier, using health_extra as fallback for health_kvg."""
    if key in category_multipliers:
        return category_multipliers[key]
    if key == "health_kvg" and "health_extra" in category_multipliers:
        return category_multipliers["health_extra"]
    return 1.0


def calculate_budget_v2(
    city_slug: str,
    category_multipliers: dict,
    pax: int = 2,
    lifestyle_anchors: dict = None,
    partner_net_monthly_eur: float = 0.0,
) -> dict:
    """
    Calculate monthly expenses using the 'comfortable' baseline with custom multipliers.

    category_multipliers: {category_key: float}  e.g. {"eating_out": 1.3, "rent_2bed": 0.9}
      Baseline is always the 'comfortable' value from city YAML.
      Apply PAX_MULTIPLIERS first, then category_multipliers.

    lifestyle_anchors: {name: eur_amount}  e.g. {"Gym": 80, "Hobbies": 150}
      Added as separate line items; converted from EUR to local currency.

    partner_net_monthly_eur: if > 0, partner pays half of total burden (shown as negative line item).
    """
    category_multipliers = category_multipliers or {}
    lifestyle_anchors = lifestyle_anchors or {}
    pax = pax if pax in (1, 2) else 2

    city = load_city(city_slug)
    country = load_country(city["country"])
    eur_rate = country["eur_rate"]

    col = city["cost_of_living"]
    items = {}
    total_local = 0.0

    for key, values in col.items():
        if key not in DISPLAY_LABELS:
            continue
        base = values.get("comfortable", 0) or 0
        pax_mult = PAX_MULTIPLIERS.get(key, {}).get(pax, 1.0)
        cat_mult = _get_cat_mult(key, category_multipliers)
        value = base * pax_mult * cat_mult

        items[key] = {
            "label": DISPLAY_LABELS[key],
            "value_local": round(value),
            "value_eur": round(value * eur_rate),
            "fixed": values.get("fixed", False),
            "note": values.get("note", ""),
        }
        total_local += value

    # Add lifestyle anchors (user provides in EUR; convert to local)
    lifestyle_total_eur = 0.0
    for anchor_name, eur_amount in lifestyle_anchors.items():
        if eur_amount and eur_amount > 0:
            local_amount = eur_amount / eur_rate
            items[f"lifestyle_{anchor_name.lower()}"] = {
                "label": f"🎯 {anchor_name}",
                "value_local": round(local_amount),
                "value_eur": round(eur_amount),
                "fixed": True,
                "note": "Lifestyle anchor (portable expense)",
            }
            total_local += local_amount
            lifestyle_total_eur += eur_amount

    total_eur = total_local * eur_rate

    # Partner contribution: partner pays half the total burden
    partner_contrib_eur = 0.0
    if partner_net_monthly_eur > 0:
        partner_contrib_eur = partner_net_monthly_eur / 2
        partner_local = partner_contrib_eur / eur_rate
        items["partner_contribution"] = {
            "label": "💑 Partner contribution (−)",
            "value_local": round(-partner_local),
            "value_eur": round(-partner_contrib_eur),
            "fixed": False,
            "note": "Partner covers half of shared household costs",
        }
        total_local -= partner_local
        total_eur -= partner_contrib_eur

    return {
        "city": city["name"],
        "country": city["country"],
        "currency": city["currency"],
        "eur_rate": eur_rate,
        "scenario": "custom",
        "items": items,
        "total_local": round(total_local),
        "total_eur": round(total_eur),
        "hidden_costs": city.get("hidden_costs", []),
        "lifestyle_total_eur": round(lifestyle_total_eur),
        "partner_contrib_eur": round(partner_contrib_eur),
    }


def calculate_budget(city_slug: str, scenario: str = "comfortable") -> dict:
    """
    Calculate monthly expenses for a city at a given scenario (great/ample/modest).
    Returns itemised breakdown and total in local currency.
    """
    city = load_city(city_slug)
    country = load_country(city["country"])
    eur_rate = country["eur_rate"]

    scenario = scenario.lower()
    col = city["cost_of_living"]

    items = {}
    total_local = 0.0

    for key, values in col.items():
        if key not in DISPLAY_LABELS:
            continue
        value = values.get(scenario, values.get("comfortable", 0)) or 0
        items[key] = {
            "label": DISPLAY_LABELS[key],
            "value_local": value,
            "value_eur": round(value * eur_rate),
            "fixed": values.get("fixed", False),
            "note": values.get("note", ""),
        }
        total_local += value

    return {
        "city": city["name"],
        "country": city["country"],
        "currency": city["currency"],
        "eur_rate": eur_rate,
        "scenario": scenario,
        "items": items,
        "total_local": round(total_local),
        "total_eur": round(total_local * eur_rate),
        "hidden_costs": city.get("hidden_costs", []),
    }


def calculate_surplus(net_monthly_eur: float, budget: dict) -> dict:
    """Calculate monthly surplus/deficit."""
    surplus_eur = net_monthly_eur - budget["total_eur"]
    return {
        "net_monthly_eur": round(net_monthly_eur),
        "total_expenses_eur": budget["total_eur"],
        "surplus_eur": round(surplus_eur),
        "is_positive": surplus_eur >= 0,
    }


def scale_expenses_to_city(
    user_expenses: dict,
    home_city_slug: str,
    target_city_slug: str,
    lifestyle_anchors: dict,
    pax: int = 2,
    settling_factor: float = 0.5,
) -> dict:
    """
    Scale user's home-city expenses to a target city using the 4-tier model.

    Tier 1 — Mandatory city cost (YAML absolute, PAX-scaled):
        health_extra, health_kvg, utilities, transport_2pax

    Tier 2 — Market anchored (YAML absolute, comfortable = realistic newcomer):
        rent_2bed

    Tier 3 — Newcomer inflated (ratio-scaled × settling-in factor):
        eating_out, misc, leisure, groceries_2pax
        cost = ratio_scaled × (1 + sensitivity × (1 − settling_factor))
        settling_factor: 0.0 = just arrived, 1.0 = fully settled

    Tier 4 — Portable (unchanged):
        travel, personal

    Ratio is capped at [0.5, 3.0] to avoid wild extrapolation.
    Returns total_eur and items dict in same format as calculate_budget_v2.
    """
    home_city = load_city(home_city_slug)
    target_city = load_city(target_city_slug)
    target_country = load_country(target_city["country"])
    eur_rate = target_country["eur_rate"]

    home_col = home_city["cost_of_living"]
    target_col = target_city["cost_of_living"]

    items = {}
    total_eur = 0.0

    for cat, user_eur in user_expenses.items():
        if cat in PORTABLE_CATEGORIES:
            # Tier 4: portable — follow the user
            scaled_eur = user_eur
            note = "Portable"

        elif cat in YAML_ABSOLUTE_CATS:
            # Tier 1 & 2: city/market-determined — use destination YAML comfortable
            if cat in {"health_extra", "health_kvg"}:
                target_ref = _resolve_health_comfortable(target_col, cat)
                note = "City rate (YAML): healthcare set by destination country"
            elif cat == "rent_2bed":
                target_ref = _get_yaml_comfortable(target_col, cat)
                note = "City rate (YAML): market anchored — comfortable tier reflects newcomer cost"
            else:
                target_ref = _get_yaml_comfortable(target_col, cat)
                note = "City rate (YAML): infrastructure cost fixed by destination city"
            pax_mult = PAX_MULTIPLIERS.get(cat, {}).get(pax, 1.0)
            scaled_eur = target_ref * pax_mult * eur_rate

        else:
            # Tier 3: ratio-scale from home city, then apply newcomer premium
            home_ref = home_col.get(cat, {}).get("comfortable", 0) or 0
            target_ref = target_col.get(cat, {}).get("comfortable", 0) or 0
            if home_ref > 0 and target_ref > 0:
                ratio = max(0.5, min(3.0, target_ref / home_ref))
                base_scaled = user_eur * ratio
                sensitivity = NEWCOMER_SENSITIVITIES.get(cat, 0.0)
                newcomer_mult = 1.0 + sensitivity * (
                    1.0 - max(0.0, min(1.0, settling_factor))
                )
                scaled_eur = base_scaled * newcomer_mult
                if sensitivity > 0 and newcomer_mult > 1.001:
                    note = (
                        f"Scaled from home (×{ratio:.2f}) + "
                        f"{(newcomer_mult - 1) * 100:.0f}% settling-in premium"
                    )
                else:
                    note = f"Scaled from home city (×{ratio:.2f})"
            elif home_ref == 0 and target_ref > 0:
                scaled_eur = target_ref * eur_rate
                note = "YAML estimate (not applicable in home city)"
            else:
                scaled_eur = user_eur
                note = "Unchanged (no reference data)"

        scaled_local = scaled_eur / eur_rate if eur_rate != 1.0 else scaled_eur

        items[cat] = {
            "label": DISPLAY_LABELS.get(cat, cat),
            "value_local": round(scaled_local),
            "value_eur": round(scaled_eur),
            "fixed": cat in PORTABLE_CATEGORIES,
            "note": note,
        }
        total_eur += scaled_eur

    for anchor_key, anchor_eur in (lifestyle_anchors or {}).items():
        if anchor_eur <= 0:
            continue
        anchor_local = anchor_eur / eur_rate if eur_rate != 1.0 else anchor_eur
        label = anchor_key.replace("_", " ").title()
        items[f"anchor_{anchor_key}"] = {
            "label": f"🎯 {label}",
            "value_local": round(anchor_local),
            "value_eur": round(anchor_eur),
            "fixed": True,
            "note": "Lifestyle anchor — portable",
        }
        total_eur += anchor_eur

    return {
        "city": target_city["name"],
        "country": target_city["country"],
        "currency": target_city["currency"],
        "eur_rate": eur_rate,
        "items": items,
        "total_local": round(total_eur / eur_rate if eur_rate != 1.0 else total_eur),
        "total_eur": round(total_eur),
        "hidden_costs": target_city.get("hidden_costs", []),
        "source": "user_actuals_scaled",
    }


def distribute_total_to_categories(
    total_eur: float, city_slug: str, pax: int = 2
) -> dict:
    """
    Distribute a total monthly expense figure across categories
    using city YAML ample values as proportional weights.
    Returns {cat_key: eur_value}.
    """
    city = load_city(city_slug)
    country = load_country(city["country"])
    eur_rate = country["eur_rate"]
    col = city["cost_of_living"]

    weights = {}
    for cat in DISPLAY_LABELS:
        if cat == "health_kvg":
            continue  # absorbed into health_extra bucket via _resolve_health_comfortable
        if cat == "health_extra":
            val = _resolve_health_comfortable(col, cat)
        else:
            val = col.get(cat, {}).get("comfortable", 0) or 0
        pax_mult = PAX_MULTIPLIERS.get(cat, {}).get(pax, 1.0)
        weights[cat] = val * pax_mult * eur_rate  # convert to EUR

    total_weight = sum(weights.values()) or 1.0
    return {cat: round(total_eur * w / total_weight) for cat, w in weights.items()}


def list_cities() -> list[dict]:
    """List all available cities with their country."""
    cities = []
    for path in sorted(CITIES_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cities.append(
            {
                "slug": path.stem,
                "name": data["name"],
                "country": data["country"],
                "currency": data["currency"],
            }
        )
    return cities
