"""
Day 3 test harness — Document Classifier + Checklist Auto-Checkoff.

Flow:
  1. Parse Scenario 1 ACORD → generate checklist (before state)
  2. Classify each follow-up document
  3. Apply each classification to the checklist
  4. Print before/after comparison
  5. Assert specific items flipped status

Run: python -m tests.test_classifier
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.acord_parser import parse_acord
from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
from app.classifier import (
    ClassificationResult,
    DocType,
    classify_document,
    apply_document_to_checklist,
)

logging.basicConfig(level=logging.WARNING)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FOLLOWUPS = FIXTURES / "followups_s1"
AS_OF = date(2026, 4, 16)

_SYMBOLS = {
    EvidenceStatus.PRESENT: "\u2705",
    EvidenceStatus.MISSING: "\u274c",
    EvidenceStatus.NOT_YET_DUE: "\u23f3",
    EvidenceStatus.NOT_APPLICABLE: "\u2014",
}


def print_classification(result: ClassificationResult, filename: str) -> None:
    print(f"\n  [{filename}]")
    print(f"    Type       : {result.doc_type.value}")
    print(f"    Confidence : {result.confidence}")
    print(f"    Path       : {result.classification_path.value}")
    if result.matched_keywords:
        print(f"    Keywords   : {result.matched_keywords}")
    if result.checklist_items_satisfied:
        print(f"    Satisfies  : {result.checklist_items_satisfied}")
    if result.extracted_entities:
        for k, v in result.extracted_entities.items():
            print(f"    Entity     : {k} = {v}")
    if result.notes:
        for note in result.notes:
            print(f"    Note       : {note}")


def print_checklist_summary(cl: EvidenceChecklist, label: str) -> None:
    print(f"\n  {label}")
    print(f"  {'─' * 76}")
    for item in cl.items:
        if item.status == EvidenceStatus.NOT_APPLICABLE:
            continue
        sym = _SYMBOLS.get(item.status, "?")
        print(f"    {sym} {item.label}")


def main() -> int:
    print("\nClaimCompass Day 3 — Document Classifier + Auto-Checkoff Test Harness")
    print(f"As-of date: {AS_OF}\n")

    # Step 1: Parse S1 and generate checklist (before state)
    record = parse_acord(FIXTURES / "acord_filled_scenario1.pdf")
    checklist = generate_checklist(record, as_of_date=AS_OF)

    before_present = checklist.present_count
    before_missing = checklist.missing_count

    print(f"{'=' * 80}")
    print(f" BEFORE: Checklist state from ACORD only")
    print(f"{'=' * 80}")
    print(f"  Present: {before_present} | Missing: {before_missing} | "
          f"Not Yet Due: {checklist.not_yet_due_count}")
    print_checklist_summary(checklist, "Checklist items:")

    # Step 2: Classify each follow-up doc
    print(f"\n{'=' * 80}")
    print(f" CLASSIFICATION RESULTS")
    print(f"{'=' * 80}")

    followup_files = sorted(FOLLOWUPS.glob("*.txt"))
    classifications: list[tuple[str, ClassificationResult]] = []

    for fp in followup_files:
        result = classify_document(fp)
        classifications.append((fp.name, result))
        print_classification(result, fp.name)

    # Step 3: Apply to checklist
    print(f"\n{'=' * 80}")
    print(f" APPLYING DOCUMENTS TO CHECKLIST")
    print(f"{'=' * 80}")

    all_updated: list[str] = []
    for filename, result in classifications:
        updated = apply_document_to_checklist(checklist, result, filename)
        if updated:
            print(f"  {filename} → updated: {updated}")
            all_updated.extend(updated)
        elif result.doc_type != DocType.UNKNOWN and result.checklist_items_satisfied:
            print(f"  {filename} → items already present or N/A")
        else:
            print(f"  {filename} → no checklist items to update")

    # Step 4: After state
    print(f"\n{'=' * 80}")
    print(f" AFTER: Checklist state with follow-up docs applied")
    print(f"{'=' * 80}")
    print(f"  Present: {checklist.present_count} | Missing: {checklist.missing_count} | "
          f"Not Yet Due: {checklist.not_yet_due_count}")
    print(f"  Items updated this round: {len(all_updated)}")
    print_checklist_summary(checklist, "Checklist items:")

    # Step 5: Assertions
    print(f"\n{'=' * 80}")
    print(f" Assertions")
    print(f"{'=' * 80}")
    issues: list[str] = []

    # Classification assertions
    type_map = {fn: r.doc_type for fn, r in classifications}

    if type_map.get("police_report_MNPD-2026-031447.txt") != DocType.POLICE_REPORT:
        issues.append("Police report not classified as POLICE_REPORT")
    if type_map.get("medical_authorization_reyes.txt") != DocType.MEDICAL_AUTHORIZATION:
        issues.append("Medical auth not classified as MEDICAL_AUTHORIZATION")
    if type_map.get("witness_statement_monroe.txt") != DocType.WITNESS_STATEMENT:
        issues.append("Witness statement not classified as WITNESS_STATEMENT")
    if type_map.get("attorney_letter_benton_graves.txt") != DocType.ATTORNEY_LETTER:
        issues.append("Attorney letter not classified as ATTORNEY_LETTER")
    if type_map.get("repair_estimate_treadmill.txt") != DocType.REPAIR_ESTIMATE:
        issues.append("Repair estimate not classified as REPAIR_ESTIMATE")
    if type_map.get("random_correspondence.txt") != DocType.UNKNOWN:
        issues.append(f"Random email should be UNKNOWN, got {type_map.get('random_correspondence.txt')}")

    # Checklist state assertions
    def _item_status(item_id: str) -> Optional[EvidenceStatus]:
        for item in checklist.items:
            if item.id == item_id:
                return item.status
        return None

    if _item_status("medical_authorization") != EvidenceStatus.PRESENT:
        issues.append("medical_authorization should be PRESENT after doc applied")
    if _item_status("witness_statements") != EvidenceStatus.PRESENT:
        issues.append("witness_statements should be PRESENT after doc applied")
    if _item_status("attorney_letter") != EvidenceStatus.PRESENT:
        issues.append("attorney_letter should be PRESENT after doc applied")

    # Police report was already PRESENT from ACORD — should stay PRESENT
    if _item_status("police_fire_report") != EvidenceStatus.PRESENT:
        issues.append("police_fire_report should still be PRESENT")

    # Present count should have increased
    if checklist.present_count <= before_present:
        issues.append(f"Present count should have increased from {before_present}, "
                      f"got {checklist.present_count}")

    if not issues:
        print("  [PASS] All classification and auto-checkoff assertions hold.")
    else:
        for issue in issues:
            print(f"  [FAIL] {issue}")

    print(f"{'=' * 80}")
    all_passed = len(issues) == 0
    print(f"\nDay 3 sign-off: {'READY' if all_passed else 'BLOCKED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
