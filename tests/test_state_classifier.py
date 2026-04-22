"""
Day 4 test harness — Claim State Classifier + Evidence Chain.

Simulates Scenario 1 (Maplewood Kitchen slip-and-fall) progressing through
claim lifecycle stages as documents arrive:

  1. ACORD uploaded → state = INTAKE
  2. Police report arrives → still INTAKE (day 33, but just ACORD + police isn't enough for Investigation since police was already present)
  3. Medical authorization arrives → checklist updates
  4. Witness statement arrives → state → INVESTIGATION (investigative docs present + elapsed ≥ 3)
  5. Attorney letter arrives → state → NEGOTIATION (attorney present + elapsed ≥ 30)

Each transition is logged to the evidence chain with full provenance:
what doc triggered it, what checklist items changed, which rule fired.

Run: python -m tests.test_state_classifier
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.acord_parser import parse_acord
from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
from app.classifier import classify_document, process_document, ClassificationResult
from app.evidence_chain import EvidenceChain
from app.state_classifier import classify_state, ClaimState, build_state_transition

logging.basicConfig(level=logging.WARNING)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FOLLOWUPS = FIXTURES / "followups_s1"
AS_OF = date(2026, 4, 16)

_STATE_SYMBOLS = {
    "INTAKE": "📥",
    "INVESTIGATION": "🔍",
    "RESERVE_SETTING": "💰",
    "NEGOTIATION": "🤝",
    "LITIGATION_TRACK": "⚖️",
    "RESOLUTION": "✅",
}


def main() -> int:
    print("\nClaimCompass Day 4 — State Classifier + Evidence Chain Test Harness")
    print(f"As-of date: {AS_OF}")
    print(f"{'=' * 85}\n")

    # ── Step 1: Parse ACORD and initial state ──
    print("Step 1: Parse ACORD Form 3 (Scenario 1 — Maplewood Kitchen)")
    record = parse_acord(FIXTURES / "acord_filled_scenario1.pdf")
    checklist = generate_checklist(record, as_of_date=AS_OF)
    chain = EvidenceChain(claim_fingerprint=record.claim_fingerprint)

    initial_state = classify_state(record, checklist)
    # Log the initial ACORD as the first evidence chain entry
    from app.evidence_chain import EvidenceChainEntry
    initial_entry = EvidenceChainEntry(
        timestamp=datetime.now(),
        trigger_document="acord_filled_scenario1.pdf",
        trigger_doc_type="acord_form_3",
        trigger_confidence="high",
        state_transition=build_state_transition(None, initial_state),
    )
    chain.add_entry(initial_entry)

    sym = _STATE_SYMBOLS.get(initial_state.state.value, "")
    print(f"  → Initial state: {sym} {initial_state.state.value}")
    print(f"  → Present: {checklist.present_count} | Missing: {checklist.missing_count}")
    initial_state.print_report()

    # ── Step 2: Feed follow-up documents one by one ──
    doc_sequence = [
        "medical_authorization_reyes.txt",
        "witness_statement_monroe.txt",
        "attorney_letter_benton_graves.txt",
    ]

    print(f"\n{'=' * 85}")
    print(f" Step 2: Process follow-up documents sequentially")
    print(f"{'=' * 85}")

    for doc_name in doc_sequence:
        doc_path = FOLLOWUPS / doc_name
        print(f"\n{'─' * 85}")
        print(f" Processing: {doc_name}")
        print(f"{'─' * 85}")

        old_state = chain.current_state or initial_state.state.value
        result = process_document(
            doc_path, record, checklist, chain
        )

        new_state_result = classify_state(record, checklist)
        new_state = new_state_result.state.value
        sym = _STATE_SYMBOLS.get(new_state, "")

        print(f"  Classified as: {result.doc_type.value} ({result.confidence})")
        print(f"  Checklist now: {checklist.present_count} present, {checklist.missing_count} missing")
        print(f"  State: {old_state} → {sym} {new_state}")

        if old_state != new_state:
            print(f"  *** STATE TRANSITION ***")
            print(f"  Rule: {new_state_result.rule_result.rule_name}")
            print(f"  Why : {new_state_result.rule_result.reason}")

    # ── Step 3: Print full evidence chain ──
    print(f"\n{'=' * 85}")
    print(f" Step 3: Full Evidence Chain")
    print(f"{'=' * 85}")
    chain.print_chain()

    # ── Step 4: Final state report with trajectory signals ──
    print(f"\n{'=' * 85}")
    print(f" Step 4: Final State Report")
    print(f"{'=' * 85}")
    final_state = classify_state(record, checklist)
    final_state.print_report()

    # ── Step 5: Run all 5 scenarios for state classification ──
    print(f"\n{'=' * 85}")
    print(f" Step 5: State Classification — All 5 Scenarios")
    print(f"{'=' * 85}")

    scenario_labels = {
        1: "Premises/tenant, 2 witnesses (day 33)",
        2: "Products/manufacturer, burn (day 14)",
        3: "Premises/owner, MISSING policy (day 25)",
        4: "Products/vendor, minor (day 13)",
        5: "Premises/tenant, BI+PD (day 2)",
    }

    for i in range(1, 6):
        r = parse_acord(FIXTURES / f"acord_filled_scenario{i}.pdf")
        cl = generate_checklist(r, as_of_date=AS_OF)
        sc = classify_state(r, cl)
        sym = _STATE_SYMBOLS.get(sc.state.value, "")
        signals = f" | signals: {len(sc.trajectory_signals)}" if sc.trajectory_signals else ""
        print(f"  S{i}: {sym} {sc.state.value:<20} | {scenario_labels[i]}{signals}")
        if sc.trajectory_signals:
            for sig in sc.trajectory_signals:
                print(f"        ⚠ {sig[:90]}")

    # ── Assertions ──
    print(f"\n{'=' * 85}")
    print(f" Assertions")
    print(f"{'=' * 85}")
    issues: list[str] = []

    # S1 with follow-up docs should be in NEGOTIATION (attorney present + elapsed 33 ≥ 30)
    if final_state.state != ClaimState.NEGOTIATION:
        issues.append(f"S1 with attorney letter: expected NEGOTIATION, got {final_state.state.value}")

    # Evidence chain should have 4 entries (ACORD + 3 follow-ups)
    if len(chain.entries) != 4:
        issues.append(f"Expected 4 evidence chain entries, got {len(chain.entries)}")

    # At least one state transition should have occurred
    transitions = [e for e in chain.entries if e.state_transition]
    if len(transitions) < 2:
        issues.append(f"Expected at least 2 state transitions, got {len(transitions)}")

    # Initial state should be INVESTIGATION (S1 has police report present from ACORD + day 33)
    if initial_state.state != ClaimState.INVESTIGATION:
        issues.append(f"Initial state should be INVESTIGATION (police present + day 33), got {initial_state.state.value}")

    # All 5 scenarios base state checks
    for i in range(1, 6):
        r = parse_acord(FIXTURES / f"acord_filled_scenario{i}.pdf")
        cl = generate_checklist(r, as_of_date=AS_OF)
        sc = classify_state(r, cl)
        # S5 (day 2, fresh) should be INTAKE
        if i == 5 and sc.state != ClaimState.INTAKE:
            issues.append(f"S5 (day 2, no follow-ups) should be INTAKE, got {sc.state.value}")
        # S3 should have trajectory signal about missing policy
        if i == 3:
            policy_signal = any("coverage" in s.lower() or "policy" in s.lower() for s in sc.trajectory_signals)
            if not policy_signal:
                issues.append("S3 should have trajectory signal about missing policy")

    if not issues:
        print("  [PASS] All state classifier and evidence chain assertions hold.")
    else:
        for issue in issues:
            print(f"  [FAIL] {issue}")

    print(f"{'=' * 85}")
    all_passed = len(issues) == 0
    print(f"\nDay 4 sign-off: {'READY' if all_passed else 'BLOCKED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
