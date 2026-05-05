"""
Tests for engine/tax.py — calculate_net() and _lookup_net()

Anchors from CONTEXT.md (validated real-world net figures):
  ES  €57,500 gross  → €3,450/mo net
  NL  €85,000 gross + 30% ruling → €5,095/mo net

Run with:  cd C:\\Personal\\salary-compass && python -m pytest tests/ -v
"""

import pytest
from engine.tax import calculate_net, find_target_gross


# ── Validated anchor points ────────────────────────────────────────────────────


class TestAnchorPoints:
    """
    Hard anchors from real-world validated payslips (see CONTEXT.md).
    These are the most important tests — if they break, tax calculations are wrong.
    """

    def test_spain_anchor_57500(self):
        """€57,500 gross → €3,450/mo net (IRPF + SS, mínimo personal, gastos deducibles)."""
        result = calculate_net(57500, "ES")
        assert result["net_monthly_eur"] == pytest.approx(3450, abs=50), (
            f"ES €57,500 gross should give ~€3,450/mo net, got €{result['net_monthly_eur']}"
        )

    def test_netherlands_30_ruling_anchor_85000(self):
        """€85,000 gross + 30% ruling → ~€5,620/mo net (2026 brackets + full credits)."""
        result = calculate_net(85000, "NL", active_schemes=["nl_30_ruling"])
        assert result["net_monthly_eur"] == pytest.approx(5620, abs=75), (
            f"NL €85,000 + 30% ruling should give ~€5,620/mo net, got €{result['net_monthly_eur']}"
        )

    def test_30_ruling_improves_net_vs_no_ruling(self):
        """30% ruling must give meaningfully more net than without."""
        with_ruling = calculate_net(85000, "NL", active_schemes=["nl_30_ruling"])
        without_ruling = calculate_net(85000, "NL")
        diff = with_ruling["net_monthly_eur"] - without_ruling["net_monthly_eur"]
        assert diff > 300, (
            f"30% ruling should add >€300/mo net at €85k gross, got +€{diff}"
        )


# ── Return structure ───────────────────────────────────────────────────────────


class TestReturnStructure:
    def test_required_keys(self):
        result = calculate_net(60000, "ES")
        for key in (
            "gross_annual",
            "net_monthly_local",
            "net_monthly_eur",
            "effective_rate",
            "currency",
            "eur_rate",
        ):
            assert key in result, f"Missing key: {key}"

    def test_currency_matches_country(self):
        assert calculate_net(60000, "ES")["currency"] == "EUR"
        assert calculate_net(60000, "NL")["currency"] == "EUR"
        assert calculate_net(120000, "CH")["currency"] == "CHF"
        assert calculate_net(700000, "NOR")["currency"] == "NOK"
        assert calculate_net(60000, "UK")["currency"] == "GBP"

    def test_eur_rate_is_one_for_eur_countries(self):
        for code in ("ES", "NL", "DE"):
            assert calculate_net(60000, code)["eur_rate"] == pytest.approx(
                1.0, abs=0.01
            )


# ── Sanity checks across all countries ────────────────────────────────────────


class TestCountrySanity:
    """Net must be positive, < gross, and effective rate in a plausible range."""

    @pytest.mark.parametrize(
        "gross,country,lo_pct,hi_pct",
        [
            (57500, "ES", 20, 40),
            (80000, "NL", 25, 45),
            (85000, "NL", 25, 45),
            (80000, "DE", 30, 50),
            (120000, "CH", 20, 40),
            (700000, "NOR", 20, 45),
            (60000, "UK", 20, 40),
        ],
    )
    def test_effective_rate_in_range(self, gross, country, lo_pct, hi_pct):
        result = calculate_net(gross, country)
        rate = result["effective_rate"] * 100
        assert lo_pct <= rate <= hi_pct, (
            f"{country} {gross}: effective rate {rate:.1f}% not in [{lo_pct}%, {hi_pct}%]"
        )

    @pytest.mark.parametrize(
        "gross,country",
        [
            (57500, "ES"),
            (85000, "NL"),
            (80000, "DE"),
            (120000, "CH"),
            (700000, "NOR"),
            (60000, "UK"),
        ],
    )
    def test_net_monthly_positive(self, gross, country):
        result = calculate_net(gross, country)
        assert result["net_monthly_eur"] > 0, (
            f"{country} {gross}: net should be positive"
        )

    @pytest.mark.parametrize(
        "gross,country",
        [
            (57500, "ES"),
            (85000, "NL"),
            (80000, "DE"),
            (120000, "CH"),
            (700000, "NOR"),
            (60000, "UK"),
        ],
    )
    def test_net_less_than_gross(self, gross, country):
        result = calculate_net(gross, country)
        assert result["net_monthly_eur"] * 12 < result["gross_annual"], (
            f"{country} {gross}: annual net should be less than gross"
        )


