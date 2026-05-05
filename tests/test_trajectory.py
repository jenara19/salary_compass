"""
Tests for engine/trajectory.py and engine/budget.calculate_surplus

Run with:  cd C:\\Personal\\salary-compass && python -m pytest tests/ -v
"""
import pytest
from engine.trajectory import calculate_trajectory
from engine.budget import calculate_budget_v2, calculate_surplus


BASE_EXPENSES = {
    "rent_2bed": 1200, "utilities": 150, "health_extra": 80,
    "groceries_2pax": 600, "transport_2pax": 50, "eating_out": 180,
    "leisure": 100, "misc": 200, "travel": 350, "personal": 700,
}


# ── calculate_surplus ──────────────────────────────────────────────────────────

class TestCalculateSurplus:
    def test_positive_surplus(self):
        result = calculate_surplus(5000, {"total_eur": 3500})
        assert result["surplus_eur"] == 1500
        assert result["is_positive"] is True

    def test_negative_surplus(self):
        result = calculate_surplus(3000, {"total_eur": 4000})
        assert result["surplus_eur"] == -1000
        assert result["is_positive"] is False

    def test_zero_surplus(self):
        result = calculate_surplus(3000, {"total_eur": 3000})
        assert result["surplus_eur"] == 0
        assert result["is_positive"] is True

    def test_return_keys(self):
        result = calculate_surplus(4000, {"total_eur": 3000})
        assert "surplus_eur" in result
        assert "net_monthly_eur" in result
        assert "total_expenses_eur" in result
        assert result["net_monthly_eur"] == 4000
        assert result["total_expenses_eur"] == 3000


# ── calculate_trajectory structure ────────────────────────────────────────────

class TestTrajectoryStructure:
    def test_returns_10_years_by_default(self):
        traj = calculate_trajectory(57500, "ES", "madrid", expenses_eur=3500)
        assert len(traj) == 10

    def test_returns_correct_year_count(self):
        traj = calculate_trajectory(57500, "ES", "madrid", years=5, expenses_eur=3500)
        assert len(traj) == 5

    def test_year_index(self):
        traj = calculate_trajectory(57500, "ES", "madrid", expenses_eur=3500)
        assert traj[0]["year"] == 1
        assert traj[-1]["year"] == 10

    def test_required_keys(self):
        traj = calculate_trajectory(57500, "ES", "madrid", expenses_eur=3000)
        row = traj[0]
        for key in ("year", "gross_annual_local", "net_monthly_eur",
                    "total_expenses_eur", "surplus_monthly_eur", "cumulative_savings_eur",
                    "effective_rate"):
            assert key in row, f"Missing key: {key}"


# ── expenses_eur parameter (regression test for budget/trajectory mismatch) ───

class TestExpensesEurParam:
    """
    Regression tests for the bug where trajectory used calculate_budget_v2 internally
    (YAML-based) while the matrix used get_budget_for_city (actuals-scaled),
    producing different expense figures for the same scenario.

    Fix: trajectory now accepts expenses_eur from the caller so both always agree.
    """

    def test_expenses_eur_used_when_provided(self):
        """Trajectory must use the exact expenses_eur value passed in year 1."""
        fixed_expenses = 4192.0  # value from matrix (actuals-scaled to Rotterdam)
        traj = calculate_trajectory(85000, "NL", "rotterdam", expenses_eur=fixed_expenses, col_inflation_rate=0.0)
        for row in traj:
            assert row["total_expenses_eur"] == pytest.approx(fixed_expenses, abs=1), (
                f"Year {row['year']}: expected expenses {fixed_expenses}, "
                f"got {row['total_expenses_eur']}"
            )

    def test_expenses_eur_constant_across_all_years_when_no_inflation(self):
        """With col_inflation_rate=0, expenses should stay flat every year."""
        traj = calculate_trajectory(57500, "ES", "madrid", expenses_eur=3004.0, col_inflation_rate=0.0)
        expenses = [row["total_expenses_eur"] for row in traj]
        assert len(set(expenses)) == 1, (
            f"Expenses should be constant with 0% CoL inflation, got: {expenses}"
        )

    def test_expenses_eur_different_from_yaml_baseline(self):
        """
        Without expenses_eur, trajectory uses YAML comfortable baseline.
        The actuals-based figure (expenses_eur) should be accepted and respected
        even when it differs from the YAML baseline.
        """
        yaml_budget = calculate_budget_v2("rotterdam", {}, pax=1)
        yaml_total = yaml_budget["total_eur"]

        actuals_based = yaml_total * 0.75  # 25% below YAML (plausible for frugal user)
        traj = calculate_trajectory(85000, "NL", "rotterdam", expenses_eur=actuals_based)
        assert traj[0]["total_expenses_eur"] == pytest.approx(actuals_based, abs=1)

    def test_surplus_consistent_with_expenses_eur(self):
        """surplus_monthly_eur must equal net_monthly_eur - expenses_eur in year 1."""
        traj = calculate_trajectory(85000, "NL", "rotterdam", expenses_eur=4192.0)
        row = traj[0]
        expected_surplus = row["net_monthly_eur"] - row["total_expenses_eur"]
        assert row["surplus_monthly_eur"] == pytest.approx(expected_surplus, abs=1), (
            f"Surplus {row['surplus_monthly_eur']} ≠ net {row['net_monthly_eur']} "
            f"- expenses {row['total_expenses_eur']}"
        )


