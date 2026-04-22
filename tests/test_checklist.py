"""
Day 2 test harness — Evidence Checklist Engine.

Runs all 5 scenarios through the checklist and prints:
  - Summary stats (present / missing / not yet due / total)
  - Every checklist item with its status and reason
  - Specific scenario invariants (e.g., S3 should flag missing policy)

Run: python -m tests.test_checklist
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.acord_parser import parse_acord
from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist

logging.basicConfig(level=logging.WARNING)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Status symbols for readability
_SYMBOLS = {
    EvidenceStatus.PRESENT: "\u2705",         # ✅
    EvidenceStatus.MISSING: "\u274c",         # ❌
    EvidenceStatus.NOT_YET_DUE: "\u23f3",    # ⏳
    EvidenceStatus.NOT_APPLICABLE: "\u2014",  # —
}

# Use a fixed "as_of" date so results are reproducible regardless of when
# you run this. Set to April 16, 2026 (the date we're building this).
AS_OF = date(2026, 4, 16)


def print_checklist(cl: EvidenceChecklist, scenario_label: str) -> None:
    print(f"\n{'=' * 90}")
    print(f" {scenario_label}")
    print(f"{'=' * 90}")
    print(f"  Liability type : {cl.liability_type.value}")
    print(f"  Elapsed days   : {cl.elapsed_days if cl.elapsed_days is not None else 'unknown'}")
    print(f"  Fingerprint    : {cl.claim_fingerprint or 'NONE'}")
    print(f"  Summary        : "
          f"{cl.present_count} present, "
          f"{cl.missing_count} missing, "
          f"{cl.not_yet_due_count} not yet due, "
          f"{cl.applicable_count} applicable")

    if cl.generation_notes:
        print(f"  Notes          :")
        for note in cl.generation_notes:
            print(f"    ! {note}")

    print(f"\n  {'Status':<6} {'Pri':<10} {'By Day':<8} {'Item'}")
    print(f"  {'-' * 84}")
    for item in cl.items:
        sym = _SYMBOLS.get(item.status, "?")
        print(f"  {sym:<6} {item.priority.value:<10} {'d' + str(item.expected_by_day):<8} {item.label}")
        # Print reason indented
        reason_lines = item.status_reason.split(". ")
        for line in reason_lines:
            line = line.strip()
            if line:
                print(f"         {line}.")


def run_scenario_assertions() -> list[str]:
    """Validate specific invariants per scenario."""
    issues: list[str] = []

    # S1: premises/tenant, day 33 — police report should be PRESENT,
    # policy should be PRESENT, surveillance should flag as MISSING (camera mentioned)
    r1 = parse_acord(FIXTURES / "acord_filled_scenario1.pdf")
    cl1 = generate_checklist(r1, as_of_date=AS_OF)

    policy_item = next((i for i in cl1.items if i.id == "policy_verification"), None)
    if not policy_item or policy_item.status != EvidenceStatus.PRESENT:
        issues.append(f"S1: policy_verification should be PRESENT, got {policy_item.status.value if policy_item else 'NOT FOUND'}")

    police_item = next((i for i in cl1.items if i.id == "police_fire_report"), None)
    if not police_item or police_item.status != EvidenceStatus.PRESENT:
        issues.append(f"S1: police_fire_report should be PRESENT, got {police_item.status.value if police_item else 'NOT FOUND'}")

    surv_item = next((i for i in cl1.items if i.id == "surveillance_footage"), None)
    if not surv_item or surv_item.status != EvidenceStatus.MISSING:
        issues.append(f"S1: surveillance_footage should be MISSING (camera mentioned in desc), got {surv_item.status.value if surv_item else 'NOT FOUND'}")

    # S2: products/manufacturer — manufacturer_notice should be NOT_APPLICABLE
    r2 = parse_acord(FIXTURES / "acord_filled_scenario2.pdf")
    cl2 = generate_checklist(r2, as_of_date=AS_OF)

    mfr_notice = next((i for i in cl2.items if i.id == "manufacturer_notice"), None)
    if not mfr_notice or mfr_notice.status != EvidenceStatus.NOT_APPLICABLE:
        issues.append(f"S2: manufacturer_notice should be NOT_APPLICABLE (insured is manufacturer), got {mfr_notice.status.value if mfr_notice else 'NOT FOUND'}")

    # S3: premises/owner, MISSING policy number — policy_verification must be MISSING
    r3 = parse_acord(FIXTURES / "acord_filled_scenario3.pdf")
    cl3 = generate_checklist(r3, as_of_date=AS_OF)

    policy3 = next((i for i in cl3.items if i.id == "policy_verification"), None)
    if not policy3 or policy3.status != EvidenceStatus.MISSING:
        issues.append(f"S3: policy_verification should be MISSING (no policy/carrier on ACORD), got {policy3.status.value if policy3 else 'NOT FOUND'}")

    police3 = next((i for i in cl3.items if i.id == "police_fire_report"), None)
    if not police3 or police3.status != EvidenceStatus.NOT_YET_DUE:
        issues.append(f"S3: police_fire_report should be NOT_YET_DUE (no authority contacted), got {police3.status.value if police3 else 'NOT FOUND'}")

    # S4: products/vendor — manufacturer_notice should NOT be NOT_APPLICABLE
    r4 = parse_acord(FIXTURES / "acord_filled_scenario4.pdf")
    cl4 = generate_checklist(r4, as_of_date=AS_OF)

    mfr4 = next((i for i in cl4.items if i.id == "manufacturer_notice"), None)
    if not mfr4 or mfr4.status == EvidenceStatus.NOT_APPLICABLE:
        issues.append(f"S4: manufacturer_notice should apply (insured is vendor), got {mfr4.status.value if mfr4 else 'NOT FOUND'}")

    # S5: premises/tenant, both BI + property damage — property damage items should be relevant
    r5 = parse_acord(FIXTURES / "acord_filled_scenario5.pdf")
    cl5 = generate_checklist(r5, as_of_date=AS_OF)

    # Verify we have premises-specific items
    premises_items = [i for i in cl5.items if i.category.value == "premises"]
    if len(premises_items) == 0:
        issues.append("S5: no premises-specific items generated")

    return issues


def main() -> int:
    print("\nClaimCompass Day 2 — Evidence Checklist Test Harness")
    print(f"As-of date: {AS_OF} (fixed for reproducibility)\n")

    scenario_labels = {
        1: "S1: Premises slip-and-fall, tenant, 2 witnesses, police report (day 33)",
        2: "S2: Products/manufacturer, serious burn, attorney involved (day 14)",
        3: "S3: Premises/owner, MISSING policy, no police, 21-day gap (day 25)",
        4: "S4: Products/vendor, minor injury, no witnesses, no police (day 13)",
        5: "S5: Premises/tenant, BI + property damage, 3 witnesses (day 2)",
    }

    for i in range(1, 6):
        pdf = FIXTURES / f"acord_filled_scenario{i}.pdf"
        record = parse_acord(pdf)
        cl = generate_checklist(record, as_of_date=AS_OF)
        print_checklist(cl, scenario_labels[i])

    print(f"\n{'=' * 90}")
    print(" Assertions")
    print("=" * 90)
    issues = run_scenario_assertions()
    if not issues:
        print("  [PASS] All scenario-specific invariants hold.")
    else:
        for issue in issues:
            print(f"  [FAIL] {issue}")

    print("=" * 90)
    all_passed = len(issues) == 0
    print(f"\nDay 2 sign-off: {'READY' if all_passed else 'BLOCKED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