# ── Higher salary → higher net ────────────────────────────────────────────────


class TestMonotonicity:
    """More gross should always mean more net (monotonic)."""

    @pytest.mark.parametrize("country", ["ES", "NL", "DE", "UK"])
    def test_higher_gross_gives_higher_net(self, country):
        low = calculate_net(50000, country)["net_monthly_eur"]
        mid = calculate_net(75000, country)["net_monthly_eur"]
        high = calculate_net(120000, country)["net_monthly_eur"]
        assert low < mid < high, (
            f"{country}: net should increase with gross, got {low} / {mid} / {high}"
        )

    @pytest.mark.parametrize("country", ["ES", "NL", "DE", "UK"])
    def test_higher_gross_gives_higher_effective_rate(self, country):
        """Progressive tax: effective rate should increase with gross."""
        low = calculate_net(50000, country)["effective_rate"]
        high = calculate_net(120000, country)["effective_rate"]
        assert high > low, (
            f"{country}: effective rate should be higher at €120k than €50k"
        )


# ── Lookup interpolation ───────────────────────────────────────────────────────


class TestLookupInterpolation:
    """Test that lookup-method countries interpolate smoothly (no step-function jumps)."""

    @pytest.mark.parametrize("country", ["ES", "CH", "GE", "NOR"])
    def test_interpolation_is_smooth(self, country):
        """Net should not jump by more than €350 between consecutive salary steps."""
        grosses = list(range(50000, 130001, 5000))
        if country == "NOR":
            grosses = list(range(400000, 900001, 50000))
        nets = [calculate_net(g, country)["net_monthly_eur"] for g in grosses]
        for i in range(1, len(nets)):
            jump = abs(nets[i] - nets[i - 1])
            assert jump < 350, (
                f"{country}: net jumped €{jump:.0f} between "
                f"{grosses[i - 1]:,} and {grosses[i]:,} — interpolation too coarse"
            )


# ── Geneva (GE) vs Zurich (CH) tax comparison ─────────────────────────────────


class TestGenevaTax:
    """
    Geneva (Canton GE) uses different cantonal rates from Zurich (Canton ZH).
    Single/cohabiting earner. Geneva should consistently give LESS net than Zurich
    at equivalent gross (higher cantonal + communal rates, no income splitting).
    """

    @pytest.mark.parametrize("gross", [80000, 100000, 120000, 130000])
    def test_geneva_less_net_than_zurich(self, gross):
        """Geneva single earner should take home less than Zurich at same gross."""
        ge_net = calculate_net(gross, "GE")["net_monthly_local"]
        ch_net = calculate_net(gross, "CH")["net_monthly_local"]
        assert ge_net < ch_net, (
            f"Geneva should give less net than Zurich at CHF {gross:,}: "
            f"GE={ge_net}, CH={ch_net}"
        )

    @pytest.mark.parametrize(
        "gross,expected,tol",
        [
            (120000, 7435, 75),
            (130000, 8010, 75),
            (80000, 5116, 75),
        ],
    )
    def test_ge_lookup_anchor(self, gross, expected, tol):
        """Key Geneva anchor points from verified LIPP tariff calculation."""
        result = calculate_net(gross, "GE")
        assert result["net_monthly_local"] == pytest.approx(expected, abs=tol), (
            f"GE CHF {gross:,}: expected ~{expected}/mo, got {result['net_monthly_local']}"
        )

    def test_geneva_currency_is_chf(self):
        """GE tax engine must return CHF (same as CH)."""
        result = calculate_net(120000, "GE")
        assert result["currency"] == "CHF"
        assert result["eur_rate"] == pytest.approx(1.091, abs=0.01)

    def test_geneva_net_positive_and_below_gross(self):
        """Sanity: net annual must be positive and below gross."""
        result = calculate_net(120000, "GE")
        assert result["net_monthly_local"] > 0
        assert result["net_monthly_local"] * 12 < 120000

    def test_geneva_higher_gross_gives_higher_net(self):
        """Monotonicity: more gross → more net in Geneva."""
        nets = [
            calculate_net(g, "GE")["net_monthly_local"]
            for g in [80000, 100000, 120000, 150000, 180000]
        ]
        for i in range(1, len(nets)):
            assert nets[i] > nets[i - 1], f"GE net not monotone at step {i}"


