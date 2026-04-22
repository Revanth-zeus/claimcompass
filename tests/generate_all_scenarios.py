"""
Generate synthetic filled ACORD Form 3 PDFs for Scenarios 1-5.

Scenario 1: Premises slip-and-fall, tenant, 2 witnesses, police report, 14-day gap (already built)
Scenario 2: Products liability, manufacturer, serious burn injury, attorney involved, 3-day gap
Scenario 3: Premises, owner, missing policy verification signal, 21-day gap, 1 witness
Scenario 4: Products liability, vendor, minor injury, no witnesses, no police, 7-day gap
Scenario 5: Premises, tenant, bodily injury + property damage, 3 witnesses, same-day report

Each scenario exercises different parser branches and will feed different
checklist/state-classifier paths on Days 2-4.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

REPO_ROOT = Path(__file__).resolve().parent.parent
BLANK_PDF = Path(r"C:\Users\revan\OneDrive - UNT System\CLAIMCOMPASS\acord-form-3-liability-notice-of-occurence.pdf")
FIXTURES_DIR = REPO_ROOT / "fixtures"

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


# ============================================================================
# Scenario data
# ============================================================================

SCENARIO_1: dict[str, str] = {
    "Form_CompletionDate_A":          "03/28/2026",
    "Loss_IncidentDate_A":            "03/14/2026",
    "Loss_IncidentTime_A":            "12:45",
    "Loss_IncidentTimePMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "CGL-884471-02",
    "Insurer_FullName_A":             "Continental Guaranty Insurance Company",
    "Insurer_NAICCode_A":             "28258",
    "Loss_InsuredLocationCode_A":     "LOC-047",
    "NamedInsured_FullName_A":        "Maplewood Kitchen Group, LLC",
    "NamedInsured_MailingAddress_LineOne_A": "2200 Industrial Blvd",
    "NamedInsured_MailingAddress_CityName_A": "Nashville",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "37210",
    "LossProperty_InsuredInterest_TenantIndicator_A": "1",
    "LossProperty_PremisesDescription_A": "Casual-dining restaurant, customer seating area",
    "LossPropertyOwner_FullName_A":   "Harpeth Commercial Realty Trust",
    "LossPropertyOwner_MailingAddress_LineOne_A": "101 Broadway, Suite 400",
    "LossPropertyOwner_MailingAddress_CityName_A": "Nashville",
    "LossPropertyOwner_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossPropertyOwner_MailingAddress_PostalCode_A": "37203",
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
    "LossInjuredParty_FullName_A":    "Patricia A. Reyes",
    "LossInjuredParty_Age_A":         "52",
    "LossInjuredParty_Occupation_A":  "Registered Nurse",
    "LossInjuredParty_ActivitiesDescription_A": "Walking from dining table to restroom",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Possible right hip fracture, soft-tissue injury to right elbow, "
        "contusions. Transported by EMS; admitted for evaluation."
    ),
    "LossInjuredParty_TakenToDescription_A": "St. Thomas West Hospital Emergency Department",
    "LossWitness_FullName_A":         "Derek J. Monroe",
    "LossWitness_MailingAddress_LineOne_A": "918 18th Ave S",
    "LossWitness_MailingAddress_CityName_A": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossWitness_FullName_B":         "Ana-Maria Kovacs",
    "LossWitness_MailingAddress_LineOne_B": "2310 Blair Blvd",
    "LossWitness_MailingAddress_CityName_B": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_B": "TN",
    "Loss_ReportedByName_A":          "Jenna Park (Shift Manager)",
    "Loss_ReportedToName_A":          "911 / MNPD dispatch",
    "Producer_FullName_A":            "Riverline Insurance Brokers, Inc.",
    "Producer_ContactPerson_FullName_A": "Marcus T. Bell",
    "Producer_ContactPerson_PhoneNumber_A": "(615) 555-0142",
    "Producer_ContactPerson_EmailAddress_A": "mbell@riverlinebrokers.example",
}


SCENARIO_2: dict[str, str] = {
    # Products liability — manufacturer — serious burn injury — attorney early
    "Form_CompletionDate_A":          "04/05/2026",
    "Loss_IncidentDate_A":            "04/02/2026",       # 3-day gap — fast report
    "Loss_IncidentTime_A":            "09:15",
    "Loss_IncidentTimeAMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "PL-220091-A",
    "Insurer_FullName_A":             "Pinnacle Casualty & Surety Co.",
    "Insurer_NAICCode_A":             "31402",
    "Loss_InsuredLocationCode_A":     "FAC-003",
    "NamedInsured_FullName_A":        "ThermaWeld Industries, Inc.",
    "NamedInsured_MailingAddress_LineOne_A": "780 Commerce Park Dr",
    "NamedInsured_MailingAddress_CityName_A": "Chattanooga",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "37421",
    "LossProduct_InsuredInterest_ManufacturerIndicator_A": "1",
    "LossProduct_ProductDescription_A": "Model TW-340 industrial heat gun, 1800W, batch #2025-11-R7",
    "LossProduct_ViewableLocation_A": "Retained by claimant's attorney — Benton & Graves LLP, 500 Church St Suite 1200, Nashville TN 37219",
    "LossLocation_PhysicalAddress_LineOne_A": "1420 Donelson Pike, Unit 9B",
    "LossLocation_PhysicalAddress_CityName_A": "Nashville",
    "LossLocation_PhysicalAddress_StateOrProvinceCode_A": "TN",
    "LossLocation_PhysicalAddress_PostalCode_A": "37214",
    "LossLocation_LocationDescription_A": "Auto body repair shop, spray booth area",
    "Loss_LossDescription_A": (
        "Claimant was using a ThermaWeld TW-340 heat gun to remove adhesive from "
        "a vehicle panel when the unit allegedly overheated and expelled burning "
        "material from the nozzle. Claimant sustained second-degree burns to left "
        "hand and forearm. Claimant states the unit was purchased new three weeks "
        "prior. No prior incidents reported by claimant. Product has been retained "
        "by claimant's counsel."
    ),
    "Loss_AuthorityContactedName_A":  "Nashville Fire Department",
    "Loss_ReportIdentifier_A":        "NFD-2026-04-0289",
    "LossInjuredParty_FullName_A":    "Raymond K. Osei",
    "LossInjuredParty_Age_A":         "34",
    "LossInjuredParty_Occupation_A":  "Auto Body Technician",
    "LossInjuredParty_ActivitiesDescription_A": "Removing adhesive from vehicle panel using heat gun",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Second-degree burns, left hand and forearm, approximately 8% body "
        "surface area. Treated at Vanderbilt University Medical Center burn unit. "
        "Expected 4-6 week recovery, possible skin graft evaluation pending."
    ),
    "LossInjuredParty_TakenToDescription_A": "Vanderbilt University Medical Center, Burn Unit",
    "LossWitness_FullName_A":         "Tyrone D. Marsh",
    "LossWitness_MailingAddress_LineOne_A": "1420 Donelson Pike, Unit 9B",
    "LossWitness_MailingAddress_CityName_A": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossWitness_FullName_B":         "Lisa M. Pruitt",
    "LossWitness_MailingAddress_LineOne_B": "1420 Donelson Pike, Unit 9A",
    "LossWitness_MailingAddress_CityName_B": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_B": "TN",
    "LossWitness_FullName_C":         "Carlos E. Vega",
    "LossWitness_MailingAddress_LineOne_C": "302 Fesslers Ln",
    "LossWitness_MailingAddress_CityName_C": "Nashville",
    "LossWitness_MailingAddress_StateOrProvinceCode_C": "TN",
    "Loss_ReportedByName_A":          "David Pruitt (Shop Owner)",
    "Loss_ReportedToName_A":          "911 / NFD dispatch",
    "Producer_FullName_A":            "Summit Risk Advisors, LLC",
    "Producer_ContactPerson_FullName_A": "Janet C. Rhodes",
    "Producer_ContactPerson_PhoneNumber_A": "(423) 555-0277",
    "Producer_ContactPerson_EmailAddress_A": "jrhodes@summitrisk.example",
}


SCENARIO_3: dict[str, str] = {
    # Premises — owner — missing policy verification — 21-day gap — 1 witness
    "Form_CompletionDate_A":          "04/12/2026",
    "Loss_IncidentDate_A":            "03/22/2026",       # 21-day gap — late report
    "Loss_IncidentTime_A":            "03:20",
    "Loss_IncidentTimePMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "",                 # MISSING — the whole point of this scenario
    "Insurer_FullName_A":             "",                  # Also missing — forces coverage verification flag
    "Insurer_NAICCode_A":             "",
    "Loss_InsuredLocationCode_A":     "",                  # Missing — can't verify scheduled location
    "NamedInsured_FullName_A":        "Greenbriar Apartments, LP",
    "NamedInsured_MailingAddress_LineOne_A": "P.O. Box 9042",
    "NamedInsured_MailingAddress_CityName_A": "Memphis",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "38109",
    "LossProperty_InsuredInterest_OwnerIndicator_A": "1",
    "LossProperty_PremisesDescription_A": "Multi-unit residential apartment complex, outdoor stairwell",
    "LossLocation_PhysicalAddress_LineOne_A": "3344 Frayser Blvd, Building C",
    "LossLocation_PhysicalAddress_CityName_A": "Memphis",
    "LossLocation_PhysicalAddress_StateOrProvinceCode_A": "TN",
    "LossLocation_PhysicalAddress_PostalCode_A": "38127",
    "LossLocation_LocationDescription_A": "Exterior metal stairwell between 2nd and 3rd floor, Building C",
    "Loss_LossDescription_A": (
        "Tenant reports that the metal railing on the exterior stairwell between "
        "the 2nd and 3rd floors of Building C detached from its mounts while "
        "claimant was descending stairs. Claimant fell approximately 6 feet to "
        "the ground-level concrete pad below. Claimant states the railing had been "
        "reported as loose to management twice in the preceding three months. "
        "Maintenance records have not yet been located."
    ),
    "Loss_AuthorityContactedName_A":  "",                  # No police contacted — another gap
    "Loss_ReportIdentifier_A":        "",
    "LossInjuredParty_FullName_A":    "Marcus D. Whitfield",
    "LossInjuredParty_Age_A":         "41",
    "LossInjuredParty_Occupation_A":  "Warehouse Associate",
    "LossInjuredParty_ActivitiesDescription_A": "Descending exterior stairwell to parking lot",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Fractured left ankle (lateral malleolus), bruised ribs, abrasions to "
        "both palms. Transported by personal vehicle to Regional One Health ER."
    ),
    "LossInjuredParty_TakenToDescription_A": "Regional One Health, Emergency Department",
    "LossWitness_FullName_A":         "Keisha R. Banks",
    "LossWitness_MailingAddress_LineOne_A": "3344 Frayser Blvd, Apt C-312",
    "LossWitness_MailingAddress_CityName_A": "Memphis",
    "LossWitness_MailingAddress_StateOrProvinceCode_A": "TN",
    "Loss_ReportedByName_A":          "Marcus D. Whitfield (Claimant)",
    "Loss_ReportedToName_A":          "Property management office",
    "Producer_FullName_A":            "Delta South Insurance Agency",
    "Producer_ContactPerson_FullName_A": "Ronald Bates",
    "Producer_ContactPerson_PhoneNumber_A": "(901) 555-0188",
    "Producer_ContactPerson_EmailAddress_A": "rbates@deltasouth.example",
}


SCENARIO_4: dict[str, str] = {
    # Products — vendor — minor injury — no witnesses — no police — 7-day gap
    "Form_CompletionDate_A":          "04/10/2026",
    "Loss_IncidentDate_A":            "04/03/2026",       # 7-day gap
    "Loss_IncidentTime_A":            "11:30",
    "Loss_IncidentTimeAMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "CGL-PV-55892",
    "Insurer_FullName_A":             "Southeastern Mutual Insurance Co.",
    "Insurer_NAICCode_A":             "19704",
    "Loss_InsuredLocationCode_A":     "STR-012",
    "NamedInsured_FullName_A":        "Blueridge Hardware & Home, LLC",
    "NamedInsured_MailingAddress_LineOne_A": "608 Main Street",
    "NamedInsured_MailingAddress_CityName_A": "Johnson City",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "37601",
    "LossProduct_InsuredInterest_VendorIndicator_A": "1",
    "LossProduct_ProductDescription_A": "ProGrip 24-ft fiberglass extension ladder, model PG-24F",
    "LossProduct_ViewableLocation_A": "At claimant residence, 210 Oak Hill Dr, Johnson City TN 37604",
    "LossProductManufacturer_FullName_A": "ProGrip Tools International, Ltd.",
    "LossProductManufacturer_MailingAddress_LineOne_A": "Unit 14, Zhongshan Industrial Zone",
    "LossProductManufacturer_MailingAddress_CityName_A": "Guangdong",
    "LossLocation_PhysicalAddress_LineOne_A": "210 Oak Hill Dr",
    "LossLocation_PhysicalAddress_CityName_A": "Johnson City",
    "LossLocation_PhysicalAddress_StateOrProvinceCode_A": "TN",
    "LossLocation_PhysicalAddress_PostalCode_A": "37604",
    "LossLocation_LocationDescription_A": "Claimant's residential property, side of house near garage",
    "Loss_LossDescription_A": (
        "Claimant reports that the locking mechanism on a ProGrip PG-24F "
        "extension ladder failed while claimant was approximately 8 feet up, "
        "cleaning gutters. The upper section slid down and claimant stepped off "
        "the ladder onto the ground. Claimant sustained a sprained right wrist "
        "and minor knee abrasion. No emergency transport required. Ladder was "
        "purchased from insured's store approximately two months prior; claimant "
        "retained receipt."
    ),
    "Loss_AuthorityContactedName_A":  "",                  # No police — minor incident
    "Loss_ReportIdentifier_A":        "",
    "LossInjuredParty_FullName_A":    "Howard S. Nakamura",
    "LossInjuredParty_Age_A":         "67",
    "LossInjuredParty_Occupation_A":  "Retired (former civil engineer)",
    "LossInjuredParty_ActivitiesDescription_A": "Cleaning gutters at personal residence using ladder",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Sprained right wrist, minor abrasion to left knee. Self-treated initially; "
        "visited urgent care the following day for wrist X-ray. No fracture confirmed."
    ),
    "LossInjuredParty_TakenToDescription_A": "Johnson City Urgent Care (next day, 04/04/2026)",
    # No witnesses
    "Loss_ReportedByName_A":          "Howard S. Nakamura (Claimant)",
    "Loss_ReportedToName_A":          "Blueridge Hardware store manager",
    "Producer_FullName_A":            "Appalachian Commercial Insurance Group",
    "Producer_ContactPerson_FullName_A": "Beverly Tran",
    "Producer_ContactPerson_PhoneNumber_A": "(423) 555-0331",
    "Producer_ContactPerson_EmailAddress_A": "btran@appcomins.example",
}


SCENARIO_5: dict[str, str] = {
    # Premises — tenant — bodily injury + property damage — 3 witnesses — same-day report
    "Form_CompletionDate_A":          "04/14/2026",
    "Loss_IncidentDate_A":            "04/14/2026",       # Same day — 0-day gap
    "Loss_IncidentTime_A":            "07:50",
    "Loss_IncidentTimeAMIndicator_A": "1",
    "Policy_PolicyNumberIdentifier_A": "CGL-TN-410228",
    "Insurer_FullName_A":             "National Allied Fire & Casualty Company",
    "Insurer_NAICCode_A":             "10044",
    "Loss_InsuredLocationCode_A":     "LOC-001",
    "NamedInsured_FullName_A":        "Volunteer Fitness Centers, Inc.",
    "NamedInsured_MailingAddress_LineOne_A": "9100 Kingston Pike, Suite 200",
    "NamedInsured_MailingAddress_CityName_A": "Knoxville",
    "NamedInsured_MailingAddress_StateOrProvinceCode_A": "TN",
    "NamedInsured_MailingAddress_PostalCode_A": "37923",
    "LossProperty_InsuredInterest_TenantIndicator_A": "1",
    "LossProperty_PremisesDescription_A": "Commercial fitness center, free-weight area and lobby",
    "LossPropertyOwner_FullName_A":   "Parkside Retail Partners, LLC",
    "LossPropertyOwner_MailingAddress_LineOne_A": "One Market Square, 22nd Floor",
    "LossPropertyOwner_MailingAddress_CityName_A": "Knoxville",
    "LossPropertyOwner_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossPropertyOwner_MailingAddress_PostalCode_A": "37902",
    "LossLocation_PhysicalAddress_LineOne_A": "2740 Merchants Dr",
    "LossLocation_PhysicalAddress_CityName_A": "Knoxville",
    "LossLocation_PhysicalAddress_StateOrProvinceCode_A": "TN",
    "LossLocation_PhysicalAddress_PostalCode_A": "37912",
    "LossLocation_LocationDescription_A": "Ground-floor fitness center, free-weight section near front windows",
    "Loss_LossDescription_A": (
        "A ceiling-mounted HVAC duct bracket failed in the free-weight area at "
        "approximately 7:50 AM, causing a 12-foot section of exposed ductwork to "
        "fall. The duct struck a member who was using the bench press and also "
        "damaged two commercial treadmills and shattered the front plate-glass "
        "window. Building management had completed an HVAC inspection six months "
        "prior with no deficiencies noted. The fitness center was evacuated; "
        "the area remains closed pending structural assessment."
    ),
    "Loss_AuthorityContactedName_A":  "Knoxville Fire Department",
    "Loss_ReportIdentifier_A":        "KFD-2026-04-1087",
    "LossInjuredParty_FullName_A":    "Steven W. Pham",
    "LossInjuredParty_Age_A":         "28",
    "LossInjuredParty_Occupation_A":  "Software Developer",
    "LossInjuredParty_ActivitiesDescription_A": "Using bench press in free-weight area",
    "LossInjuredParty_ExtentOfInjury_A": (
        "Laceration to forehead (approximately 3 cm, required 8 sutures), "
        "contusion to right shoulder, possible mild concussion. Transported "
        "by EMS to University of Tennessee Medical Center ER."
    ),
    "LossInjuredParty_TakenToDescription_A": "UT Medical Center Emergency Department",
    "LossProperty_PropertyDescription_A": (
        "Two Precor TRM 885 commercial treadmills (approx. $7,500 each), one "
        "plate-glass storefront window (approx. 8ft x 10ft)"
    ),
    "LossProperty_EstimatedDamageAmount_A": "$19,200",
    "LossWitness_FullName_A":         "Jordan T. McAllister",
    "LossWitness_MailingAddress_LineOne_A": "6200 Baum Dr, Apt 14",
    "LossWitness_MailingAddress_CityName_A": "Knoxville",
    "LossWitness_MailingAddress_StateOrProvinceCode_A": "TN",
    "LossWitness_FullName_B":         "Rebecca L. Huang",
    "LossWitness_MailingAddress_LineOne_B": "1122 Westland Dr",
    "LossWitness_MailingAddress_CityName_B": "Knoxville",
    "LossWitness_MailingAddress_StateOrProvinceCode_B": "TN",
    "LossWitness_FullName_C":         "Nathan A. Brooks",
    "LossWitness_MailingAddress_LineOne_C": "409 Cedar Bluff Rd",
    "LossWitness_MailingAddress_CityName_C": "Knoxville",
    "LossWitness_MailingAddress_StateOrProvinceCode_C": "TN",
    "Loss_ReportedByName_A":          "Alicia Chen (General Manager)",
    "Loss_ReportedToName_A":          "911 / KFD dispatch",
    "Producer_FullName_A":            "East Tennessee Risk Partners, Inc.",
    "Producer_ContactPerson_FullName_A": "William D. Fraser",
    "Producer_ContactPerson_PhoneNumber_A": "(865) 555-0194",
    "Producer_ContactPerson_EmailAddress_A": "wfraser@etriskpartners.example",
}


ALL_SCENARIOS = {
    "acord_filled_scenario1.pdf": SCENARIO_1,
    "acord_filled_scenario2.pdf": SCENARIO_2,
    "acord_filled_scenario3.pdf": SCENARIO_3,
    "acord_filled_scenario4.pdf": SCENARIO_4,
    "acord_filled_scenario5.pdf": SCENARIO_5,
}


def _build_full_name_map(reader: PdfReader, short_values: dict[str, str]) -> dict[str, object]:
    """Match short-name values to fully-qualified field names, coercing checkboxes."""
    all_fields = reader.get_fields() or {}
    full_map: dict[str, object] = {}
    for short_name, value in short_values.items():
        target_suffix = f".{short_name}[0]"
        matched = None
        for full_name in all_fields:
            if full_name.endswith(target_suffix):
                matched = full_name
                break
        if matched:
            if short_name in _CHECKBOX_SHORT_NAMES:
                full_map[matched] = NameObject("/1")
            else:
                full_map[matched] = value
    return full_map


def generate_all() -> None:
    if not BLANK_PDF.exists():
        raise FileNotFoundError(f"Blank ACORD not found at {BLANK_PDF}")
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    for filename, scenario_data in ALL_SCENARIOS.items():
        reader = PdfReader(str(BLANK_PDF))
        writer = PdfWriter(clone_from=reader)
        full_map = _build_full_name_map(reader, scenario_data)

        for page in writer.pages:
            writer.update_page_form_field_values(page, full_map)

        out_path = FIXTURES_DIR / filename
        with open(out_path, "wb") as f:
            writer.write(f)
        print(f"  [{filename}] {len(full_map)} fields filled")

    print(f"\nAll 5 scenarios written to {FIXTURES_DIR}/")


if __name__ == "__main__":
    generate_all()