# ── Salary growth ──────────────────────────────────────────────────────────────

class TestSalaryGrowth:
    def test_gross_grows_each_year(self):
        traj = calculate_trajectory(57500, "ES", "madrid", cagr=0.05, expenses_eur=3000)
        for i in range(1, len(traj)):
            assert traj[i]["gross_annual_local"] > traj[i - 1]["gross_annual_local"], (
                f"Gross should grow each year (CAGR 5%), failed at year {traj[i]['year']}"
            )

    def test_year1_gross_equals_input(self):
        traj = calculate_trajectory(57500, "ES", "madrid", expenses_eur=3000)
        assert traj[0]["gross_annual_local"] == 57500

    def test_zero_cagr_keeps_gross_flat(self):
        traj = calculate_trajectory(57500, "ES", "madrid", cagr=0.0, expenses_eur=3000)
        grosses = [row["gross_annual_local"] for row in traj]
        assert len(set(grosses)) == 1, "Zero CAGR should keep gross flat"

    def test_net_grows_with_salary(self):
        """Higher salary → higher net (within same tax regime)."""
        traj = calculate_trajectory(57500, "ES", "madrid", cagr=0.05, expenses_eur=3000)
        nets = [row["net_monthly_eur"] for row in traj]
        assert nets[-1] > nets[0], "Net should grow as salary grows at 5% CAGR over 10 years"


# ── Cumulative savings ────────────────────────────────────────────────────────

class TestCumulativeSavings:
    def test_cumulative_compounds(self):
        """cumulative[n] = cumulative[n-1] + surplus[n] * 12"""
        traj = calculate_trajectory(85000, "NL", "rotterdam", expenses_eur=3000, cagr=0.0)
        for i in range(1, len(traj)):
            prev = traj[i - 1]["cumulative_savings_eur"]
            monthly = traj[i]["surplus_monthly_eur"]
            expected = prev + monthly * 12
            assert traj[i]["cumulative_savings_eur"] == pytest.approx(expected, abs=2), (
                f"Year {traj[i]['year']}: cumulative should be {expected}, "
                f"got {traj[i]['cumulative_savings_eur']}"
            )

    def test_consistent_surplus_gives_linear_cumulative(self):
        """With 0 CAGR and 0 CoL inflation, surplus is constant so cumulative grows linearly."""
        traj = calculate_trajectory(85000, "NL", "rotterdam", cagr=0.0, expenses_eur=3500, col_inflation_rate=0.0)
        annual_savings = [traj[i]["cumulative_savings_eur"] - traj[i - 1]["cumulative_savings_eur"]
                          for i in range(1, len(traj))]
        # All annual deltas should be equal
        assert max(annual_savings) - min(annual_savings) <= 2, (
            "With 0 CAGR and 0% CoL inflation, annual cumulative delta should be constant"
        )

    def test_negative_surplus_reduces_cumulative(self):
        """High expenses → negative surplus → cumulative should decrease each year."""
        traj = calculate_trajectory(30000, "ES", "madrid", cagr=0.0, expenses_eur=9999)
        for i in range(1, len(traj)):
            assert traj[i]["cumulative_savings_eur"] < traj[i - 1]["cumulative_savings_eur"], (
                f"Year {traj[i]['year']}: cumulative should decrease with negative surplus"
            )


# ── Scheme expiry ─────────────────────────────────────────────────────────────

