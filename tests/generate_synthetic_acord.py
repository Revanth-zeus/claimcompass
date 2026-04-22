"""
Generate a synthetic filled ACORD Form 3 for testing and Day 6 demo use.

Scenario: Demo Scenario 1 from the 7-day plan.
  - Insured: mid-size commercial restaurant chain (tenant, not owner)
  - Liability: premises — slip-and-fall
  - Injured: 52-year-old customer, taken to ER
  - 2 witnesses, police report filed
  - Date of loss: 14 days before form completion (reporting-gap signal)

This scenario is deliberately designed to exercise:
  - The tenant branch (forces property_owner_name to populate)
  - Non-zero witness_count (contestability signal)
  - Authority-contacted populated (police report on file)
  - Treatment location = ER (severity signal for state classifier)
  - A 14-day reporting gap (later feeds trajectory deviation logic)

Usage:
    python -m tests.generate_synthetic_acord

Writes to fixtures/acord_filled_scenario1.pdf.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

# ACORD 3 (2019/09) checkboxes all use "/1" as the on-state. Values we write
# as NameObject("/1") are recognized on read; plain "1" strings are not and
# end up stored as "/Off". List comes from inspection of the form's /AP dicts.
_CHECKBOX_SHORT_NAMES = {
    "Loss_IncidentTimeAMIndicator_A",
    "Loss_IncidentTimePMIndicator_A",
    "LossProperty_InsuredInterest_OwnerIndicator_A",
    "LossProperty_InsuredInterest_TenantIndicator_A",
    "LossProperty_InsuredInterest_OtherIndicator_A",
    "LossProduct_InsuredInterest_ManufacturerIndicator_A",
    "LossProduct_InsuredInterest_VendorIndicator_A",
    "LossProduct_InsuredInterest_OtherIndicator_A",
    "LossContact_ContactInsuredIndicator_A",
}

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
BLANK_PDF = Path(r"C:\Users\revan\OneDrive - UNT System\CLAIMCOMPASS\acord-form-3-liability-notice-of-occurence.pdf")
OUTPUT_PDF = REPO_ROOT / "fixtures" / "acord_filled_scenario1.pdf"


# The fields below use the short suffix names; we build a fully-qualified
# mapping against the blank form's actual field names at fill time. This
# mirrors how the parser looks up fields and keeps the two files in sync.
SHORT_NAME_VALUES: dict[str, str] = {
    # --- Identity / timing ---
    "Form_CompletionDate_A":          "03/28/2026",
    "Loss_IncidentDate_A":            "03/14/2026",    # 14 days before completion
    "Loss_IncidentTime_A":            "12:45",
    "Loss_IncidentTimePMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "CGL-884471-02",
    "Insurer_FullName_A":             "Continental Guaranty Insurance Company",
    "Insurer_NAICCode_A":             "28258",
    "Loss_InsuredLocationCode_A":     "LOC-047",       # scheduled location 47

    # --- Named insured (restaurant chain, tenant) ---
    "NamedInsured_FullName_A":        "Maplewood Kitchen Group, LLC",
    "NamedInsured_MailingAddress_LineOne_A": "2200 Industrial Blvd",
    "NamedInsured_MailingAddress_CityName_A": "Nashville",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "37210",

    # --- Liability branch: premises, tenant ---
    "LossProperty_InsuredInterest_TenantIndicator_A": "1",
    "LossProperty_PremisesDescription_A": "Casual-dining restaurant, customer seating area",

    # --- Property owner (populated because insured is tenant) ---
    "LossPropertyOwner_FullName_A":   "Harpeth Commercial Realty Trust",
    "LossPropertyOwner_MailingAddress_LineOne_A": "101 Broadway, Suite 400",
    "LossPropertyOwner_MailingAddress_CityName_A": "Nashville",
    "LossPropertyOwner_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossPropertyOwner_MailingAddress_PostalCode_A": "37203",

    # --- Occurrence location + description ---
    "LossLocation_PhysicalAddress_LineOne_A": "4812 Charlotte Pike",
    "LossLocation_PhysicalAddress_CityName_A": "Nashville",
    "LossLocation_PhysicalAddress_StateOrProvinceCode_A": "TN",
    "LossLocation_PhysicalAddress_PostalCode_A": "37209",
    "LossLocation_LocationDescription_A": "Main dining room, near entrance to restrooms",
    "Loss_LossDescription_A": (
        "Claimant, a customer, slipped on a wet floor near the restroom corridor "
        "at approximately 12:45 PM. Staff had mopped the area approximately ten "
        "minutes prior; a wet-floor sign was reportedly in place at one end of the "
        "corridor but not the other. Claimant fell onto right hip and elbow, was "
        "unable to stand without assistance, and was transported by ambulance to "
        "St. Thomas West ER. Incident captured on interior surveillance camera."
    ),
    "Loss_AuthorityContactedName_A":  "Metro Nashville Police Department",
    "Loss_ReportIdentifier_A":        "MNPD-2026-031447",

    # --- Injured party ---
    "LossInjuredParty_FullName_A":    "Patricia A. Reyes",
    "LossInjuredParty_Age_A":         "52",
    "LossInjuredParty_Occupation_A":  "Registered Nurse",
    "LossInjuredParty_ActivitiesDescription_A": "Walking from dining table to restroom",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Possible right hip fracture, soft-tissue injury to right elbow, "
        "contusions. Transported by EMS; admitted for evaluation."
    ),
    "LossInjuredParty_TakenToDescription_A": "St. Thomas West Hospital Emergency Department",

    # --- Witnesses (2 slots filled; slot C left blank) ---
    "LossWitness_FullName_A":         "Derek J. Monroe",
    "LossWitness_MailingAddress_LineOne_A": "918 18th Ave S",
    "LossWitness_MailingAddress_CityName_A": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_A": "TN",

    "LossWitness_FullName_B":         "Ana-Maria Kovacs",
    "LossWitness_MailingAddress_LineOne_B": "2310 Blair Blvd",
    "LossWitness_MailingAddress_CityName_B": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_B": "TN",

    # --- Reported by / to ---
    "Loss_ReportedByName_A":          "Jenna Park (Shift Manager)",
    "Loss_ReportedToName_A":          "911 / MNPD dispatch",

    # --- Producer / broker ---
    "Producer_FullName_A":            "Riverline Insurance Brokers, Inc.",
    "Producer_ContactPerson_FullName_A": "Marcus T. Bell",
    "Producer_ContactPerson_PhoneNumber_A": "(615) 555-0142",
    "Producer_ContactPerson_EmailAddress_A": "mbell@riverlinebrokers.example",
}


def _build_full_name_map(reader: PdfReader) -> dict[str, str]:
    """Match each short-name value to its fully-qualified field name in the PDF."""
    all_fields = reader.get_fields() or {}
    full_map: dict[str, str] = {}
    missing: list[str] = []
    for short_name in SHORT_NAME_VALUES:
        target_suffix = f".{short_name}[0]"
        matched = None
        for full_name in all_fields:
            if full_name.endswith(target_suffix):
                matched = full_name
                break
        if matched:
            value = SHORT_NAME_VALUES[short_name]
            # Checkboxes require NameObject("/1"), not the string "1".
            if short_name in _CHECKBOX_SHORT_NAMES:
                value = NameObject("/1")
            full_map[matched] = value
        else:
            missing.append(short_name)
    if missing:
        print(f"WARNING: {len(missing)} short-name fields had no match:")
        for name in missing:
            print(f"  - {name}")
    return full_map


def main() -> None:
    if not BLANK_PDF.exists():
        raise FileNotFoundError(f"Blank ACORD not found at {BLANK_PDF}")
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(BLANK_PDF))
    writer = PdfWriter(clone_from=reader)

    full_map = _build_full_name_map(reader)
    print(f"Filling {len(full_map)} fields...")

    # pypdf's update_page_form_field_values wants the dict keyed the way the
    # page knows the fields. We pass the fully-qualified names we built above.
    for page in writer.pages:
        writer.update_page_form_field_values(page, full_map)

    with open(OUTPUT_PDF, "wb") as f:
        writer.write(f)
    print(f"Wrote {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