# ── Beckham Law (Ley de Impatriados) ─────────────────────────────────────────


class TestBeckhamLaw:
    """
    Beckham Law applies a flat 24% IRPF on full gross for new ES residents.
    SS contributions still apply (capped at EUR ~57,606).
    Only beneficial above ~€72k gross (below that, progressive IRPF < 24%).
    """

    def test_beckham_gives_higher_net_at_90k(self):
        """At €90k gross, Beckham (24% flat) beats standard progressive IRPF."""
        standard = calculate_net(90000, "ES")
        beckham = calculate_net(90000, "ES", active_schemes=["es_beckham_law"])
        assert beckham["net_monthly_eur"] > standard["net_monthly_eur"], (
            f"Beckham at €90k should beat standard: "
            f"Beckham €{beckham['net_monthly_eur']}/mo vs standard €{standard['net_monthly_eur']}/mo"
        )

    def test_beckham_material_at_120k(self):
        """At €120k gross, Beckham should save >€600/mo vs standard progressive rates."""
        standard = calculate_net(120000, "ES")
        beckham = calculate_net(120000, "ES", active_schemes=["es_beckham_law"])
        saving = beckham["net_monthly_eur"] - standard["net_monthly_eur"]
        assert saving > 600, f"Beckham should save >€600/mo at €120k, got +€{saving}/mo"

    def test_beckham_worse_at_low_income(self):
        """Below break-even (~€72k), standard progressive IRPF is lower than flat 24%."""
        standard = calculate_net(57500, "ES")
        beckham = calculate_net(57500, "ES", active_schemes=["es_beckham_law"])
        assert standard["net_monthly_eur"] >= beckham["net_monthly_eur"], (
            f"Standard should beat Beckham at €57.5k: "
            f"standard €{standard['net_monthly_eur']}/mo vs Beckham €{beckham['net_monthly_eur']}/mo"
        )

    def test_beckham_effective_rate_is_24pct_plus_ss_ratio(self):
        """At high income (SS capped), effective rate approaches 24% + SS_cap/gross."""
        result = calculate_net(150000, "ES", active_schemes=["es_beckham_law"])
        # At €150k: SS capped at ~57606 * 6.37% ≈ 3670/yr. IRPF = 150000 * 24% = 36000.
        # Net = 150000 - 36000 - 3670 = 110330 / 12 = 9194/mo
        assert result["net_monthly_eur"] == pytest.approx(9194, abs=100), (
            f"Beckham €150k: expected ~€9,194/mo, got €{result['net_monthly_eur']}"
        )

    def test_beckham_scheme_in_es_yaml(self):
        """ES.yaml must contain the Beckham Law scheme."""
        from engine.tax import get_schemes

        schemes = get_schemes("ES")
        scheme_ids = [s["id"] for s in schemes]
        assert "es_beckham_law" in scheme_ids, (
            f"ES must have es_beckham_law scheme, found: {scheme_ids}"
        )

    def test_beckham_returns_correct_structure(self):
        """flat_rate_override path must return same keys as standard calculate_net."""
        result = calculate_net(90000, "ES", active_schemes=["es_beckham_law"])
        for key in (
            "gross_annual",
            "net_monthly_eur",
            "effective_rate",
            "currency",
            "eur_rate",
        ):
            assert key in result, f"Beckham result missing key: {key}"


# ── NL 2026: heffingskortingen (tax credits) ─────────────────────────────────


