"""
ClaimCompass — ACORD Form 3 parser.

Two-path design:
  1. pypdf.get_fields()  — fillable PDF, deterministic, 0 LLM calls
  2. Gemini vision        — fallback for flattened or scanned PDFs

The parser logs which path it took on every run. That observability is
deliberate: it sells the architecture in a demo ("fillable gets 0 LLM
calls, scan falls back to vision") and it catches silent regressions
(if every incoming ACORD suddenly starts hitting the fallback path,
something upstream changed).

Field-name mapping comes from direct inspection of the ACORD 3 (2019/09)
fillable PDF — all names were confirmed via pypdf.get_fields() against
the real form, not guessed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Optional

from pypdf import PdfReader

from app.fingerprint import compute_fingerprint
from app.schemas import (
    AuthorityReport,
    ClaimRecord,
    ExtractionPath,
    InjuredParty,
    LiabilityType,
    PremisesRole,
    ProductsRole,
    PropertyDamage,
)

log = logging.getLogger("claimcompass.parser")


# --------------------------------------------------------------------------
# Field-name constants.
# These names were read directly from the fillable PDF via pypdf.get_fields()
# and are stable for ACORD 3 (2019/09). If ACORD releases a new revision,
# this mapping is the only thing that needs updating.
# --------------------------------------------------------------------------

F_COMPLETION_DATE = "Form_CompletionDate_A"
F_LOSS_DATE = "Loss_IncidentDate_A"
F_LOSS_TIME = "Loss_IncidentTime_A"
F_LOSS_AM = "Loss_IncidentTimeAMIndicator_A"
F_LOSS_PM = "Loss_IncidentTimePMIndicator_A"
F_POLICY_NUMBER = "Policy_PolicyNumberIdentifier_A"
F_CARRIER = "Insurer_FullName_A"
F_NAIC = "Insurer_NAICCode_A"
F_INSURED_LOCATION_CODE = "Loss_InsuredLocationCode_A"

F_INSURED_NAME = "NamedInsured_FullName_A"
F_PROPERTY_OWNER = "LossPropertyOwner_FullName_A"
F_MANUFACTURER = "LossProductManufacturer_FullName_A"

F_LOSS_CITY = "LossLocation_PhysicalAddress_CityName_A"
F_LOSS_STATE = "LossLocation_PhysicalAddress_StateOrProvinceCode_A"
F_LOSS_LOCATION_DESC = "LossLocation_LocationDescription_A"
F_LOSS_DESCRIPTION = "Loss_LossDescription_A"
F_AUTHORITY_NAME = "Loss_AuthorityContactedName_A"
F_AUTHORITY_REPORT_ID = "Loss_ReportIdentifier_A"

# Premises branch
F_PREMISES_OWNER = "LossProperty_InsuredInterest_OwnerIndicator_A"
F_PREMISES_TENANT = "LossProperty_InsuredInterest_TenantIndicator_A"
F_PREMISES_OTHER = "LossProperty_InsuredInterest_OtherIndicator_A"
F_PREMISES_DESC = "LossProperty_PremisesDescription_A"

# Products branch
F_PRODUCTS_MFR = "LossProduct_InsuredInterest_ManufacturerIndicator_A"
F_PRODUCTS_VENDOR = "LossProduct_InsuredInterest_VendorIndicator_A"
F_PRODUCTS_OTHER = "LossProduct_InsuredInterest_OtherIndicator_A"
F_PRODUCT_DESC = "LossProduct_ProductDescription_A"
F_PRODUCT_VIEWABLE = "LossProduct_ViewableLocation_A"

# Page 2
F_INJURED_NAME = "LossInjuredParty_FullName_A"
F_INJURED_AGE = "LossInjuredParty_Age_A"
F_INJURED_OCCUPATION = "LossInjuredParty_Occupation_A"
F_INJURED_EXTENT = "LossInjuredParty_ExtentOfInjury_A"
F_INJURED_TAKEN_TO = "LossInjuredParty_TakenToDescription_A"

F_PROPERTY_DESC = "LossProperty_PropertyDescription_A"
F_PROPERTY_ESTIMATE = "LossProperty_EstimatedDamageAmount_A"

# Witnesses — form supports 3 slots natively (A, B, C)
F_WITNESS_SLOTS = [
    "LossWitness_FullName_A",
    "LossWitness_FullName_B",
    "LossWitness_FullName_C",
]


# --------------------------------------------------------------------------
# Helpers for reading values out of pypdf's fields dict.
# pypdf returns a dict keyed on the fully-qualified name (e.g.
# 'F[0].P1[0].Loss_IncidentDate_A[0]'). We match on suffix because the
# top-level prefix is an implementation detail of the form's XFA tree.
# --------------------------------------------------------------------------

def _find_field_value(fields: dict, short_name: str) -> Optional[str]:
    """Look up a field by its short suffix. Returns the /V value or None."""
    target_suffix = f".{short_name}[0]"
    for full_name, field in fields.items():
        if full_name.endswith(target_suffix) or full_name == short_name:
            value = field.get("/V")
            if value is None:
                return None
            # pypdf sometimes returns ByteStrings; coerce to str and strip.
            value_str = str(value).strip()
            return value_str if value_str else None
    return None


def _is_checkbox_set(fields: dict, short_name: str) -> bool:
    """ACORD checkboxes: on-state is the NameObject '/1', off-state is '/Off' or None.

    We accept a small set of common checkbox on-values from other insurers too
    ('yes', 'on', 'true', plain '1'), but for ACORD 3 the canonical value is '/1'.
    """
    raw = _find_field_value(fields, short_name)
    if raw is None:
        return False
    normalized = raw.lstrip("/").lower()
    return normalized in {"1", "yes", "on", "true"}


def _parse_date(value: Optional[str]) -> Optional[date]:
    """ACORD forms commonly use MM/DD/YYYY. Be tolerant of a few variants."""
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    log.warning("Could not parse date value: %r", value)
    return None


def _parse_time(value: Optional[str], am: bool, pm: bool) -> Optional[time]:
    """Parse loss time. AM/PM come from separate indicator fields on the form."""
    if not value:
        return None
    raw = value.strip().replace(" ", "")
    for fmt in ("%H:%M", "%I:%M"):
        try:
            t = datetime.strptime(raw, fmt).time()
            if pm and t.hour < 12:
                t = t.replace(hour=t.hour + 12)
            elif am and t.hour == 12:
                t = t.replace(hour=0)
            return t
        except ValueError:
            continue
    return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------
# Branch-classification logic.
# The liability type is DERIVED from which indicator fields are checked —
# we do not trust or require a single "liability_type" field because the
# form doesn't have one. It has two independent branches (premises and
# products), each with its own indicator set.
# --------------------------------------------------------------------------

def _classify_liability(fields: dict) -> tuple[LiabilityType, PremisesRole, ProductsRole]:
    premises_signals = any(
        _is_checkbox_set(fields, f) for f in (F_PREMISES_OWNER, F_PREMISES_TENANT, F_PREMISES_OTHER)
    ) or bool(_find_field_value(fields, F_PREMISES_DESC))

    products_signals = any(
        _is_checkbox_set(fields, f) for f in (F_PRODUCTS_MFR, F_PRODUCTS_VENDOR, F_PRODUCTS_OTHER)
    ) or bool(_find_field_value(fields, F_PRODUCT_DESC))

    if premises_signals and products_signals:
        liability = LiabilityType.BOTH
    elif premises_signals:
        liability = LiabilityType.PREMISES
    elif products_signals:
        liability = LiabilityType.PRODUCTS
    else:
        liability = LiabilityType.UNKNOWN

    if _is_checkbox_set(fields, F_PREMISES_OWNER):
        premises_role = PremisesRole.OWNER
    elif _is_checkbox_set(fields, F_PREMISES_TENANT):
        premises_role = PremisesRole.TENANT
    elif _is_checkbox_set(fields, F_PREMISES_OTHER):
        premises_role = PremisesRole.OTHER
    else:
        premises_role = PremisesRole.UNKNOWN

    if _is_checkbox_set(fields, F_PRODUCTS_MFR):
        products_role = ProductsRole.MANUFACTURER
    elif _is_checkbox_set(fields, F_PRODUCTS_VENDOR):
        products_role = ProductsRole.VENDOR
    elif _is_checkbox_set(fields, F_PRODUCTS_OTHER):
        products_role = ProductsRole.OTHER
    else:
        products_role = ProductsRole.UNKNOWN

    return liability, premises_role, products_role


# --------------------------------------------------------------------------
# Primary extraction path: pypdf fillable form reader.
# --------------------------------------------------------------------------

def _extract_from_fillable(fields: dict[str, Any]) -> ClaimRecord:
    """Build a ClaimRecord from a pypdf get_fields() dict."""
    liability, premises_role, products_role = _classify_liability(fields)

    # Witness count: number of non-empty witness name slots
    witness_count = sum(
        1 for slot in F_WITNESS_SLOTS if _find_field_value(fields, slot)
    )

    am = _is_checkbox_set(fields, F_LOSS_AM)
    pm = _is_checkbox_set(fields, F_LOSS_PM)

    record = ClaimRecord(
        form_completion_date=_parse_date(_find_field_value(fields, F_COMPLETION_DATE)),
        date_of_loss=_parse_date(_find_field_value(fields, F_LOSS_DATE)),
        time_of_loss=_parse_time(_find_field_value(fields, F_LOSS_TIME), am, pm),
        policy_number=_find_field_value(fields, F_POLICY_NUMBER),

        carrier_name=_find_field_value(fields, F_CARRIER),
        carrier_naic_code=_find_field_value(fields, F_NAIC),

        liability_type=liability,
        premises_role=premises_role,
        premises_type=_find_field_value(fields, F_PREMISES_DESC),
        products_role=products_role,
        product_description=_find_field_value(fields, F_PRODUCT_DESC),
        product_viewable_location=_find_field_value(fields, F_PRODUCT_VIEWABLE),

        insured_name=_find_field_value(fields, F_INSURED_NAME),
        property_owner_name=_find_field_value(fields, F_PROPERTY_OWNER),
        product_manufacturer_name=_find_field_value(fields, F_MANUFACTURER),

        loss_location_city=_find_field_value(fields, F_LOSS_CITY),
        loss_location_state=_find_field_value(fields, F_LOSS_STATE),
        loss_location_description=_find_field_value(fields, F_LOSS_LOCATION_DESC),
        loss_description=_find_field_value(fields, F_LOSS_DESCRIPTION),
        authority_contacted=AuthorityReport(
            authority_name=_find_field_value(fields, F_AUTHORITY_NAME),
            report_number=_find_field_value(fields, F_AUTHORITY_REPORT_ID),
        ),
        insured_location_code=_find_field_value(fields, F_INSURED_LOCATION_CODE),

        injured_party=InjuredParty(
            full_name=_find_field_value(fields, F_INJURED_NAME),
            age=_parse_int(_find_field_value(fields, F_INJURED_AGE)),
            occupation=_find_field_value(fields, F_INJURED_OCCUPATION),
            injury_description=_find_field_value(fields, F_INJURED_EXTENT),
            treatment_location=_find_field_value(fields, F_INJURED_TAKEN_TO),
        ),

        property_damage=PropertyDamage(
            description=_find_field_value(fields, F_PROPERTY_DESC),
            estimated_amount=_find_field_value(fields, F_PROPERTY_ESTIMATE),
        ),

        witness_count=witness_count,
        extraction_path=ExtractionPath.PYPDF_FILLABLE,
    )

    record.claim_fingerprint = compute_fingerprint(
        record.insured_name, record.date_of_loss, record.policy_number
    )
    return record


# --------------------------------------------------------------------------
# Fallback path: Gemini vision.
# This is a stub that raises a clear error. Full implementation lands on
# Day 3 when we have the Gemini client wired up (reused from ClaimFlow).
# The stub exists now so the architecture is visible from Day 1.
# --------------------------------------------------------------------------

def _extract_via_gemini_vision(pdf_path: Path) -> ClaimRecord:
    """Vision-based fallback for flattened / scanned ACORDs.

    Stubbed for Day 1. On Day 3 this gets wired to the ClaimFlow Gemini
    2.5 Flash client with a structured-output schema matching ClaimRecord.
    """
    raise NotImplementedError(
        "Gemini vision fallback lands on Day 3. Day 1 scope is the pypdf path."
    )


# --------------------------------------------------------------------------
# Public entry point.
# --------------------------------------------------------------------------

def parse_acord(pdf_path: str | Path) -> ClaimRecord:
    """Parse an ACORD Form 3 PDF into a ClaimRecord.

    Path selection:
      - If pypdf.get_fields() returns a non-empty dict → fillable form path
      - Otherwise → Gemini vision fallback (Day 3)

    Every return value carries `extraction_path` so downstream systems can
    see how the record was produced.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}

    if fields:
        log.info(
            "ACORD parse: fillable form detected (%d fields). Using pypdf path. 0 LLM calls.",
            len(fields),
        )
        return _extract_from_fillable(fields)

    log.info("ACORD parse: no fillable fields detected. Falling back to Gemini vision.")
    return _extract_via_gemini_vision(pdf_path)
