"""
Tests for engine/budget.py

Run with:  python -m pytest tests/ -v
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from engine.budget import (
    DISPLAY_LABELS,
    YAML_ABSOLUTE_CATS,
    calculate_budget,
    calculate_budget_v2,
    distribute_total_to_categories,
    scale_expenses_to_city,
)

# ── Health-insurance system-difference fix ─────────────────────────────────────


class TestHealthScaling:
    """
    Health insurance must always use the TARGET city's YAML value, never scale
    from the home city.  Key scenario: Madrid user (free SNS = €0-80) vs
    Rotterdam (mandatory ZVW ≈ €400/mo).
    """

    def test_rotterdam_health_not_scaled_from_madrid_zero(self):
        """If Madrid user spends €0 on health, Rotterdam must still show ~€400."""
        madrid_expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 0,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(madrid_expenses, "madrid", "rotterdam", {}, pax=2)
        health_eur = result["items"]["health_extra"]["value_eur"]
        # Rotterdam YAML comfortable health_extra should be used directly (≥ 300)
        assert health_eur >= 300, (
            f"Rotterdam health should use YAML estimate (≥€300), got €{health_eur}. "
            "Health cannot be scaled from free SNS (€0) to mandatory ZVW."
        )

    def test_rotterdam_health_not_scaled_from_madrid_low(self):
        """Even if Madrid user has small optional private cover, Rotterdam uses YAML."""
        madrid_expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(madrid_expenses, "madrid", "rotterdam", {}, pax=2)
        health_eur = result["items"]["health_extra"]["value_eur"]
        # Old (broken) behavior: 80 × 3.0 (capped) = 240 — wrong
        # Correct: use Rotterdam YAML comfortable = ~400
        assert health_eur >= 300, (
            f"Rotterdam health should use YAML (≥€300), got €{health_eur}. "
            "Scaling €80 Madrid optional cover to Rotterdam mandatory ZVW is wrong."
        )

    def test_zurich_health_kvg_resolved_from_health_extra(self):
        """
        User expense is tracked as 'health_extra'; Zurich YAML uses 'health_kvg'.
        scale_expenses_to_city must resolve the alias and return the KVG comfortable value.
        """
        madrid_expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(madrid_expenses, "madrid", "zurich", {}, pax=2)
        health_eur = result["items"]["health_extra"]["value_eur"]
        # Zurich KVG comfortable = 760 CHF; at ~1.0 eur_rate equiv should be > 500 EUR
        assert health_eur > 500, (
            f"Zurich health should use KVG comfortable (~CHF 760 > €700 equiv), got €{health_eur}."
        )

    def test_london_health_stays_low(self):
        """London NHS is free — health_extra should be low/zero when coming from Madrid."""
        madrid_expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(madrid_expenses, "madrid", "london", {}, pax=2)
        health_eur = result["items"]["health_extra"]["value_eur"]
        # London YAML health_extra should be low (NHS is free; optional private ~£40-100)
        # In EUR: < 150
        assert health_eur < 200, (
            f"London health should be low (NHS free, optional private ~€40-100), got €{health_eur}."
        )

    def test_yaml_absolute_cats_set(self):
        """health_extra and health_kvg must be in YAML_ABSOLUTE_CATS."""
        assert "health_extra" in YAML_ABSOLUTE_CATS
        assert "health_kvg" in YAML_ABSOLUTE_CATS


# ── Portable categories ────────────────────────────────────────────────────────


class TestPortableCategories:
    def test_travel_unchanged(self):
        """Travel is portable — should not be scaled between cities."""
        expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(expenses, "madrid", "rotterdam", {}, pax=2)
        assert result["items"]["travel"]["value_eur"] == 350

    def test_personal_unchanged(self):
        """Personal spending is portable — same value in every city."""
        expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(expenses, "madrid", "zurich", {}, pax=2)
        assert result["items"]["personal"]["value_eur"] == 700


# ── Scaling ratio (lifestyle categories) ──────────────────────────────────────


class TestScalingRatio:
    def test_rent_amsterdam_uses_yaml_comfortable(self):
        """rent_2bed is now YAML-absolute (Tier 2) — returns Amsterdam YAML comfortable."""
        expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(expenses, "madrid", "amsterdam", {}, pax=2)
        rent_eur = result["items"]["rent_2bed"]["value_eur"]
        # Amsterdam comfortable rent is notably higher than Madrid (~€1800)
        assert rent_eur > 1500, (
            f"Amsterdam rent YAML comfortable should exceed €1500, got €{rent_eur}"
        )

    def test_rent_note_indicates_market_anchored(self):
        """rent_2bed note must say YAML/market-anchored."""
        expenses = {
            "rent_2bed": 100,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result = scale_expenses_to_city(expenses, "madrid", "amsterdam", {}, pax=2)
        note = result["items"]["rent_2bed"]["note"]
        assert "YAML" in note or "market" in note.lower(), (
            f"Rent note should indicate YAML/market anchored, got: '{note}'"
        )

    def test_rent_in_yaml_absolute_cats(self):
        """rent_2bed must be in YAML_ABSOLUTE_CATS."""
        from engine.budget import YAML_ABSOLUTE_CATS

        assert "rent_2bed" in YAML_ABSOLUTE_CATS

    def test_groceries_ratio_scales_up_madrid_to_amsterdam(self):
        """Groceries (Tier 3) should still ratio-scale between cities."""
        expenses = {
            "rent_2bed": 1200,
            "utilities": 150,
            "health_extra": 80,
            "groceries_2pax": 600,
            "transport_2pax": 50,
            "eating_out": 180,
            "leisure": 100,
            "misc": 200,
            "travel": 350,
            "personal": 700,
        }
        result_madrid = scale_expenses_to_city(
            expenses, "madrid", "madrid", {}, pax=2, settling_factor=1.0
        )
        result_amsterdam = scale_expenses_to_city(
            expenses, "madrid", "amsterdam", {}, pax=2, settling_factor=1.0
        )
        # Amsterdam groceries should be higher than Madrid (more expensive city)
        assert (
            result_amsterdam["items"]["groceries_2pax"]["value_eur"]
            >= result_madrid["items"]["groceries_2pax"]["value_eur"]
        ), "Amsterdam groceries should be >= Madrid at settling_factor=1.0"


# ── calculate_budget basic smoke tests ────────────────────────────────────────


class TestCalculateBudget:
    @pytest.mark.parametrize(
        "city,scenario",
        [
            ("madrid", "comfortable"),
            ("rotterdam", "comfortable"),
            ("zurich", "comfortable"),
            ("amsterdam", "frugal"),
            ("london", "generous"),
            ("berlin", "comfortable"),
            ("oslo", "comfortable"),
            ("munich", "comfortable"),
        ],
    )
    def test_budget_returns_positive_total(self, city, scenario):
        result = calculate_budget(city, scenario)
        assert result["total_local"] > 0
        assert result["total_eur"] > 0
        assert "items" in result

    def test_zurich_budget_has_health_kvg(self):
        result = calculate_budget("zurich", "comfortable")
        assert "health_kvg" in result["items"], "Zurich budget must include health_kvg"
        assert result["items"]["health_kvg"]["value_local"] > 0

    def test_rotterdam_budget_has_health_extra(self):
        result = calculate_budget("rotterdam", "comfortable")
        assert "health_extra" in result["items"], "Rotterdam budget must include health_extra"
        assert result["items"]["health_extra"]["value_eur"] >= 300

    def test_madrid_health_is_low(self):
        result = calculate_budget("madrid", "comfortable")
        health = result["items"].get("health_extra", {})
        # Madrid optional private: comfortable ≤ €150/mo
        assert health.get("value_eur", 0) <= 150, (
            "Madrid health_extra comfortable should be low (optional private only, NHS/SNS free)"
        )

    def test_scenario_ordering(self):
        """generous > comfortable > frugal for total expenses."""
        for city in ("madrid", "rotterdam", "zurich", "amsterdam"):
            frugal = calculate_budget(city, "frugal")["total_eur"]
            comfortable = calculate_budget(city, "comfortable")["total_eur"]
            generous = calculate_budget(city, "generous")["total_eur"]
            assert frugal <= comfortable <= generous, (
                f"{city}: expected frugal ≤ comfortable ≤ generous, "
                f"got {frugal} / {comfortable} / {generous}"
            )

    def test_hidden_costs_present(self):
        """All cities should have at least 1 hidden cost."""
        for city in ("madrid", "rotterdam", "zurich", "amsterdam", "london"):
            result = calculate_budget(city, "comfortable")
            assert len(result.get("hidden_costs", [])) > 0, f"{city} should have hidden_costs"


# ── calculate_budget_v2 ────────────────────────────────────────────────────────


class TestCalculateBudgetV2:
    def test_returns_expected_structure(self):
        result = calculate_budget_v2("madrid", {}, pax=2, lifestyle_anchors={})
        assert "items" in result
        assert "total_eur" in result
        assert result["total_eur"] > 0

    def test_category_multiplier_applied(self):
        base = calculate_budget_v2("madrid", {}, pax=2)
        double = calculate_budget_v2("madrid", {"eating_out": 2.0}, pax=2)
        assert double["items"]["eating_out"]["value_eur"] == pytest.approx(
            base["items"]["eating_out"]["value_eur"] * 2, abs=5
        )

    def test_lifestyle_anchor_added(self):
        result = calculate_budget_v2("madrid", {}, pax=2, lifestyle_anchors={"Gym": 100})
        assert "lifestyle_gym" in result["items"]
        assert result["items"]["lifestyle_gym"]["value_eur"] == 100

    def test_zurich_health_kvg_multiplier_propagates(self):
        """Scenario multiplier applied to health_extra should also affect health_kvg."""
        base = calculate_budget_v2("zurich", {}, pax=2)
        scaled = calculate_budget_v2("zurich", {"health_kvg": 1.5}, pax=2)
        base_h = base["items"]["health_kvg"]["value_local"]
        scale_h = scaled["items"]["health_kvg"]["value_local"]
        assert scale_h == pytest.approx(base_h * 1.5, abs=10)


# ── distribute_total_to_categories ────────────────────────────────────────────


class TestDistribute:
    def test_distribution_sums_to_total(self):
        total = 4000.0
        dist = distribute_total_to_categories(total, "madrid", pax=2)
        # Sum of distributed values should be close to total (rounding allowed)
        assert abs(sum(dist.values()) - total) < 50, (
            f"Distribution should sum to ~{total}, got {sum(dist.values())}"
        )

    def test_all_display_label_keys_present(self):
        dist = distribute_total_to_categories(4000.0, "madrid", pax=2)
        # health_kvg is intentionally absorbed into health_extra bucket
        # (CH cities' KVG cost is represented via _resolve_health_comfortable under health_extra)
        expected_keys = {k for k in DISPLAY_LABELS if k != "health_kvg"}
        for key in expected_keys:
            assert key in dist, f"Key {key!r} missing from distribution"
        assert "health_kvg" not in dist, "health_kvg should be absorbed into health_extra"

    def test_zurich_health_distributed_via_kvg(self):
        """For a CH city, health_extra bucket should reflect the larger KVG amount."""
        dist_zurich = distribute_total_to_categories(4000.0, "zurich", pax=2)
        dist_madrid = distribute_total_to_categories(4000.0, "madrid", pax=2)
        assert "health_kvg" not in dist_zurich, "health_kvg should not appear as separate key"
        assert dist_zurich["health_extra"] > dist_madrid["health_extra"], (
            "Zurich health_extra should be larger than Madrid's (KVG > SNS optional private)"
        )


# ── YAML validity ──────────────────────────────────────────────────────────────


class TestYamlValidity:
    CITY_SLUGS: ClassVar[list[str]] = [
        "madrid",
        "barcelona",
        "amsterdam",
        "rotterdam",
        "berlin",
        "munich",
        "london",
        "manchester",
        "oslo",
        "zurich",
        "geneva",
    ]

    @pytest.mark.parametrize("city", CITY_SLUGS)
    def test_all_cities_load(self, city):
        from engine.budget import load_city, load_country

        data = load_city(city)
        assert data["name"]
        assert data["country"]
        country = load_country(data["country"])
        assert country["eur_rate"] > 0

    @pytest.mark.parametrize("city", CITY_SLUGS)
    def test_required_keys_present(self, city):
        from engine.budget import load_city

        col = load_city(city)["cost_of_living"]
        required = {"rent_2bed", "groceries_2pax", "transport_2pax", "eating_out"}
        for key in required:
            assert key in col, f"{city} missing required CoL key: {key}"

    @pytest.mark.parametrize("city", CITY_SLUGS)
    def test_comfortable_values_positive(self, city):
        from engine.budget import load_city

        col = load_city(city)["cost_of_living"]
        for key, vals in col.items():
            if key in DISPLAY_LABELS:
                comfortable = vals.get("comfortable", 0)
                assert comfortable > 0, f"{city}.{key}.comfortable should be > 0"

    def test_swiss_cities_use_health_kvg(self):
        from engine.budget import load_city

        for city in ("zurich", "geneva"):
            col = load_city(city)["cost_of_living"]
            assert "health_kvg" in col, f"{city} should use health_kvg key"

    def test_ch_eur_rate_reasonable(self):
        from engine.budget import load_country

        ch = load_country("CH")
        # 1 CHF ≈ 1.0 EUR; EUR rate should be around 0.95–1.10
        assert 0.8 < ch["eur_rate"] < 1.2, f"CH eur_rate looks wrong: {ch['eur_rate']}"


# ── PAX multiplier for health in scale_expenses_to_city ───────────────────────


class TestPaxHealthScaling:
    """Bug fix: health insurance must respect pax=1 multiplier in scale_expenses_to_city."""

    BASE_EXPENSES: ClassVar[dict[str, int]] = {
        "rent_2bed": 1200,
        "utilities": 150,
        "health_extra": 80,
        "groceries_2pax": 600,
        "transport_2pax": 50,
        "eating_out": 180,
        "leisure": 100,
        "misc": 200,
        "travel": 350,
        "personal": 700,
    }

    def test_single_person_health_is_half_of_two_person(self):
        """pax=1 health should be ≈ half of pax=2 (PAX_MULTIPLIER health = 0.5 for single)."""
        two_pax = scale_expenses_to_city(self.BASE_EXPENSES, "madrid", "rotterdam", {}, pax=2)
        one_pax = scale_expenses_to_city(self.BASE_EXPENSES, "madrid", "rotterdam", {}, pax=1)
        h2 = two_pax["items"]["health_extra"]["value_eur"]
        h1 = one_pax["items"]["health_extra"]["value_eur"]
        assert h1 == pytest.approx(h2 * 0.5, abs=5), (
            f"Single-person health EUR {h1} should be ~half of 2-person EUR {h2}"
        )

    def test_single_person_zurich_kvg_is_halved(self):
        """KVG (CH) for pax=1 should be ~half the 2-person YAML comfortable value."""
        two_pax = scale_expenses_to_city(self.BASE_EXPENSES, "madrid", "zurich", {}, pax=2)
        one_pax = scale_expenses_to_city(self.BASE_EXPENSES, "madrid", "zurich", {}, pax=1)
        # health_extra key holds the resolved KVG value
        h2 = two_pax["items"]["health_extra"]["value_eur"]
        h1 = one_pax["items"]["health_extra"]["value_eur"]
        assert h1 < h2, "Single-person Zurich health should be less than 2-person"
        assert h1 == pytest.approx(h2 * 0.5, abs=10)

    def test_two_person_health_uses_full_yaml_value(self):
        """pax=2 (2-person baseline) should use the full comfortable YAML value."""
        result = scale_expenses_to_city(self.BASE_EXPENSES, "madrid", "rotterdam", {}, pax=2)
        health_eur = result["items"]["health_extra"]["value_eur"]
        # Rotterdam comfortable health_extra = 345 EUR (2 pax)
        assert health_eur == pytest.approx(345, abs=5)


# -- Infrastructure categories (Option C): YAML-absolute for transport & utilities --


class TestInfrastructureScaling:
    """
    transport_2pax and utilities must use the destination city YAML comfortable value,
    not the user home-city spend ratio-scaled.

    Rationale: a user who walks everywhere in Madrid (10 EUR/mo transport) does not
    mean they would spend 7 EUR in Rotterdam. The city infrastructure has an objective
    cost floor regardless of lifestyle habits.
    """

    FRUGAL_TRANSPORT_MADRID: ClassVar[dict[str, int]] = {
        "rent_2bed": 1200,
        "utilities": 150,
        "health_extra": 80,
        "groceries_2pax": 600,
        "transport_2pax": 10,
        "eating_out": 180,
        "leisure": 100,
        "misc": 200,
        "travel": 350,
        "personal": 700,
    }

    FRUGAL_UTILITIES_MADRID: ClassVar[dict[str, int]] = {
        "rent_2bed": 1200,
        "utilities": 20,
        "health_extra": 80,
        "groceries_2pax": 600,
        "transport_2pax": 50,
        "eating_out": 180,
        "leisure": 100,
        "misc": 200,
        "travel": 350,
        "personal": 700,
    }

    def test_rotterdam_transport_uses_yaml_not_scaled_from_low_madrid(self):
        result = scale_expenses_to_city(
            self.FRUGAL_TRANSPORT_MADRID, "madrid", "rotterdam", {}, pax=2
        )
        transport_eur = result["items"]["transport_2pax"]["value_eur"]
        assert transport_eur >= 100, (
            f"Rotterdam transport should use YAML (>=100), got {transport_eur}."
        )

    def test_rotterdam_transport_not_ratio_scaled_from_madrid(self):
        result = scale_expenses_to_city(
            self.FRUGAL_TRANSPORT_MADRID, "madrid", "rotterdam", {}, pax=2
        )
        transport_eur = result["items"]["transport_2pax"]["value_eur"]
        assert transport_eur > 20, (
            f"Rotterdam transport ({transport_eur}) looks ratio-scaled from 10 EUR input."
        )

    def test_rotterdam_utilities_uses_yaml_not_scaled_from_low_madrid(self):
        result = scale_expenses_to_city(
            self.FRUGAL_UTILITIES_MADRID, "madrid", "rotterdam", {}, pax=2
        )
        utilities_eur = result["items"]["utilities"]["value_eur"]
        assert utilities_eur >= 150, (
            f"Rotterdam utilities should use YAML (>=150), got {utilities_eur}."
        )

    def test_zurich_transport_pax1_less_than_pax2(self):
        two_pax = scale_expenses_to_city(
            self.FRUGAL_TRANSPORT_MADRID, "madrid", "zurich", {}, pax=2
        )
        one_pax = scale_expenses_to_city(
            self.FRUGAL_TRANSPORT_MADRID, "madrid", "zurich", {}, pax=1
        )
        t2 = two_pax["items"]["transport_2pax"]["value_eur"]
        t1 = one_pax["items"]["transport_2pax"]["value_eur"]
        assert t1 < t2, "Single-person Zurich transport should be less than 2-person"

    def test_infrastructure_cats_in_yaml_absolute_set(self):
        assert "utilities" in YAML_ABSOLUTE_CATS
        assert "transport_2pax" in YAML_ABSOLUTE_CATS

    def test_note_indicates_city_rate(self):
        result = scale_expenses_to_city(
            self.FRUGAL_TRANSPORT_MADRID, "madrid", "rotterdam", {}, pax=2
        )
        note = result["items"]["transport_2pax"]["note"]
        assert "YAML" in note or "city" in note.lower(), (
            f"Transport note should mention YAML/city rate, got: '{note}'"
        )


# -- Newcomer settling-in sensitivity (Tier 3) ---------------------------------


class TestNewcomerSensitivity:
    """
    Tier 3 categories apply a newcomer premium controlled by settling_factor.
    settling_factor=0.0 means just arrived (max premium).
    settling_factor=1.0 means fully settled (no premium, pure ratio).
    """

    BASE: ClassVar[dict[str, int]] = {
        "rent_2bed": 1200,
        "utilities": 150,
        "health_extra": 80,
        "groceries_2pax": 600,
        "transport_2pax": 140,
        "eating_out": 300,
        "leisure": 150,
        "misc": 200,
        "travel": 350,
        "personal": 700,
    }

    def test_eating_out_higher_when_just_arrived(self):
        """eating_out at settling=0 must be higher than at settling=1."""
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        assert (
            arrived["items"]["eating_out"]["value_eur"]
            > settled["items"]["eating_out"]["value_eur"]
        ), "eating_out at settling=0 should be higher than at settling=1"

    def test_eating_out_max_premium_is_25_pct(self):
        """At settling=0, eating_out should be exactly 1.25x the settled value."""
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        ratio = (
            arrived["items"]["eating_out"]["value_eur"]
            / settled["items"]["eating_out"]["value_eur"]
        )
        assert ratio == pytest.approx(1.25, abs=0.02), (
            f"eating_out newcomer premium at settling=0 should be 1.25x, got {ratio:.3f}"
        )

    def test_misc_max_premium_is_20_pct(self):
        """At settling=0, misc should be 1.20x the settled value."""
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        ratio = arrived["items"]["misc"]["value_eur"] / settled["items"]["misc"]["value_eur"]
        assert ratio == pytest.approx(1.20, abs=0.02), (
            f"misc newcomer premium at settling=0 should be 1.20x, got {ratio:.3f}"
        )

    def test_groceries_max_premium_is_10_pct(self):
        """At settling=0, groceries should be 1.10x the settled value."""
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        ratio = (
            arrived["items"]["groceries_2pax"]["value_eur"]
            / settled["items"]["groceries_2pax"]["value_eur"]
        )
        assert ratio == pytest.approx(1.10, abs=0.02), (
            f"groceries newcomer premium at settling=0 should be 1.10x, got {ratio:.3f}"
        )

    def test_no_premium_on_home_city(self):
        """Settling-in premium must NOT apply to the home city (it is not called for home)."""
        # When city == home_city the code takes the home path, not scale_expenses_to_city.
        # Here we just confirm settling=0 and settling=1 produce identical results for
        # a case where ratio=1 (home to home would use a different path, so we use a
        # category with no newcomer sensitivity as a control).
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        # travel is portable (no newcomer effect) -- should be identical
        assert arrived["items"]["travel"]["value_eur"] == settled["items"]["travel"]["value_eur"], (
            "Portable categories must not be affected by settling_factor"
        )

    def test_settling_factor_50_is_between_0_and_100(self):
        """Default settling=0.5 must produce a value between settled and just-arrived."""
        arrived = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.0
        )
        half = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=0.5
        )
        settled = scale_expenses_to_city(
            self.BASE, "madrid", "rotterdam", {}, pax=2, settling_factor=1.0
        )
        eat_arrived = arrived["items"]["eating_out"]["value_eur"]
        eat_half = half["items"]["eating_out"]["value_eur"]
        eat_settled = settled["items"]["eating_out"]["value_eur"]
        assert eat_settled <= eat_half <= eat_arrived, (
            f"settling=0.5 eating_out ({eat_half}) should be between "
            f"settled ({eat_settled}) and just-arrived ({eat_arrived})"
        )
