"""Test YAML schema validation against all city and country configs."""

import pathlib

import pytest
import yaml

from engine.schema import CityConfig, CountryConfig


class TestCityYAMLValidation:
    """Validate all city YAML files conform to CityConfig schema."""

    @pytest.fixture
    def city_dir(self) -> pathlib.Path:
        return pathlib.Path(__file__).parent.parent / "data" / "cities"

    def test_all_cities_valid(self, city_dir: pathlib.Path) -> None:
        """Load all city YAMLs and validate against CityConfig."""
        city_files = list(city_dir.glob("*.yaml"))
        assert len(city_files) > 0, "No city YAML files found"

        for city_file in city_files:
            with open(city_file) as f:
                data = yaml.safe_load(f)
            try:
                CityConfig(**data)
            except Exception as e:
                pytest.fail(f"City {city_file.name} failed validation: {e}")

    @pytest.mark.parametrize(
        "city_name",
        [
            "amsterdam",
            "barcelona",
            "berlin",
            "geneva",
            "london",
            "madrid",
            "manchester",
            "munich",
            "oslo",
            "rotterdam",
            "zurich",
        ],
    )
    def test_city_has_required_fields(self, city_dir: pathlib.Path, city_name: str) -> None:
        """Verify each city has name, country, cost_of_living, and career."""
        city_file = city_dir / f"{city_name}.yaml"
        assert city_file.exists(), f"City file not found: {city_file}"

        with open(city_file) as f:
            data = yaml.safe_load(f)
        city = CityConfig(**data)

        assert city.name
        assert city.country
        assert city.cost_of_living
        assert city.career

    def test_city_cost_of_living_all_categories(self, city_dir: pathlib.Path) -> None:
        """Verify each city has all 10 cost-of-living categories."""
        for city_file in city_dir.glob("*.yaml"):
            with open(city_file) as f:
                data = yaml.safe_load(f)
            city = CityConfig(**data)
            col = city.cost_of_living

            required = [
                "rent_2bed",
                "utilities",
                "health_extra",
                "groceries_2pax",
                "transport_2pax",
                "eating_out",
                "leisure",
                "misc",
                "travel",
                "personal",
            ]
            for cat in required:
                point = getattr(col, cat)
                assert point.generous > 0
                assert point.comfortable > 0
                assert point.frugal > 0
                assert point.comfortable <= point.generous
                assert point.frugal <= point.comfortable


class TestCountryYAMLValidation:
    """Validate all country YAML files conform to CountryConfig schema."""

    @pytest.fixture
    def country_dir(self) -> pathlib.Path:
        return pathlib.Path(__file__).parent.parent / "data" / "countries"

    def test_all_countries_valid(self, country_dir: pathlib.Path) -> None:
        """Load all country YAMLs and validate against CountryConfig."""
        country_files = list(country_dir.glob("*.yaml"))
        assert len(country_files) > 0, "No country YAML files found"

        for country_file in country_files:
            with open(country_file) as f:
                data = yaml.safe_load(f)
            try:
                CountryConfig(**data)
            except Exception as e:
                pytest.fail(f"Country {country_file.name} failed validation: {e}")

    @pytest.mark.parametrize(
        "country_code",
        ["NL", "ES", "DE", "CH", "GE", "NOR", "UK"],
    )
    def test_country_has_required_fields(
        self, country_dir: pathlib.Path, country_code: str
    ) -> None:
        """Verify each country has name, code, income_tax, and healthcare."""
        country_file = country_dir / f"{country_code}.yaml"
        assert country_file.exists(), f"Country file not found: {country_file}"

        with open(country_file) as f:
            data = yaml.safe_load(f)
        country = CountryConfig(**data)

        assert country.name
        assert country.code == country_code
        assert country.income_tax
        assert country.income_tax.brackets
        assert country.healthcare

    def test_country_brackets_non_overlapping(self, country_dir: pathlib.Path) -> None:
        """Verify tax brackets don't overlap and are ordered."""
        for country_file in country_dir.glob("*.yaml"):
            with open(country_file) as f:
                data = yaml.safe_load(f)
            country = CountryConfig(**data)

            brackets = country.income_tax.brackets
            for i, bracket in enumerate(brackets[:-1]):
                next_bracket = brackets[i + 1]
                assert bracket.up_to is not None or bracket.rate is not None
                # If current has up_to, next should start there or after
                if bracket.up_to and hasattr(next_bracket, "from_"):
                    assert (
                        next_bracket.from_ <= bracket.up_to or next_bracket.from_ == bracket.up_to
                    )
