"""
Day 1 test harness.

Runs the ACORD parser against two inputs:
  1. The blank ACORD Form 3 (as uploaded) — expect mostly-null
  2. A synthetic filled ACORD (Demo Scenario 1) — expect full extraction

Prints a side-by-side report so a reviewer can see at a glance that:
  - The blank form does NOT hallucinate values
  - The filled form extracts cleanly into the 26-field schema
  - Both runs log which extraction path was taken

Run: python -m tests.test_parser
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.acord_parser import parse_acord
from app.schemas import ClaimRecord

# Reduce pypdf's chatty warnings about PDF structure — they aren't errors.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("pypdf").setLevel(logging.ERROR)


REPO_ROOT = Path(__file__).resolve().parent.parent
BLANK_PDF = Path(r"C:\Users\revan\OneDrive - UNT System\CLAIMCOMPASS\acord-form-3-liability-notice-of-occurence.pdf")
FILLED_PDF = REPO_ROOT / "fixtures" / "acord_filled_scenario1.pdf"

# Total core fields in ClaimRecord.populated_field_count().
TOTAL_CORE_FIELDS = 26


# ---- Reporting helpers ------------------------------------------------------

def _fmt_value(value) -> str:
    if value is None:
        return "—"
    s = str(value)
    if len(s) > 70:
        s = s[:67] + "..."
    return s


def print_report(record: ClaimRecord, label: str) -> None:
    print(f"\n{'=' * 78}")
    print(f" {label}")
    print("=" * 78)
    print(f"Extraction path : {record.extraction_path.value}")
    print(f"Fingerprint     : {record.claim_fingerprint or '— (insufficient inputs)'}")
    print(f"Populated fields: {record.populated_field_count()} / {TOTAL_CORE_FIELDS}")
    print("-" * 78)

    rows: list[tuple[str, object]] = [
        ("form_completion_date", record.form_completion_date),
        ("date_of_loss", record.date_of_loss),
        ("time_of_loss", record.time_of_loss),
        ("policy_number", record.policy_number),
        ("carrier_name", record.carrier_name),
        ("carrier_naic_code", record.carrier_naic_code),
        ("insured_location_code", record.insured_location_code),
        ("liability_type", record.liability_type.value),
        ("premises_role", record.premises_role.value),
        ("premises_type", record.premises_type),
        ("products_role", record.products_role.value),
        ("product_description", record.product_description),
        ("product_viewable_location", record.product_viewable_location),
        ("insured_name", record.insured_name),
        ("property_owner_name", record.property_owner_name),
        ("product_manufacturer_name", record.product_manufacturer_name),
        ("loss_location_city", record.loss_location_city),
        ("loss_location_state", record.loss_location_state),
        ("loss_location_description", record.loss_location_description),
        ("loss_description", record.loss_description),
        ("authority_contacted.name", record.authority_contacted.authority_name),
        ("authority_contacted.report_number", record.authority_contacted.report_number),
        ("injured_party.full_name", record.injured_party.full_name),
        ("injured_party.age", record.injured_party.age),
        ("injured_party.occupation", record.injured_party.occupation),
        ("injured_party.injury_description", record.injured_party.injury_description),
        ("injured_party.treatment_location", record.injured_party.treatment_location),
        ("property_damage.description", record.property_damage.description),
        ("property_damage.estimated_amount", record.property_damage.estimated_amount),
        ("witness_count", record.witness_count),
    ]
    for name, value in rows:
        print(f"  {name:<42} {_fmt_value(value)}")


# ---- Assertions -------------------------------------------------------------

def assert_blank_is_mostly_null(record: ClaimRecord) -> list[str]:
    """The blank form should populate almost nothing. Returns list of issues."""
    issues = []
    populated = record.populated_field_count()
    # A few fields may legitimately be nonzero on the blank (none expected, but
    # if a checkbox default is 'Off' it could be caught by the enum logic).
    # We assert a strict ceiling here.
    if populated > 2:
        issues.append(
            f"Blank form populated {populated} fields — expected 0–2. "
            f"Parser may be hallucinating."
        )
    if record.claim_fingerprint is not None:
        issues.append(
            f"Blank form produced a fingerprint ({record.claim_fingerprint}) — "
            f"expected None (sparse input guard should block this)."
        )
    return issues


def assert_filled_is_populated(record: ClaimRecord) -> list[str]:
    """The filled form should populate the vast majority of fields."""
    issues = []
    populated = record.populated_field_count()
    if populated < 20:
        issues.append(
            f"Filled form only populated {populated}/{TOTAL_CORE_FIELDS} fields — "
            f"expected at least 20."
        )
    if record.claim_fingerprint is None:
        issues.append("Filled form produced no fingerprint — check name/date/policy.")

    # Scenario-specific invariants (Demo Scenario 1):
    if record.liability_type.value != "premises":
        issues.append(f"Expected liability_type=premises, got {record.liability_type.value}")
    if record.premises_role.value != "tenant":
        issues.append(f"Expected premises_role=tenant, got {record.premises_role.value}")
    if record.witness_count != 2:
        issues.append(f"Expected witness_count=2, got {record.witness_count}")
    if not record.property_owner_name:
        issues.append("Expected property_owner_name to be populated (insured is tenant)")
    if not record.authority_contacted.report_number:
        issues.append("Expected police report number to be populated")
    if record.injured_party.age != 52:
        issues.append(f"Expected injured_party.age=52, got {record.injured_party.age}")

    # The reporting-gap signal: loss on 3/14, reported 3/28 → 14 days
    if record.date_of_loss and record.form_completion_date:
        gap = (record.form_completion_date - record.date_of_loss).days
        if gap != 14:
            issues.append(f"Expected 14-day reporting gap, got {gap}")
    else:
        issues.append("Cannot verify reporting gap — dates missing")

    return issues


# ---- Main -------------------------------------------------------------------

def main() -> int:
    print("\nClaimCompass Day 1 — ACORD parser test harness")

    if not BLANK_PDF.exists():
        print(f"ERROR: Blank ACORD missing at {BLANK_PDF}")
        return 1
    if not FILLED_PDF.exists():
        print(f"ERROR: Filled ACORD missing at {FILLED_PDF}. "
              f"Run: python -m tests.generate_synthetic_acord")
        return 1

    blank_record = parse_acord(BLANK_PDF)
    filled_record = parse_acord(FILLED_PDF)

    print_report(blank_record, "RUN 1: Blank ACORD (negative test — expect ~null)")
    print_report(filled_record, "RUN 2: Filled ACORD, Scenario 1 (positive test)")

    print(f"\n{'=' * 78}")
    print(" Assertions")
    print("=" * 78)
    blank_issues = assert_blank_is_mostly_null(blank_record)
    filled_issues = assert_filled_is_populated(filled_record)

    if not blank_issues:
        print("  [PASS] Blank form: no hallucination, no fingerprint on sparse input.")
    else:
        print("  [FAIL] Blank form:")
        for issue in blank_issues:
            print(f"         - {issue}")

    if not filled_issues:
        print("  [PASS] Filled form: all Scenario 1 invariants hold.")
    else:
        print("  [FAIL] Filled form:")
        for issue in filled_issues:
            print(f"         - {issue}")

    print("=" * 78)
    all_passed = not (blank_issues or filled_issues)
    print(f"\nDay 1 sign-off: {'READY' if all_passed else 'BLOCKED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