class TestNLTaxCredits2026:
    """
    Verify that arbeidskorting and algemene heffingskorting are correctly applied
    in the 2026 three-bracket NL tax model.

    Reference values computed from official belastingdienst.nl 2026 tables.
    """

    def test_nl_no_ruling_85k_net(self):
        """€85k gross, no ruling → ~€4,517/mo net (after ZVW €159/mo in social)."""
        result = calculate_net(85000, "NL")
        # Without credits the old model gave ~€4,140/mo — credits add ~€377/mo
        assert result["net_monthly_eur"] == pytest.approx(4517, abs=30), (
            f"NL €85k no ruling: expected ~€4,517/mo, got €{result['net_monthly_eur']}"
        )

    def test_nl_no_ruling_100k_net(self):
        """€100k gross, no ruling → ~€5,067/mo net (after ZVW)."""
        result = calculate_net(100000, "NL")
        assert result["net_monthly_eur"] == pytest.approx(5067, abs=30), (
            f"NL €100k no ruling: expected ~€5,067/mo, got €{result['net_monthly_eur']}"
        )

    def test_30_ruling_adds_over_1000_at_85k(self):
        """With credits, 30% ruling benefit at €85k should be >€1,000/mo."""
        with_ruling = calculate_net(85000, "NL", active_schemes=["nl_30_ruling"])
        without_ruling = calculate_net(85000, "NL")
        diff = with_ruling["net_monthly_eur"] - without_ruling["net_monthly_eur"]
        assert diff > 1000, (
            f"30% ruling at €85k should add >€1,000/mo with credits, got +€{diff:.0f}"
        )

    def test_ahk_zero_above_78426(self):
        """AHK phases to zero at the bracket-2/3 boundary (€78,426)."""
        from engine.tax import _calc_phase_out_credit

        credit_cfg = {
            "max_credit": 3115,
            "phase_out_start": 29736,
            "phase_out_end": 78426,
            "phase_out_rate": 0.06398,
        }
        assert _calc_phase_out_credit(78426, credit_cfg) == pytest.approx(0, abs=5)
        assert _calc_phase_out_credit(100000, credit_cfg) == 0.0

    def test_ahk_max_below_phase_out_start(self):
        """AHK is at maximum (€3,115) for incomes at or below €29,736."""
        from engine.tax import _calc_phase_out_credit

        credit_cfg = {
            "max_credit": 3115,
            "phase_out_start": 29736,
            "phase_out_end": 78426,
            "phase_out_rate": 0.06398,
        }
        assert _calc_phase_out_credit(20000, credit_cfg) == pytest.approx(3115, abs=1)
        assert _calc_phase_out_credit(0, credit_cfg) == pytest.approx(3115, abs=1)

    def test_arbeidskorting_peak(self):
        """Arbeidskorting is maximised at ~€5,685 around €45,592 income."""
        from engine.tax import _calc_piecewise_credit

        credit_cfg = {
            "bands": [
                {"from": 0, "to": 11965, "base": 0, "rate": 0.08324},
                {"from": 11965, "to": 25845, "base": 996, "rate": 0.31009},
                {"from": 25845, "to": 45592, "base": 5300, "rate": 0.01950},
                {"from": 45592, "to": 132920, "base": 5685, "rate": -0.06510},
                {"from": 132920, "to": None, "base": 0, "rate": 0.0},
            ]
        }
        assert _calc_piecewise_credit(45592, credit_cfg) == pytest.approx(5685, abs=5)

    def test_arbeidskorting_zero_above_132920(self):
        """Arbeidskorting phases to zero above €132,920."""
        from engine.tax import _calc_piecewise_credit

        credit_cfg = {
            "bands": [
                {"from": 0, "to": 11965, "base": 0, "rate": 0.08324},
                {"from": 11965, "to": 25845, "base": 996, "rate": 0.31009},
                {"from": 25845, "to": 45592, "base": 5300, "rate": 0.01950},
                {"from": 45592, "to": 132920, "base": 5685, "rate": -0.06510},
                {"from": 132920, "to": None, "base": 0, "rate": 0.0},
            ]
        }
        assert _calc_piecewise_credit(150000, credit_cfg) == 0.0
        assert _calc_piecewise_credit(132920, credit_cfg) == pytest.approx(0, abs=5)

    def test_credits_increase_net_vs_old_model(self):
        """New model must give materially more net than old 37.07% / 49.5% brackets-only."""
        # Old model: 85k × 37.07% = 31,510 tax + 1,860 ZVW → net = 51,630 / 12 = 4,303/mo
        new_net = calculate_net(85000, "NL")["net_monthly_eur"]
        old_net_approx = (85000 - 85000 * 0.3707 - 1860) / 12  # old broken model
        assert new_net > old_net_approx + 200, (
            f"New model should be >€200/mo more than old brackets-only: "
            f"new={new_net:.0f}, old≈{old_net_approx:.0f}"
        )


