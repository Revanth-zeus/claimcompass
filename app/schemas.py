"""
ClaimCompass — ACORD Form 3 extraction schema.

26 fields, all optional. A blank ACORD must parse into this schema without
raising; the blank-form test exists specifically to confirm the parser
does not hallucinate missing values.

Field groupings:
  1-4    Claim identity + carrier
  5-10   Liability classification (premises/products branches)
  11-13  Parties (insured + property owner + manufacturer)
  14-18  Occurrence (location, description, authority contacted, scheduled location)
  19-23  Injured party (severity proxies for state classifier)
  24-25  Property damage (feeds reserve-setting stage)
  26     Witness count (contestability signal)

Every field below feeds a downstream decision. Fields that would only
exist as passive data (e.g., gender) were excluded on principle.
"""

from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# -------- Enums for the liability branch --------

class LiabilityType(str, Enum):
    """Derived from which InsuredInterest indicator fields are set on the form."""
    PREMISES = "premises"
    PRODUCTS = "products"
    BOTH = "both"
    UNKNOWN = "unknown"


class PremisesRole(str, Enum):
    """Maps to LossProperty_InsuredInterest_{Owner,Tenant,Other}Indicator."""
    OWNER = "owner"
    TENANT = "tenant"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProductsRole(str, Enum):
    """Maps to LossProduct_InsuredInterest_{Manufacturer,Vendor,Other}Indicator."""
    MANUFACTURER = "manufacturer"
    VENDOR = "vendor"
    OTHER = "other"
    UNKNOWN = "unknown"


class ExtractionPath(str, Enum):
    """Which parsing path was taken. Logged on every run for observability."""
    PYPDF_FILLABLE = "pypdf_fillable"      # deterministic, 0 LLM calls
    GEMINI_VISION = "gemini_vision"        # fallback for flattened/scanned
    FAILED = "failed"


# -------- Nested structures --------

class AuthorityReport(BaseModel):
    """Police or fire department contact info — feeds evidence checklist."""
    authority_name: Optional[str] = None      # Loss_AuthorityContactedName_A
    report_number: Optional[str] = None       # Loss_ReportIdentifier_A


class InjuredParty(BaseModel):
    """Severity signals for the state classifier. Name is extracted for
    cross-referencing with later medical-authorization documents."""
    full_name: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    injury_description: Optional[str] = None      # ExtentOfInjury_A — severity signal
    treatment_location: Optional[str] = None      # TakenToDescription_A (ER/urgent care/none)


class PropertyDamage(BaseModel):
    """Damages quantification for reserve-setting stage."""
    description: Optional[str] = None
    estimated_amount: Optional[str] = None    # kept as str — form accepts free text


# -------- Top-level claim record --------

class ClaimRecord(BaseModel):
    """
    Structured claim record extracted from an ACORD Form 3.

    All fields optional. A blank form produces a record where nearly every
    field is None — that is the correct behavior and is what the blank-form
    test verifies.
    """

    # --- Identity + timing (1-4) ---
    form_completion_date: Optional[date] = None           # gap from loss → report
    date_of_loss: Optional[date] = None
    time_of_loss: Optional[time] = None
    policy_number: Optional[str] = None

    # --- Carrier ---
    carrier_name: Optional[str] = None
    carrier_naic_code: Optional[str] = None

    # --- Liability classification (5-10) ---
    liability_type: LiabilityType = LiabilityType.UNKNOWN
    premises_role: PremisesRole = PremisesRole.UNKNOWN
    premises_type: Optional[str] = None                   # free text: "restaurant", etc.
    products_role: ProductsRole = ProductsRole.UNKNOWN
    product_description: Optional[str] = None
    product_viewable_location: Optional[str] = None       # where product can be inspected

    # --- Parties (11-13) ---
    insured_name: Optional[str] = None
    property_owner_name: Optional[str] = None             # populated only if tenant
    product_manufacturer_name: Optional[str] = None       # populated only if vendor

    # --- Occurrence (14-18) ---
    loss_location_city: Optional[str] = None
    loss_location_state: Optional[str] = None
    loss_location_description: Optional[str] = None       # free-text fallback
    loss_description: Optional[str] = None                # main narrative box
    authority_contacted: AuthorityReport = Field(default_factory=AuthorityReport)
    insured_location_code: Optional[str] = None           # scheduled-location code

    # --- Injured party (19-23) ---
    injured_party: InjuredParty = Field(default_factory=InjuredParty)

    # --- Property damage (24-25) ---
    property_damage: PropertyDamage = Field(default_factory=PropertyDamage)

    # --- Contestability (26) ---
    witness_count: int = 0                                # derived from 3 witness slots

    # --- Metadata (not part of the 26; pipeline bookkeeping) ---
    claim_fingerprint: Optional[str] = None
    extraction_path: ExtractionPath = ExtractionPath.FAILED
    extraction_notes: list[str] = Field(default_factory=list)

    def populated_field_count(self) -> int:
        """How many of the 26 core fields are populated. Used by the test harness."""
        count = 0
        # Top-level scalars
        for name in [
            "form_completion_date", "date_of_loss", "time_of_loss", "policy_number",
            "carrier_name", "carrier_naic_code", "premises_type",
            "product_description", "product_viewable_location", "insured_name",
            "property_owner_name", "product_manufacturer_name",
            "loss_location_city", "loss_location_state", "loss_location_description",
            "loss_description", "insured_location_code",
        ]:
            if getattr(self, name) is not None:
                count += 1
        # Enums: count only if not UNKNOWN
        if self.liability_type != LiabilityType.UNKNOWN:
            count += 1
        if self.premises_role != PremisesRole.UNKNOWN:
            count += 1
        if self.products_role != ProductsRole.UNKNOWN:
            count += 1
        # Nested
        if self.authority_contacted.authority_name or self.authority_contacted.report_number:
            count += 1
        for name in ["full_name", "age", "occupation", "injury_description", "treatment_location"]:
            if getattr(self.injured_party, name) is not None:
                count += 1
        if self.property_damage.description is not None:
            count += 1
        if self.property_damage.estimated_amount is not None:
            count += 1
        if self.witness_count > 0:
            count += 1
        return count