class TestSchemeExpiry:
    def test_30_ruling_expiry_increases_effective_rate(self):
        """After NL 30% ruling expires, effective tax rate must jump up."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            active_schemes=["nl_30_ruling"],
            scheme_expiry={"nl_30_ruling": 5},
            cagr=0.03,
            expenses_eur=4000,
        )
        rate_year5  = traj[4]["effective_rate"]  # still on ruling
        rate_year6  = traj[5]["effective_rate"]  # ruling just expired
        assert rate_year6 > rate_year5, (
            f"Effective rate should jump after 30% ruling expires: "
            f"year 5 = {rate_year5}%, year 6 = {rate_year6}%"
        )

    def test_30_ruling_expiry_reduces_net(self):
        """After ruling expires, net monthly must drop (same gross, more tax)."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            active_schemes=["nl_30_ruling"],
            scheme_expiry={"nl_30_ruling": 5},
            cagr=0.0,
            expenses_eur=4000,
        )
        net_year5 = traj[4]["net_monthly_eur"]
        net_year6 = traj[5]["net_monthly_eur"]
        assert net_year6 < net_year5, (
            f"Net should drop when 30% ruling expires: year 5 = €{net_year5}, year 6 = €{net_year6}"
        )

    def test_no_expiry_schemes_unchanged(self):
        """With no expiry set and ruling start year far enough to avoid rate change, rates are stable."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            active_schemes=["nl_30_ruling"],
            cagr=0.0,
            expenses_eur=4000,
            ruling_start_year=2030,  # 2030+9=2039, rate change at 2027 never triggers
        )
        # With flat CAGR and no expiry, effective rates should be constant
        rates = [row["effective_rate"] for row in traj]
        assert max(rates) - min(rates) < 1.0, (
            "With no expiry and 0 CAGR, effective rate should be stable"
        )


# ── CoL inflation ─────────────────────────────────────────────────────────────

class TestColInflation:
    """
    col_inflation_rate causes expenses to grow each year.
    With salary growing faster than expenses (CAGR > CoL inflation), surpluses
    should improve over time; with expenses growing faster, they should shrink.
    """

    def test_expenses_grow_with_inflation(self):
        """total_expenses_eur should increase each year with col_inflation_rate > 0."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=4000, cagr=0.0, col_inflation_rate=0.03,
        )
        for i in range(1, len(traj)):
            assert traj[i]["total_expenses_eur"] >= traj[i - 1]["total_expenses_eur"], (
                f"Expenses should grow each year with 3% CoL inflation"
            )

    def test_zero_inflation_keeps_expenses_flat(self):
        """col_inflation_rate=0 should hold expenses constant every year."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=4200, cagr=0.05, col_inflation_rate=0.0,
        )
        expenses = [row["total_expenses_eur"] for row in traj]
        assert len(set(expenses)) == 1, f"Expenses should stay flat with 0% inflation, got {expenses}"

    def test_year10_inflation_magnitude(self):
        """At 3% CoL inflation, year-10 expenses should be ≈ year-1 × (1.03^9) = 1.305×."""
        base = 4000
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=base, cagr=0.0, col_inflation_rate=0.03,
        )
        expected_yr10 = round(base * (1.03 ** 9))
        actual_yr10   = traj[9]["total_expenses_eur"]
        assert actual_yr10 == pytest.approx(expected_yr10, abs=5), (
            f"Year-10 expenses should be ~{expected_yr10}, got {actual_yr10}"
        )

    def test_inflation_reduces_cumulative_vs_flat(self):
        """10-year cumulative with CoL inflation should be lower than with flat expenses."""
        flat = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=4000, cagr=0.05, col_inflation_rate=0.0,
        )
        with_inf = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=4000, cagr=0.05, col_inflation_rate=0.03,
        )
        cum_flat   = flat[-1]["cumulative_savings_eur"]
        cum_inflat = with_inf[-1]["cumulative_savings_eur"]
        assert cum_inflat < cum_flat, (
            f"Cumulative with 3% CoL inflation ({cum_inflat:,}) should be "
            f"less than flat ({cum_flat:,})"
        )

    def test_year1_expenses_match_input_regardless_of_inflation(self):
        """Year 1 expenses should equal the input expenses_eur (inflation applied from year 2)."""
        traj = calculate_trajectory(
            85000, "NL", "rotterdam",
            expenses_eur=4200, cagr=0.05, col_inflation_rate=0.05,
        )
        assert traj[0]["total_expenses_eur"] == 4200, (
            f"Year 1 expenses should equal input 4200, got {traj[0]['total_expenses_eur']}"
        )