# -- Reverse Salary Calculator -----------------------------------------------


class TestFindTargetGross:
    def test_inverse_of_calculate_net_spain(self):
        from engine.tax import calculate_net, find_target_gross

        target_net = calculate_net(80000, "ES")["net_monthly_eur"]
        result_gross = find_target_gross(target_net, "ES")
        check_net = calculate_net(result_gross, "ES")["net_monthly_eur"]
        assert abs(check_net - target_net) <= 10

    def test_inverse_of_calculate_net_nl(self):
        from engine.tax import calculate_net, find_target_gross

        target_net = calculate_net(100000, "NL")["net_monthly_eur"]
        result_gross = find_target_gross(target_net, "NL")
        check_net = calculate_net(result_gross, "NL")["net_monthly_eur"]
        assert abs(check_net - target_net) <= 10

    def test_inverse_with_30_ruling(self):
        from engine.tax import calculate_net, find_target_gross

        target_net = calculate_net(90000, "NL", ["nl_30_ruling"])["net_monthly_eur"]
        result_gross = find_target_gross(
            target_net, "NL", active_schemes=["nl_30_ruling"]
        )
        check_net = calculate_net(result_gross, "NL", ["nl_30_ruling"])[
            "net_monthly_eur"
        ]
        assert abs(check_net - target_net) <= 10

    def test_monotonic(self):
        from engine.tax import find_target_gross

        g1 = find_target_gross(3000, "ES")
        g2 = find_target_gross(4000, "ES")
        g3 = find_target_gross(6000, "ES")
        assert g1 < g2 < g3

    def test_returns_numeric(self):
        from engine.tax import find_target_gross

        r = find_target_gross(3500, "DE")
        assert isinstance(r, (int, float)) and r > 0

    def test_inverse_for_lookup_country(self):
        from engine.tax import calculate_net, find_target_gross

        target_net = calculate_net(120000, "CH")["net_monthly_eur"]
        result_gross = find_target_gross(target_net, "CH")
        check_net = calculate_net(result_gross, "CH")["net_monthly_eur"]
        assert abs(check_net - target_net) <= 20


# ── NL 30% → 27% rate change (Jan 2027) ──────────────────────────────────────


