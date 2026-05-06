"""
Excel export for SalaryCompass.
Builds a styled multi-sheet workbook in memory and returns raw bytes.

Usage:
    from output.excel import generate_excel_report
    raw = generate_excel_report(city_inputs, results_matrix, scenarios_def,
                                city_names, home_city_slug, scen_names,
                                col_inflation_rate=0.02)
    st.download_button("⬇️ Download Excel", data=raw, file_name="salary_compass.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import xlsxwriter

# ── colour palette (matches GIC design system) ────────────────────────────────
_C_HEADER_BG = "#1A1F2E"
_C_HEADER_FG = "#FFFFFF"
_C_SUBHEAD_BG = "#2C3E50"
_C_SUBHEAD_FG = "#FFFFFF"
_C_ALT_ROW = "#F4F6F9"
_C_SURPLUS_POS = "#27AE60"
_C_SURPLUS_NEG = "#E74C3C"
_C_AMBER = "#F39C12"
_C_AMBER_BG = "#FEF9E7"


def generate_excel_report(
    city_inputs: dict[str, dict],
    results_matrix: dict[str, dict[str, dict]],
    scenarios_def: list[dict],
    city_names: dict[str, str],
    home_city_slug: str,
    scen_names: list[str],
    col_inflation_rate: float = 0.02,
) -> bytes:
    """Generate a complete Excel workbook and return as bytes."""
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_numbers": False})

    # ── shared formats ─────────────────────────────────────────────────────────
    def _fmt(**kwargs) -> Any:
        return wb.add_format(kwargs)

    F = {
        "title": _fmt(
            bold=True,
            font_size=14,
            font_color=_C_HEADER_FG,
            bg_color=_C_HEADER_BG,
            border=0,
        ),
        "subtitle": _fmt(
            bold=True,
            font_size=10,
            font_color=_C_SUBHEAD_FG,
            bg_color=_C_SUBHEAD_BG,
            border=0,
        ),
        "header": _fmt(
            bold=True,
            font_size=9,
            font_color=_C_HEADER_FG,
            bg_color=_C_SUBHEAD_BG,
            align="center",
            border=0,
        ),
        "label": _fmt(bold=True, font_size=9),
        "normal": _fmt(font_size=9),
        "alt": _fmt(font_size=9, bg_color=_C_ALT_ROW),
        "money": _fmt(font_size=9, num_format="€#,##0"),
        "money_alt": _fmt(font_size=9, num_format="€#,##0", bg_color=_C_ALT_ROW),
        "money_bold": _fmt(font_size=9, num_format="€#,##0", bold=True),
        "surplus_pos": _fmt(font_size=9, num_format="€#,##0", bold=True, font_color=_C_SURPLUS_POS),
        "surplus_neg": _fmt(font_size=9, num_format="€#,##0", bold=True, font_color=_C_SURPLUS_NEG),
        "pct": _fmt(font_size=9, num_format="0.0%"),
        "amber": _fmt(font_size=9, bold=True, font_color=_C_AMBER, bg_color=_C_AMBER_BG),
        "amber_money": _fmt(
            font_size=9,
            bold=True,
            num_format="€#,##0",
            font_color=_C_AMBER,
            bg_color=_C_AMBER_BG,
        ),
        "caption": _fmt(font_size=8, italic=True, font_color="#888888"),
    }

    slugs = list(city_inputs.keys())

    _write_summary(wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs)
    _write_budget(wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs)
    _write_trajectory(
        wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs
    )
    _write_negotiation(
        wb,
        F,
        city_inputs,
        results_matrix,
        scenarios_def,
        city_names,
        scen_names,
        slugs,
        home_city_slug,
    )
    _write_assumptions(
        wb,
        F,
        city_inputs,
        city_names,
        scen_names,
        scenarios_def,
        col_inflation_rate,
        home_city_slug,
    )

    wb.close()
    output.seek(0)
    return output.read()


# ── Sheet 1: Summary ──────────────────────────────────────────────────────────


def _write_summary(
    wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs
):
    ws = wb.add_worksheet("1. Summary")
    ws.set_zoom(90)
    ws.freeze_panes(3, 1)
    ws.set_column(0, 0, 22)

    # Title row
    num_data_cols = len(slugs) * 3
    ws.merge_range(0, 0, 0, num_data_cols, f"SalaryCompass — Summary  [{date.today()}]", F["title"])
    ws.set_row(0, 22)

    # City headers (merged across 3 sub-columns each)
    ws.write(1, 0, "Scenario", F["header"])
    for i, slug in enumerate(slugs):
        col = 1 + i * 3
        ws.merge_range(1, col, 1, col + 2, city_names[slug], F["header"])
        ws.set_column(col, col, 15)
        ws.set_column(col + 1, col + 1, 15)
        ws.set_column(col + 2, col + 2, 15)

    # Sub-column headers
    ws.write(2, 0, "", F["header"])
    for i in range(len(slugs)):
        col = 1 + i * 3
        ws.write(2, col, "Net/mo", F["header"])
        ws.write(2, col + 1, "Expenses/mo", F["header"])
        ws.write(2, col + 2, "Surplus/mo", F["header"])
    ws.set_row(2, 14)

    # Data rows
    for row_i, scen in enumerate(scenarios_def):
        row = 3 + row_i
        alt = row_i % 2 == 1
        ws.write(row, 0, scen["name"], F["alt"] if alt else F["normal"])
        for j, slug in enumerate(slugs):
            col = 1 + j * 3
            r = results_matrix[slug][scen["name"]]
            net = r["net"]["net_monthly_eur"] + city_inputs[slug].get("perks_monthly_eur", 0)
            exp = r["budget"]["total_eur"]
            sur = net - exp
            ws.write_number(row, col, net, F["money_alt"] if alt else F["money"])
            ws.write_number(row, col + 1, exp, F["money_alt"] if alt else F["money"])
            ws.write_number(row, col + 2, sur, F["surplus_pos"] if sur >= 0 else F["surplus_neg"])

    # Perks note
    has_perks = any(ci.get("perks_monthly_eur", 0) > 0 for ci in city_inputs.values())
    note_row = 3 + len(scenarios_def) + 1
    if has_perks:
        ws.merge_range(
            note_row,
            0,
            note_row,
            num_data_cols,
            "* Net includes tax-free perks (travel allowance + meal vouchers)",
            F["caption"],
        )
    ws.merge_range(
        note_row + 1,
        0,
        note_row + 1,
        num_data_cols,
        "Directional estimates only — not financial or tax advice.",
        F["caption"],
    )


# ── Sheet 2: Budget Breakdown ─────────────────────────────────────────────────

_CAT_LABELS = {
    "rent_2bed": "🏠 Rent (2-bed)",
    "utilities": "⚡ Utilities",
    "health_extra": "🏥 Health",
    "groceries_2pax": "🛒 Groceries",
    "transport_2pax": "🚌 Transport",
    "eating_out": "🍽️ Eating out",
    "leisure": "🎮 Leisure",
    "misc": "🎁 Misc",
    "travel": "✈️ Travel (portable)",
    "personal": "👤 Personal (portable)",
}


def _write_budget(wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs):
    ws = wb.add_worksheet("2. Budget Breakdown")
    ws.set_zoom(90)
    ws.set_column(0, 0, 26)
    for c in range(1, len(slugs) + 2):
        ws.set_column(c, c, 15)
    ws.freeze_panes(2, 1)

    ws.merge_range(
        0,
        0,
        0,
        len(slugs),
        f"SalaryCompass — Budget Breakdown  [{date.today()}]",
        F["title"],
    )
    ws.set_row(0, 22)

    # Per-scenario blocks
    current_row = 1
    for scen in scenarios_def:
        # Scenario header
        ws.merge_range(current_row, 0, current_row, len(slugs), scen["name"], F["subtitle"])
        ws.set_row(current_row, 16)
        current_row += 1

        # City column headers
        ws.write(current_row, 0, "Category", F["header"])
        for j, slug in enumerate(slugs):
            ws.write(current_row, j + 1, city_names[slug], F["header"])
        current_row += 1

        # Category rows
        cats = list(_CAT_LABELS.keys())
        for row_i, cat in enumerate(cats):
            alt = row_i % 2 == 1
            ws.write(current_row, 0, _CAT_LABELS[cat], F["alt"] if alt else F["normal"])
            for j, slug in enumerate(slugs):
                items = results_matrix[slug][scen["name"]]["budget"].get("items", {})
                item = items.get(cat, {})
                val = item.get("value_eur", 0) if isinstance(item, dict) else 0
                ws.write_number(current_row, j + 1, val, F["money_alt"] if alt else F["money"])
            current_row += 1

        # Total row
        ws.write(current_row, 0, "TOTAL", F["label"])
        for j, slug in enumerate(slugs):
            total = results_matrix[slug][scen["name"]]["budget"]["total_eur"]
            ws.write_number(current_row, j + 1, total, F["money_bold"])
        current_row += 2


# ── Sheet 3: 10-Year Trajectory ───────────────────────────────────────────────


def _write_trajectory(
    wb, F, city_inputs, results_matrix, scenarios_def, city_names, scen_names, slugs
):
    ws = wb.add_worksheet("3. Trajectory")
    ws.set_zoom(85)
    ws.freeze_panes(2, 0)
    ws.set_column(0, 0, 5)  # Year
    ws.set_column(1, 1, 14)  # Gross local
    ws.set_column(2, 2, 13)  # Net EUR
    ws.set_column(3, 3, 15)  # Expenses EUR
    ws.set_column(4, 4, 13)  # Surplus EUR
    ws.set_column(5, 5, 16)  # Cumulative EUR
    ws.set_column(6, 6, 8)  # Eff rate
    ws.set_column(7, 7, 40)  # Events

    ws.merge_range(0, 0, 0, 7, f"SalaryCompass — 10-Year Trajectory  [{date.today()}]", F["title"])
    ws.set_row(0, 22)

    COL_HEADS = [
        "Yr",
        "Gross (local)",
        "Net €/mo",
        "Expenses €/mo",
        "Surplus €/mo",
        "Cumulative €",
        "Eff. rate",
        "Events",
    ]

    current_row = 1
    for slug in slugs:
        for scen in scenarios_def:
            # Block header
            ws.merge_range(
                current_row,
                0,
                current_row,
                7,
                f"{city_names[slug]}  ·  {scen['name']}",
                F["subtitle"],
            )
            ws.set_row(current_row, 15)
            current_row += 1

            # Column headers
            for c, h in enumerate(COL_HEADS):
                ws.write(current_row, c, h, F["header"])
            current_row += 1

            traj = results_matrix[slug][scen["name"]]["trajectory"]
            for row_i, yr in enumerate(traj):
                alt = row_i % 2 == 1
                events = yr.get("events", [])
                has_event = len(events) > 0
                mf = F["amber"] if has_event else (F["alt"] if alt else F["normal"])
                mm = F["amber_money"] if has_event else (F["money_alt"] if alt else F["money"])
                sur = yr["surplus_monthly_eur"]
                sur_fmt = (
                    F["amber_money"]
                    if has_event
                    else (F["surplus_pos"] if sur >= 0 else F["surplus_neg"])
                )

                ws.write_number(current_row, 0, yr["year"], mf)
                ws.write_number(current_row, 1, yr["gross_annual_local"], mm)
                ws.write_number(current_row, 2, yr["net_monthly_eur"], mm)
                ws.write_number(current_row, 3, yr["total_expenses_eur"], mm)
                ws.write_number(current_row, 4, sur, sur_fmt)
                ws.write_number(current_row, 5, yr["cumulative_savings_eur"], mm)
                ws.write(
                    current_row,
                    6,
                    f"{yr['effective_rate']:.1f}%",
                    F["alt"] if alt else F["normal"],
                )
                ws.write(current_row, 7, " | ".join(events) if events else "", mf)
                current_row += 1

            current_row += 1  # blank spacer row


# ── Sheet 4: Negotiation Targets ─────────────────────────────────────────────


def _write_negotiation(
    wb,
    F,
    city_inputs,
    results_matrix,
    scenarios_def,
    city_names,
    scen_names,
    slugs,
    home_city_slug,
):
    from engine.tax import _find_scheme, calculate_net, find_target_gross, load_country

    ws = wb.add_worksheet("4. Negotiation Targets")
    ws.set_zoom(90)
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 20)
    ws.set_column(2, 5, 16)

    ws.merge_range(0, 0, 0, 5, f"SalaryCompass — Negotiation Targets  [{date.today()}]", F["title"])
    ws.set_row(0, 22)

    non_home = [s for s in slugs if s != home_city_slug]
    if not non_home:
        non_home = slugs

    # Reference: home city comfortable net + surplus
    if home_city_slug in city_inputs and home_city_slug in results_matrix:
        ref_scen = scen_names[min(1, len(scen_names) - 1)]
        home_net = results_matrix[home_city_slug][ref_scen]["net"]["net_monthly_eur"] + city_inputs[
            home_city_slug
        ].get("perks_monthly_eur", 0)
        home_exp = results_matrix[home_city_slug][ref_scen]["budget"]["total_eur"]
        home_surplus = home_net - home_exp
    else:
        home_surplus = 0
        home_net = 0

    row = 1
    ws.write(
        row,
        0,
        f"Reference city: {city_names.get(home_city_slug, home_city_slug)}",
        F["label"],
    )
    ws.write(row, 2, f"Reference net: €{home_net:,.0f}/mo", F["normal"])
    ws.write(row, 4, f"Reference surplus: €{home_surplus:+,.0f}/mo", F["normal"])
    row += 2

    for slug in non_home:
        ci = city_inputs[slug]
        ws.merge_range(row, 0, row, 5, f"📍 {city_names[slug]}", F["subtitle"])
        ws.set_row(row, 15)
        row += 1

        # Break-even salary per scenario
        ws.write(row, 0, "Scenario", F["header"])
        ws.write(row, 1, "Break-even gross/yr (local)", F["header"])
        ws.write(row, 2, "Resulting surplus/mo", F["header"])
        row += 1

        perks = ci.get("perks_monthly_eur", 0)
        active_schemes = list(ci.get("active_schemes", []))
        for scen in scenarios_def:
            budget_eur = results_matrix[slug][scen["name"]]["budget"]["total_eur"]
            target_net = home_surplus + budget_eur - perks
            be_gross = find_target_gross(
                target_net,
                ci["country_code"],
                active_schemes=active_schemes,
            )
            check_net = (
                calculate_net(be_gross, ci["country_code"], active_schemes)["net_monthly_eur"]
                + perks
            )
            actual_surplus = check_net - budget_eur
            sur_fmt = F["surplus_pos"] if actual_surplus >= 0 else F["surplus_neg"]
            ws.write(row, 0, scen["name"], F["normal"])
            ws.write(row, 1, f"{ci['currency']} {be_gross:,}", F["normal"])
            ws.write_number(row, 2, actual_surplus, sur_fmt)
            row += 1

        # Post-rate-change rows (e.g. NL 30%→27% from 2027)
        _cd = load_country(ci["country_code"])
        rc_schemes = [
            (sid, _find_scheme(_cd, sid))
            for sid in active_schemes
            if _find_scheme(_cd, sid) and _find_scheme(_cd, sid).get("rate_change")  # type: ignore[union-attr]
        ]
        if rc_schemes:
            row += 1
            ws.merge_range(row, 0, row, 2, "Post rate-change break-even", F["subtitle"])
            row += 1
            ws.write(row, 0, "Scenario", F["header"])
            ws.write(row, 1, "Break-even gross/yr (post-change)", F["header"])
            ws.write(row, 2, "Resulting surplus/mo", F["header"])
            row += 1
            for sid, scheme_data in rc_schemes:
                rc = scheme_data["rate_change"]  # type: ignore[index]
                new_mult = rc["new_multiplier"]
                old_pct = int((1 - scheme_data["multiplier"]) * 100)  # type: ignore[index]
                new_pct = int((1 - new_mult) * 100)
                overrides = {sid: {"multiplier": new_mult}}
                for scen in scenarios_def:
                    budget_eur = results_matrix[slug][scen["name"]]["budget"]["total_eur"]
                    target_net = home_surplus + budget_eur - perks
                    be_rc = find_target_gross(
                        target_net,
                        ci["country_code"],
                        active_schemes=active_schemes,
                        scheme_overrides=overrides,
                    )
                    check_net_rc = (
                        calculate_net(
                            be_rc, ci["country_code"], active_schemes, scheme_overrides=overrides
                        )["net_monthly_eur"]
                        + perks
                    )
                    actual_surplus_rc = check_net_rc - budget_eur
                    sur_fmt_rc = F["surplus_pos"] if actual_surplus_rc >= 0 else F["surplus_neg"]
                    label = (
                        f"{scen['name']} ({old_pct}%→{new_pct}% ruling from {rc['calendar_year']})"
                    )
                    ws.write(row, 0, label, F["amber"])
                    ws.write(row, 1, f"{ci['currency']} {be_rc:,}", F["amber"])
                    ws.write_number(row, 2, actual_surplus_rc, sur_fmt_rc)
                    row += 1

        # Move readiness
        from engine.budget import load_city

        city_data = load_city(slug)
        hidden = city_data.get("hidden_costs", [])
        _net_data = results_matrix[slug][scen_names[0]]["net"]
        eur_rate = _net_data.get("eur_rate", 1.0)

        mandatory_ot = sum(
            h.get("one_time", 0) * eur_rate
            for h in hidden
            if h.get("mandatory") and "one_time" in h
        )
        comfortable_budget = results_matrix[slug][scen_names[min(1, len(scen_names) - 1)]][
            "budget"
        ]["total_eur"]
        buffer_3m = comfortable_budget * 3
        total_cash = mandatory_ot + buffer_3m

        row += 1
        ws.write(row, 0, "Move readiness (mandatory deposits + 3-month buffer)", F["label"])
        ws.write_number(row, 1, total_cash, F["money_bold"])
        row += 1

        # Permit
        permit = city_data.get("permit", {})
        if permit:
            ws.write(row, 0, "Permit complexity", F["label"])
            ws.write(row, 1, permit.get("complexity", "n/a"), F["normal"])
            ws.write(
                row,
                2,
                f"EU/EEA: {permit.get('eu_eea', {}).get('timeline', 'n/a')}",
                F["normal"],
            )
            ws.write(
                row,
                3,
                f"Non-EU: {permit.get('non_eu', {}).get('timeline', 'n/a')}",
                F["normal"],
            )
            row += 1

        row += 1  # spacer


# ── Sheet 5: Assumptions ──────────────────────────────────────────────────────


def _write_assumptions(
    wb,
    F,
    city_inputs,
    city_names,
    scen_names,
    scenarios_def,
    col_inflation_rate,
    home_city_slug,
):
    ws = wb.add_worksheet("5. Assumptions")
    ws.set_zoom(90)
    ws.set_column(0, 0, 32)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 5, 18)

    ws.merge_range(
        0,
        0,
        0,
        3,
        f"SalaryCompass — Assumptions & Inputs  [{date.today()}]",
        F["title"],
    )
    ws.set_row(0, 22)

    def _row(r, label, *values):
        ws.write(r, 0, label, F["label"])
        for i, v in enumerate(values):
            ws.write(r, i + 1, v, F["normal"])

    row = 2
    ws.write(row, 0, "Global settings", F["subtitle"])
    ws.merge_range(row, 0, row, 3, "Global settings", F["subtitle"])
    row += 1
    _row(row, "Generated on", str(date.today()))
    row += 1
    _row(row, "Home city", city_names.get(home_city_slug, home_city_slug))
    row += 1
    _row(row, "CoL inflation rate (annual)", f"{col_inflation_rate * 100:.1f}%")
    row += 2

    ws.merge_range(row, 0, row, 3, "Per-city inputs", F["subtitle"])
    row += 1
    ws.write(row, 0, "City", F["header"])
    ws.write(row, 1, "Gross/yr", F["header"])
    ws.write(row, 2, "Active schemes", F["header"])
    ws.write(row, 3, "CAGR", F["header"])
    ws.write(row, 4, "Tax-free perks/mo", F["header"])
    ws.set_column(4, 4, 18)
    row += 1

    for slug, ci in city_inputs.items():
        ccy = ci["currency"]
        schemes = ", ".join(ci.get("active_schemes", [])) or "none"
        perks = ci.get("perks_monthly_eur", 0)
        ws.write(row, 0, city_names[slug], F["normal"])
        ws.write(row, 1, f"{ccy} {ci['effective_gross']:,}", F["normal"])
        ws.write(row, 2, schemes, F["normal"])
        ws.write(row, 3, f"{ci['cagr'] * 100:.1f}%", F["normal"])
        ws.write(row, 4, f"€{perks:,.0f}/mo" if perks else "—", F["normal"])
        row += 1

    row += 2
    ws.merge_range(row, 0, row, 3, "Scenarios", F["subtitle"])
    row += 1
    for scen in scenarios_def:
        _row(
            row,
            scen["name"],
            f"Global {scen.get('global_pct', 100)}%",
            f"Cat. multipliers: {len(scen.get('category_multipliers', {}))} customised",
        )
        row += 1

    row += 1
    ws.merge_range(
        row,
        0,
        row,
        3,
        "Directional estimates only — not financial or tax advice.",
        F["caption"],
    )
