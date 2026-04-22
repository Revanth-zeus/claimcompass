"""
ClaimCompass — Evidence Checklist Engine (Day 2).

Deterministic checklist rules keyed on liability_type. Each evidence item has:
  - A category (which liability types require it)
  - A time window (when it's typically expected after date_of_loss)
  - A status computed from what's present in the claim record

Status logic:
  PRESENT       — evidence confirmed in the ACORD or follow-up docs
  MISSING       — past the expected window, still not present
  NOT_YET_DUE   — within normal timeframe, absence is not a flag
  NOT_APPLICABLE — this evidence type doesn't apply to this claim

Time windows are conservative estimates from public adjuster training
material and standard CGL claims-handling practice. They are NOT
fabricated statistics — they represent "when a competent adjuster would
typically expect to have this" not "X% of claims have this by day N."

No fake citations. No NAIC numbers. No invented benchmarks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from app.schemas import ClaimRecord, LiabilityType, PremisesRole, ProductsRole


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------

class EvidenceStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    NOT_YET_DUE = "not_yet_due"
    NOT_APPLICABLE = "not_applicable"


class EvidenceCategory(str, Enum):
    """Which liability branches require this evidence."""
    BOTH = "both"              # required for any liability claim
    PREMISES = "premises"      # premises-specific
    PRODUCTS = "products"      # products-specific


class EvidencePriority(str, Enum):
    """How urgently this item matters for claim progression."""
    CRITICAL = "critical"      # blocks stage transitions if missing
    IMPORTANT = "important"    # should be present, flags if missing
    SUPPORTING = "supporting"  # nice to have, absence is informational


# --------------------------------------------------------------------------
# Evidence item definition
# --------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """A single item on the evidence checklist."""
    id: str                          # stable key for Day 3 auto-checkoff
    label: str                       # human-readable name
    category: EvidenceCategory       # which liability branches need it
    priority: EvidencePriority
    expected_by_day: int             # days after loss when absence becomes a flag
    description: str                 # why this matters (shown in UI)
    status: EvidenceStatus = EvidenceStatus.NOT_YET_DUE
    status_reason: str = ""          # explains why this status was assigned


@dataclass
class EvidenceChecklist:
    """Full checklist for a claim, with summary stats."""
    claim_fingerprint: Optional[str]
    liability_type: LiabilityType
    elapsed_days: Optional[int]      # days since loss, None if date unknown
    items: list[EvidenceItem] = field(default_factory=list)
    generation_notes: list[str] = field(default_factory=list)

    @property
    def present_count(self) -> int:
        return sum(1 for i in self.items if i.status == EvidenceStatus.PRESENT)

    @property
    def missing_count(self) -> int:
        return sum(1 for i in self.items if i.status == EvidenceStatus.MISSING)

    @property
    def not_yet_due_count(self) -> int:
        return sum(1 for i in self.items if i.status == EvidenceStatus.NOT_YET_DUE)

    @property
    def applicable_count(self) -> int:
        return sum(1 for i in self.items if i.status != EvidenceStatus.NOT_APPLICABLE)


# --------------------------------------------------------------------------
# Evidence catalog.
# Each tuple: (id, label, category, priority, expected_by_day, description)
#
# Time windows rationale:
#   0-7 days:   Items the adjuster needs in the first contact round
#   7-14 days:  Items that require a request + response cycle
#   14-30 days: Items that depend on third-party cooperation
#   30-60 days: Items that require medical treatment to stabilize
#   60+ days:   Late-stage items (demands, settlements)
#
# These are NOT benchmarks. They are "when absence becomes noteworthy."
# --------------------------------------------------------------------------

_EVIDENCE_CATALOG: list[tuple[str, str, EvidenceCategory, EvidencePriority, int, str]] = [
    # --- Universal (both premises and products) ---
    (
        "policy_verification",
        "CGL Policy Verification",
        EvidenceCategory.BOTH,
        EvidencePriority.CRITICAL,
        7,
        "Confirm active policy, coverage dates, and that the loss location/product "
        "is within policy scope. This is the first thing an adjuster checks."
    ),
    (
        "police_fire_report",
        "Police or Fire Department Report",
        EvidenceCategory.BOTH,
        EvidencePriority.IMPORTANT,
        14,
        "Official incident report. Not always filed (minor incidents may not "
        "involve authorities), but if the ACORD indicates contact, the report "
        "should be obtained."
    ),
    (
        "claimant_statement",
        "Claimant's Recorded/Written Statement",
        EvidenceCategory.BOTH,
        EvidencePriority.IMPORTANT,
        14,
        "First-person account from the injured party describing the incident."
    ),
    (
        "witness_statements",
        "Witness Statements",
        EvidenceCategory.BOTH,
        EvidencePriority.IMPORTANT,
        21,
        "Statements from witnesses listed on the ACORD. The number of witnesses "
        "affects contestability — 0 witnesses means the account is unverified."
    ),
    (
        "medical_authorization",
        "Medical Records Authorization (HIPAA Release)",
        EvidenceCategory.BOTH,
        EvidencePriority.CRITICAL,
        14,
        "Signed authorization allowing the carrier to obtain claimant's medical "
        "records. Required before medical records can be requested."
    ),
    (
        "medical_records",
        "Claimant Medical Records",
        EvidenceCategory.BOTH,
        EvidencePriority.CRITICAL,
        45,
        "Treatment records documenting the injury, diagnosis, and prognosis. "
        "Needed for reserve setting and damages evaluation."
    ),
    (
        "medical_bills",
        "Medical Bills / Itemized Charges",
        EvidenceCategory.BOTH,
        EvidencePriority.IMPORTANT,
        45,
        "Itemized medical expenses. Required for damages quantification."
    ),
    (
        "insured_statement",
        "Insured's Statement",
        EvidenceCategory.BOTH,
        EvidencePriority.IMPORTANT,
        14,
        "Statement from the named insured about the circumstances of the loss."
    ),
    (
        "attorney_letter",
        "Attorney Letter of Representation",
        EvidenceCategory.BOTH,
        EvidencePriority.SUPPORTING,
        90,
        "If the claimant has retained counsel, a letter of representation will "
        "arrive. Early attorney involvement (within 30 days) is a complexity signal."
    ),
    (
        "settlement_demand",
        "Settlement Demand / Demand Letter",
        EvidenceCategory.BOTH,
        EvidencePriority.SUPPORTING,
        120,
        "Formal demand for settlement from claimant or claimant's counsel."
    ),
    (
        "release_settlement",
        "Release / Settlement Agreement",
        EvidenceCategory.BOTH,
        EvidencePriority.SUPPORTING,
        180,
        "Signed release closing the claim. Presence signals Resolution stage."
    ),

    # --- Premises-specific ---
    (
        "photos_location",
        "Photos of Loss Location",
        EvidenceCategory.PREMISES,
        EvidencePriority.CRITICAL,
        7,
        "Photos of the specific location where the incident occurred — condition "
        "of flooring, lighting, signage, structural elements. Time-sensitive: "
        "conditions change."
    ),
    (
        "maintenance_records",
        "Premises Maintenance / Inspection Records",
        EvidenceCategory.PREMISES,
        EvidencePriority.IMPORTANT,
        21,
        "Records showing maintenance history for the area where the loss occurred. "
        "Relevant to establishing or refuting negligence."
    ),
    (
        "incident_report_internal",
        "Internal Incident Report",
        EvidenceCategory.PREMISES,
        EvidencePriority.IMPORTANT,
        7,
        "The insured's own incident report filed at the time of the event."
    ),
    (
        "surveillance_footage",
        "Surveillance / Security Camera Footage",
        EvidenceCategory.PREMISES,
        EvidencePriority.CRITICAL,
        7,
        "If surveillance is mentioned in the loss description, footage must be "
        "preserved immediately — most systems overwrite within 7-30 days."
    ),
    (
        "lease_ownership_proof",
        "Proof of Ownership or Lease Agreement",
        EvidenceCategory.PREMISES,
        EvidencePriority.IMPORTANT,
        14,
        "Establishes the insured's legal relationship to the premises. "
        "Critical for tenant-insured claims where the property owner is a "
        "separate party."
    ),

    # --- Products-specific ---
    (
        "product_identification",
        "Product Identification / Batch Records",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.CRITICAL,
        7,
        "Serial number, batch/lot number, manufacturing date, model number. "
        "Required to trace the specific unit and identify potential defect scope."
    ),
    (
        "product_inspection",
        "Product Inspection / Preservation",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.CRITICAL,
        14,
        "Physical inspection of the product by an expert or adjuster. The product "
        "must be preserved — spoliation of evidence is a serious issue."
    ),
    (
        "product_purchase_records",
        "Purchase Records / Receipt",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.IMPORTANT,
        14,
        "Proof of purchase: where, when, and from whom the product was acquired. "
        "Establishes chain of distribution and identifies responsible parties."
    ),
    (
        "recall_history",
        "Recall / Safety Bulletin History",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.IMPORTANT,
        14,
        "Check CPSC, manufacturer recalls, and safety bulletins for the product "
        "model. Prior recalls are relevant to foreseeability."
    ),
    (
        "product_manual_warnings",
        "Product Manual / Warning Labels",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.IMPORTANT,
        14,
        "Documentation of warnings, instructions, and safety labels on the product."
    ),
    (
        "manufacturer_notice",
        "Notice to Manufacturer (if vendor/distributor)",
        EvidenceCategory.PRODUCTS,
        EvidencePriority.CRITICAL,
        14,
        "If the insured is a vendor or distributor (not manufacturer), the "
        "manufacturer must be notified. This is both a contractual obligation "
        "and a coverage requirement under most vendor endorsements."
    ),
]


# --------------------------------------------------------------------------
# Status-assignment logic.
# --------------------------------------------------------------------------

def _check_policy_verification(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Policy is 'present' if we have policy_number + carrier + location code."""
    has_policy = bool(record.policy_number)
    has_carrier = bool(record.carrier_name)
    has_location = bool(record.insured_location_code)

    if has_policy and has_carrier and has_location:
        return EvidenceStatus.PRESENT, (
            f"Policy {record.policy_number} with {record.carrier_name}, "
            f"location code {record.insured_location_code} present on ACORD."
        )
    missing_parts = []
    if not has_policy:
        missing_parts.append("policy number")
    if not has_carrier:
        missing_parts.append("carrier name")
    if not has_location:
        missing_parts.append("insured location code")
    return EvidenceStatus.MISSING, (
        f"Coverage verification incomplete — missing: {', '.join(missing_parts)}. "
        f"Cannot confirm active coverage without these."
    )


