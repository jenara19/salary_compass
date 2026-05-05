"""
Smoke tests for output/excel.py — generate_excel_report().

These tests verify that:
- The function returns non-empty bytes
- The bytes form a valid ZIP/XLSX file
- All 5 expected sheets are present in the workbook
"""

import io
import zipfile

from output.excel import generate_excel_report


def _minimal_inputs():
    """Minimal but structurally complete inputs for the export function."""
    city_inputs = {
        "amsterdam": {
            "country_code": "NL",
            "currency": "EUR",
            "gross_annual": 85000,
            "effective_gross": 85000,
            "active_schemes": ["nl_30_ruling"],
            "scheme_expiry": {"nl_30_ruling": 5},
            "ruling_start_year": 2026,
            "cagr": 0.03,
            "perks_monthly_eur": 100.0,
            "city_overrides": {},
            "bonus_pct": 0.0,
            "rsu": 0.0,
            "company": "",
        },
        "berlin": {
            "country_code": "DE",
            "currency": "EUR",
            "gross_annual": 90000,
            "effective_gross": 90000,
            "active_schemes": [],
            "scheme_expiry": {},
            "ruling_start_year": 2026,
            "cagr": 0.03,
            "perks_monthly_eur": 0.0,
            "city_overrides": {},
            "bonus_pct": 0.0,
            "rsu": 0.0,
            "company": "",
        },
    }

    scenarios_def = [
        {
            "name": "comfortable",
            "label": "Comfortable",
            "category_multipliers": {
                "rent": 1.0,
                "food": 1.0,
                "transport": 1.0,
                "healthcare": 1.0,
                "entertainment": 1.0,
                "misc": 1.0,
            },
        }
    ]

    city_names = {"amsterdam": "Amsterdam", "berlin": "Berlin"}
    scen_names = ["comfortable"]

    # Build a minimal results_matrix with correct structure
    from engine.tax import calculate_net
    from engine.trajectory import calculate_trajectory

    results_matrix = {}
    for slug, ci in city_inputs.items():
        results_matrix[slug] = {}
        for scen in scenarios_def:
            net = calculate_net(ci["effective_gross"], ci["country_code"], ci["active_schemes"])
            traj = calculate_trajectory(
                ci["effective_gross"],
                ci["country_code"],
                slug,
                active_schemes=ci["active_schemes"],
                scheme_expiry=ci["scheme_expiry"],
                expenses_eur=2500,
                cagr=ci["cagr"],
                ruling_start_year=ci["ruling_start_year"],
                perks_monthly_eur=ci["perks_monthly_eur"],
            )
            results_matrix[slug][scen["name"]] = {
                "net": net,
                "trajectory": traj,
                "budget": {"total_eur": 2500, "items": {}},
            }

    return city_inputs, results_matrix, scenarios_def, city_names, scen_names


class TestExcelSmoke:
    def test_returns_bytes(self):
        city_inputs, results_matrix, scenarios_def, city_names, scen_names = _minimal_inputs()
        raw = generate_excel_report(
            city_inputs=city_inputs,
            results_matrix=results_matrix,
            scenarios_def=scenarios_def,
            city_names=city_names,
            home_city_slug="amsterdam",
            scen_names=scen_names,
        )
        assert isinstance(raw, bytes), "generate_excel_report must return bytes"
        assert len(raw) > 0, "Returned bytes must be non-empty"

    def test_valid_zip_structure(self):
        """XLSX is a ZIP file — verify it can be opened as such."""
        city_inputs, results_matrix, scenarios_def, city_names, scen_names = _minimal_inputs()
        raw = generate_excel_report(
            city_inputs=city_inputs,
            results_matrix=results_matrix,
            scenarios_def=scenarios_def,
            city_names=city_names,
            home_city_slug="amsterdam",
            scen_names=scen_names,
        )
        buf = io.BytesIO(raw)
        assert zipfile.is_zipfile(buf), "Output must be a valid ZIP/XLSX file"

    def test_five_sheets_present(self):
        """Verify the workbook contains all 5 expected sheets."""
        city_inputs, results_matrix, scenarios_def, city_names, scen_names = _minimal_inputs()
        raw = generate_excel_report(
            city_inputs=city_inputs,
            results_matrix=results_matrix,
            scenarios_def=scenarios_def,
            city_names=city_names,
            home_city_slug="amsterdam",
            scen_names=scen_names,
        )
        buf = io.BytesIO(raw)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            # xl/worksheets/sheet*.xml correspond to each sheet
            sheet_files = [n for n in names if n.startswith("xl/worksheets/sheet")]
        assert len(sheet_files) == 5, f"Expected 5 sheets, found {len(sheet_files)}: {sheet_files}"