class TestNL30to27RulingRateChange:
    """
    Verify that the Jan-2027 rate reduction (30%→27%) is correctly modelled
    in calculate_net (via scheme_overrides) and calculate_trajectory.
    """

    def test_scheme_overrides_reduces_net(self):
        """Overriding multiplier to 0.73 (27% ruling) reduces net vs 0.70 (30%)."""
        net_30 = calculate_net(85000, "NL", ["nl_30_ruling"])["net_monthly_eur"]
        net_27 = calculate_net(
            85000,
            "NL",
            ["nl_30_ruling"],
            scheme_overrides={"nl_30_ruling": {"multiplier": 0.73}},
        )["net_monthly_eur"]
        assert net_27 < net_30, "27% ruling should give lower net than 30%"
        drop = net_30 - net_27
        assert 100 < drop < 400, f"Expected €100–400/mo drop at €85k, got €{drop:.0f}"

    def test_scheme_overrides_backwards_compatible(self):
        """Calling calculate_net without scheme_overrides gives same result as before."""
        net_a = calculate_net(85000, "NL", ["nl_30_ruling"])["net_monthly_eur"]
        net_b = calculate_net(85000, "NL", ["nl_30_ruling"], scheme_overrides=None)[
            "net_monthly_eur"
        ]
        assert net_a == net_b

    def test_27pct_drop_ballpark_at_85k(self):
        """At €85k gross, 30%→27% drop should be roughly €150–250/mo."""
        net_30 = calculate_net(85000, "NL", ["nl_30_ruling"])["net_monthly_eur"]
        net_27 = calculate_net(
            85000,
            "NL",
            ["nl_30_ruling"],
            scheme_overrides={"nl_30_ruling": {"multiplier": 0.73}},
        )["net_monthly_eur"]
        drop = net_30 - net_27
        assert 100 <= drop <= 350, (
            f"Drop should be ~€150–250/mo at €85k, got €{drop:.0f}"
        )

    def test_trajectory_emits_rate_change_event(self):
        """Trajectory emits ⚡ event in the first year the 2027 rate change hits."""
        from engine.trajectory import calculate_trajectory

        # ruling_start_year=2026 → Year 2 = 2027 triggers rate change
        traj = calculate_trajectory(
            85000,
            "NL",
            "amsterdam",
            active_schemes=["nl_30_ruling"],
            cagr=0.0,
            expenses_eur=3000,
            ruling_start_year=2026,
        )
        year2_events = traj[1].get("events", [])
        assert any("⚡" in e for e in year2_events), (
            f"Year 2 should have ⚡ rate-change event, got: {year2_events}"
        )
        # Year 1 should NOT have the event
        year1_events = traj[0].get("events", [])
        assert not any("⚡" in e for e in year1_events), (
            f"Year 1 should not have rate-change event, got: {year1_events}"
        )

    def test_trajectory_rate_change_drops_net(self):
        """Net should be lower in Year 2 vs Year 1 due to 30%→27% switch."""
        from engine.trajectory import calculate_trajectory

        traj = calculate_trajectory(
            85000,
            "NL",
            "amsterdam",
            active_schemes=["nl_30_ruling"],
            cagr=0.0,
            expenses_eur=2000,
            ruling_start_year=2026,
        )
        assert traj[1]["net_monthly_eur"] < traj[0]["net_monthly_eur"], (
            "Year 2 net should be lower than Year 1 (rate change from 30% to 27%)"
        )

    def test_trajectory_start_2027_applies_27pct_from_year1(self):
        """If ruling starts in 2027 or later, 27% ruling applies from Year 1."""
        from engine.trajectory import calculate_trajectory

        traj_2026 = calculate_trajectory(
            85000,
            "NL",
            "amsterdam",
            active_schemes=["nl_30_ruling"],
            cagr=0.0,
            expenses_eur=2000,
            ruling_start_year=2026,
        )
        traj_2027 = calculate_trajectory(
            85000,
            "NL",
            "amsterdam",
            active_schemes=["nl_30_ruling"],
            cagr=0.0,
            expenses_eur=2000,
            ruling_start_year=2027,
        )
        # Year 1 of 2027-start should equal Year 2 of 2026-start (both at 27%)
        assert traj_2027[0]["net_monthly_eur"] == pytest.approx(
            traj_2026[1]["net_monthly_eur"], abs=10
        ), "ruling_start_year=2027 Year 1 should match ruling_start_year=2026 Year 2"

    def test_expiry_before_2027_no_rate_change_event(self):
        """If ruling expires before 2027, the rate-change event should never fire."""
        from engine.trajectory import calculate_trajectory

        traj = calculate_trajectory(
            85000,
            "NL",
            "amsterdam",
            active_schemes=["nl_30_ruling"],
            scheme_expiry={"nl_30_ruling": 1},  # expires after Year 1
            cagr=0.0,
            expenses_eur=2000,
            ruling_start_year=2026,
        )
        all_events = [e for yr in traj for e in yr.get("events", [])]
        assert not any("⚡" in e for e in all_events), (
            "No rate-change event should fire when ruling expires before 2027"
        )

    def test_find_target_gross_with_scheme_overrides(self):
        """find_target_gross supports scheme_overrides for 27%-ruling cliff calc."""
        net_30 = calculate_net(85000, "NL", ["nl_30_ruling"])["net_monthly_eur"]
        gross_needed = find_target_gross(
            net_30,
            "NL",
            active_schemes=["nl_30_ruling"],
            scheme_overrides={"nl_30_ruling": {"multiplier": 0.73}},
        )
        # With 27% ruling, need higher gross to match 30% net
        assert gross_needed > 85000, (
            "Need higher gross under 27% ruling to match 30% net"
        )
        # Verify the gross actually achieves the target
        check = calculate_net(
            gross_needed,
            "NL",
            ["nl_30_ruling"],
            scheme_overrides={"nl_30_ruling": {"multiplier": 0.73}},
        )
        assert abs(check["net_monthly_eur"] - net_30) <= 10