def _check_police_fire_report(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Present if authority contacted AND report number exist."""
    has_authority = bool(record.authority_contacted.authority_name)
    has_report_num = bool(record.authority_contacted.report_number)

    if has_authority and has_report_num:
        return EvidenceStatus.PRESENT, (
            f"{record.authority_contacted.authority_name} contacted, "
            f"report #{record.authority_contacted.report_number}."
        )
    if has_authority and not has_report_num:
        return EvidenceStatus.MISSING, (
            f"{record.authority_contacted.authority_name} contacted per ACORD, "
            f"but no report number recorded. Report should be obtained."
        )
    # No authority contacted at all — not necessarily missing, just not filed
    return EvidenceStatus.NOT_YET_DUE, (
        "No police/fire contact indicated on ACORD. May not be applicable "
        "for minor incidents, but should be confirmed with insured."
    )


def _check_witness_statements(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Status depends on whether witnesses exist."""
    if record.witness_count == 0:
        return EvidenceStatus.NOT_YET_DUE, (
            "No witnesses listed on ACORD. Claimant account is currently "
            "unverified — this affects contestability."
        )
    return EvidenceStatus.NOT_YET_DUE, (
        f"{record.witness_count} witness(es) listed on ACORD. "
        f"Statements should be obtained from each."
    )


def _check_surveillance(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Flag as critical if the loss description mentions cameras/surveillance."""
    desc = (record.loss_description or "").lower()
    mentions_surveillance = any(
        kw in desc for kw in ["camera", "surveillance", "cctv", "video", "footage", "recorded"]
    )
    if mentions_surveillance:
        return EvidenceStatus.MISSING, (
            "Loss description mentions surveillance/camera. Footage must be "
            "preserved immediately — most systems overwrite within 7-30 days. "
            "This is time-critical."
        )
    return EvidenceStatus.NOT_YET_DUE, (
        "No surveillance mentioned in loss description. Confirm with insured "
        "whether cameras cover the loss location."
    )


def _check_property_damage(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Check if property damage exists on the claim."""
    has_desc = bool(record.property_damage.description)
    has_est = bool(record.property_damage.estimated_amount)
    if has_desc or has_est:
        parts = []
        if has_desc:
            parts.append(f"description: {record.property_damage.description[:80]}")
        if has_est:
            parts.append(f"estimate: {record.property_damage.estimated_amount}")
        return EvidenceStatus.PRESENT, f"Property damage documented — {'; '.join(parts)}."
    return EvidenceStatus.NOT_APPLICABLE, "No property damage indicated on ACORD."


def _check_manufacturer_notice(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Only applicable if insured is vendor/distributor, not manufacturer."""
    if record.products_role == ProductsRole.MANUFACTURER:
        return EvidenceStatus.NOT_APPLICABLE, (
            "Insured is the manufacturer — no third-party manufacturer to notify."
        )
    mfr_name = record.product_manufacturer_name
    if mfr_name:
        return EvidenceStatus.NOT_YET_DUE, (
            f"Insured is {record.products_role.value}. Manufacturer "
            f"({mfr_name}) must be notified per vendor endorsement terms."
        )
    return EvidenceStatus.MISSING, (
        f"Insured is {record.products_role.value} but no manufacturer "
        f"identified on ACORD. Manufacturer must be identified and notified."
    )


def _check_lease_ownership(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Especially important if insured is tenant."""
    if record.premises_role == PremisesRole.TENANT:
        owner = record.property_owner_name
        if owner:
            return EvidenceStatus.NOT_YET_DUE, (
                f"Insured is tenant; property owner ({owner}) listed. "
                f"Lease agreement should be obtained to clarify maintenance obligations."
            )
        return EvidenceStatus.MISSING, (
            "Insured is tenant but no property owner identified on ACORD. "
            "Lease agreement and owner identity are needed for liability allocation."
        )
    if record.premises_role == PremisesRole.OWNER:
        return EvidenceStatus.NOT_YET_DUE, (
            "Insured is owner. Proof of ownership may be needed to confirm "
            "insurable interest."
        )
    return EvidenceStatus.NOT_YET_DUE, "Ownership/tenancy status unclear."


def _check_medical_records(record: ClaimRecord) -> tuple[EvidenceStatus, str]:
    """Medical records relevance depends on injury severity signals."""
    has_injury = bool(record.injured_party.injury_description)
    treatment = record.injured_party.treatment_location or ""

    if not has_injury:
        return EvidenceStatus.NOT_APPLICABLE, "No injury described on ACORD."

    severity_signals = []
    treatment_lower = treatment.lower()
    if any(kw in treatment_lower for kw in ["emergency", "er", "burn unit", "trauma", "admitted"]):
        severity_signals.append(f"ER/hospital treatment ({treatment[:60]})")
    if record.injured_party.age and record.injured_party.age >= 65:
        severity_signals.append(f"claimant age {record.injured_party.age}")

    injury_lower = (record.injured_party.injury_description or "").lower()
    if any(kw in injury_lower for kw in ["fracture", "surgery", "graft", "concussion", "burn"]):
        severity_signals.append("significant injury type noted")

    if severity_signals:
        return EvidenceStatus.NOT_YET_DUE, (
            f"Medical records will be critical — severity signals: "
            f"{'; '.join(severity_signals)}."
        )
    return EvidenceStatus.NOT_YET_DUE, "Injury described; medical records should be requested."


# Map evidence IDs to special-case checkers. Items not in this map use
# the default elapsed-time logic.
_SPECIAL_CHECKS: dict[str, callable] = {
    "policy_verification": _check_policy_verification,
    "police_fire_report": _check_police_fire_report,
    "witness_statements": _check_witness_statements,
    "surveillance_footage": _check_surveillance,
    "medical_records": _check_medical_records,
    "medical_bills": _check_medical_records,  # same gating as records
    "lease_ownership_proof": _check_lease_ownership,
    "manufacturer_notice": _check_manufacturer_notice,
}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def generate_checklist(
    record: ClaimRecord,
    as_of_date: Optional[date] = None,
) -> EvidenceChecklist:
    """Generate the evidence checklist for a parsed ACORD claim record.

    Args:
        record: Parsed ClaimRecord from the ACORD parser.
        as_of_date: The date to compute elapsed days from. Defaults to today.

    Returns:
        EvidenceChecklist with status assigned to each applicable item.
    """
    if as_of_date is None:
        as_of_date = date.today()

    elapsed: Optional[int] = None
    if record.date_of_loss:
        elapsed = (as_of_date - record.date_of_loss).days
        if elapsed < 0:
            elapsed = 0  # future loss date — treat as day 0

    # Determine which categories apply
    lt = record.liability_type
    applicable_categories = {EvidenceCategory.BOTH}
    if lt in (LiabilityType.PREMISES, LiabilityType.BOTH):
        applicable_categories.add(EvidenceCategory.PREMISES)
    if lt in (LiabilityType.PRODUCTS, LiabilityType.BOTH):
        applicable_categories.add(EvidenceCategory.PRODUCTS)

    checklist = EvidenceChecklist(
        claim_fingerprint=record.claim_fingerprint,
        liability_type=record.liability_type,
        elapsed_days=elapsed,
    )

    if lt == LiabilityType.UNKNOWN:
        checklist.generation_notes.append(
            "WARNING: liability_type is unknown — applying universal checklist only. "
            "Premises and products items excluded until liability type is determined."
        )

    for (eid, label, cat, priority, expected_day, desc) in _EVIDENCE_CATALOG:
        # Skip items that don't apply to this liability type
        if cat not in applicable_categories:
            continue

        item = EvidenceItem(
            id=eid,
            label=label,
            category=cat,
            priority=priority,
            expected_by_day=expected_day,
            description=desc,
        )

        # Special-case checkers (items we can partially evaluate from the ACORD)
        if eid in _SPECIAL_CHECKS:
            item.status, item.status_reason = _SPECIAL_CHECKS[eid](record)
        else:
            # Default: time-based status
            if elapsed is not None and elapsed > expected_day:
                item.status = EvidenceStatus.MISSING
                item.status_reason = (
                    f"Day {elapsed} of claim — expected by day {expected_day}. "
                    f"Not yet confirmed as present."
                )
            else:
                item.status = EvidenceStatus.NOT_YET_DUE
                if elapsed is not None:
                    item.status_reason = (
                        f"Day {elapsed} of claim — typically expected by day {expected_day}."
                    )
                else:
                    item.status_reason = (
                        f"Date of loss unknown — cannot compute timing. "
                        f"Typically expected by day {expected_day}."
                    )

        checklist.items.append(item)

    return checklist
