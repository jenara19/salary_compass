"""Pydantic v2 schemas for YAML validation — city and country configurations.

Enables strict schema validation at load time without breaking on future keys.
Tolerates extra fields (extra='allow') to permit gradual feature expansion.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# City YAML Schema
# ============================================================================


class CityPoint(BaseModel):
    """Cost-of-living category (e.g. rent_2bed, groceries_2pax)."""

    generous: float
    comfortable: float
    frugal: float
    fixed: bool | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CityHiddenCost(BaseModel):
    """One-time or recurring hidden cost entry."""

    name: str
    annual: float | None = None
    monthly: float | None = None
    one_time: float | None = None
    mandatory: bool | None = None

    model_config = ConfigDict(extra="allow")


class CityCostOfLiving(BaseModel):
    """Complete cost-of-living breakdown for a city."""

    rent_2bed: CityPoint
    utilities: CityPoint
    health_extra: CityPoint
    groceries_2pax: CityPoint
    transport_2pax: CityPoint
    eating_out: CityPoint
    leisure: CityPoint
    misc: CityPoint
    travel: CityPoint
    personal: CityPoint

    model_config = ConfigDict(extra="allow")


class CityCareer(BaseModel):
    """Career market data and salary expectations."""

    market: str
    typical_cagr: float
    ceiling_gross_eur: float | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CityPermitRules(BaseModel):
    """Visa/permit rules for work eligibility."""

    eu_eea: bool | None = None
    us_visa: bool | None = None
    blue_card: bool | None = None
    notes: list[str] | None = None

    model_config = ConfigDict(extra="allow")


class CityQualitative(BaseModel):
    """Soft factors for relocation decision (A6)."""

    safety_score: float | None = None
    english_friendliness: float | None = None
    expat_community: str | None = None
    climate: str | None = None
    healthcare_quality: str | None = None
    bureaucracy_complexity: str | None = None
    overall_livability: str | None = None
    sources: list[str] | None = None

    model_config = ConfigDict(extra="allow")


class CityConfig(BaseModel):
    """Root schema for city YAML files."""

    name: str
    country: str
    currency: str = "EUR"
    cost_of_living: CityCostOfLiving
    hidden_costs: list[CityHiddenCost]
    career: CityCareer
    permit: dict[str, Any] | None = None
    qualitative: CityQualitative | None = None

    model_config = ConfigDict(extra="allow")


# ============================================================================
# Country YAML Schema
# ============================================================================


class CountryTaxBracket(BaseModel):
    """Single income tax bracket."""

    up_to: float | None = None
    from_: float | None = Field(None, alias="from")
    rate: float

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CountryTaxCredit(BaseModel):
    """Tax credit (Heffingskorting, Working Tax Credit, etc.)."""

    type: str
    name: str
    max_credit: float | None = None
    phase_out_start: float | None = None
    phase_out_end: float | None = None
    phase_out_rate: float | None = None
    bands: list[dict[str, Any]] | None = None

    model_config = ConfigDict(extra="allow")


class CountryIncomeTax(BaseModel):
    """Income tax configuration."""

    personal_allowance: float | None = None
    brackets: list[CountryTaxBracket]
    tax_credits: list[CountryTaxCredit] | None = None

    model_config = ConfigDict(extra="allow")


class CountryEmployeeSocialContribution(BaseModel):
    """Employee social contribution (insurance premium, etc.)."""

    name: str
    monthly_flat: float | None = None
    rate: float | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CountrySocialContributions(BaseModel):
    """Employee and employer social contributions."""

    employee: list[CountryEmployeeSocialContribution] | None = None
    employer: list[dict[str, Any]] | None = None
    cap_annual: float | None = None

    model_config = ConfigDict(extra="allow")


class CountryHealthcare(BaseModel):
    """Healthcare cost model."""

    model: str
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CountryMultiplierScheme(BaseModel):
    """Tax multiplier (e.g. 30% ruling, researcher status)."""

    name: str
    effective_rate: float
    eligible_income_min: float | None = None
    eligible_income_max: float | None = None
    years_allowed: int | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CountrySchemeOverride(BaseModel):
    """Per-year scheme configuration (e.g. NL 30% ruling end-date or change)."""

    year: int
    scheme: str | None = None
    active: bool | None = None
    rate_change: float | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow")


class CountryConfig(BaseModel):
    """Root schema for country YAML files."""

    name: str
    code: str
    currency: str = "EUR"
    eur_rate: float = 1.0
    tax_year: int
    disclaimer: str | None = None
    income_tax: CountryIncomeTax
    social_contributions: CountrySocialContributions
    healthcare: CountryHealthcare
    multiplier_schemes: list[CountryMultiplierScheme] | None = None
    scheme_overrides: list[CountrySchemeOverride] | None = None

    model_config = ConfigDict(extra="allow")
