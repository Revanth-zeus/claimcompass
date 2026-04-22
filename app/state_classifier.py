"""
ClaimCompass — Claim State Classifier (Day 4).

The opinionation piece: "Where is this claim, and what should happen next?"

6 lifecycle states with explicit boolean rules:
  INTAKE          — only ACORD + 0-2 docs, <7 days
  INVESTIGATION   — police/witness evidence arriving, <30 days
  RESERVE_SETTING — medical records present, damages quantifiable, 30-90 days
  NEGOTIATION     — attorney or settlement demand present, 60-180 days
  LITIGATION_TRACK— lawsuit signals, represented claimant, 90+ days
  RESOLUTION      — release signed, settlement docs present

State classification is DETERMINISTIC and RULE-BASED. Not ML-based.
Rules are derived from document presence + elapsed time + liability type.
Every transition has a receipt in the evidence chain (Trust Anchor 3).

Next actions come from public adjuster training material logic, not
invented benchmarks. Framed as "typical actions at this stage" not
"statistically optimal actions."

Critical constraints (from handoff plan, non-negotiable):
  - No fake statistics
  - No litigation risk percentages
  - Stage classification = explicit boolean rules, fully transparent
  - Frame as augmenting adjusters, not replacing them
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.checklist import EvidenceChecklist, EvidenceStatus
from app.evidence_chain import EvidenceChain, StateTransition
from app.schemas import ClaimRecord, LiabilityType

log = logging.getLogger("claimcompass.state")


# --------------------------------------------------------------------------
# Claim states
# --------------------------------------------------------------------------

class ClaimState(str, Enum):
    INTAKE = "INTAKE"
    INVESTIGATION = "INVESTIGATION"
    RESERVE_SETTING = "RESERVE_SETTING"
    NEGOTIATION = "NEGOTIATION"
    LITIGATION_TRACK = "LITIGATION_TRACK"
    RESOLUTION = "RESOLUTION"


# --------------------------------------------------------------------------
# Next actions per state.
# These are "typical steps at this stage" from public adjuster training
# material and standard CGL claims handling practice. NOT "statistically
# optimal actions." NOT benchmarks. Just what a competent adjuster would
# typically do at each stage.
# --------------------------------------------------------------------------

NEXT_ACTIONS: dict[ClaimState, list[str]] = {
    ClaimState.INTAKE: [
        "Verify coverage — confirm policy is active and loss location/product is within scope",
        "Acknowledge claim receipt to insured and claimant within carrier SLA",
        "Begin first-contact round — insured, claimant, witnesses (aim for ~15 contacts in first 48 hours)",
        "Request police/fire report if authority was contacted",
        "If premises: request photos of loss location immediately (conditions change)",
        "If premises + surveillance mentioned: preserve footage now (systems overwrite in 7-30 days)",
        "If products: identify and preserve the product for inspection",
        "Set initial diary/follow-up date within 7 days",
    ],
    ClaimState.INVESTIGATION: [
        "Obtain and review police/fire report",
        "Complete recorded statements from claimant and all witnesses",
        "Obtain signed medical records authorization (HIPAA release) from claimant",
        "If premises: obtain maintenance/inspection records for the loss location",
        "If premises + tenant: obtain lease agreement to clarify maintenance obligations",
        "If products: arrange product inspection by qualified expert",
        "If products + vendor: notify manufacturer per vendor endorsement terms",
        "If products: check CPSC recall history for the product model",
        "Evaluate liability exposure based on evidence gathered so far",
        "Set follow-up diary at 14-day intervals",
    ],
    ClaimState.RESERVE_SETTING: [
        "Review medical records for injury severity, treatment plan, and prognosis",
        "Obtain itemized medical bills and verify charges",
        "Evaluate policy limits relative to damages exposure",
        "Set initial reserve based on documented damages + allocated loss adjustment expense (ALAE)",
        "If prior injuries or pre-existing conditions noted, request prior medical history",
        "Document reserve rationale with specific reference to medical documentation",
        "Reassess liability position with complete evidence file",
        "Set follow-up diary at 30-day intervals",
    ],
    ClaimState.NEGOTIATION: [
        "Review attorney letter of representation — update all contact to go through counsel",
        "If demand received: evaluate demand against documented damages and policy limits",
        "Prepare counter-offer with itemized rationale tied to evidence on file",
        "Ensure all medical treatment has concluded or reached maximum medical improvement (MMI)",
        "Verify all subrogation interests are identified before settlement",
        "If approaching policy limits: notify insured of potential excess exposure",
        "Document all negotiation communications in claim file",
    ],
    ClaimState.LITIGATION_TRACK: [
        "Forward suit papers to coverage counsel immediately upon receipt",
        "Notify insured of litigation and explain defense obligations under policy",
        "Coordinate with defense counsel on litigation strategy",
        "Prepare litigation budget and update reserves accordingly",
        "Ensure all evidence is preserved and documented for discovery",
        "Monitor litigation milestones — answer deadline, discovery cutoff, trial date",
        "Evaluate mediation or alternative dispute resolution options",
    ],
    ClaimState.RESOLUTION: [
        "Verify release/settlement agreement is properly executed",
        "Confirm all lien holders and subrogation interests are satisfied",
        "Issue settlement payment per agreement terms",
        "Close claim file with final documentation of resolution",
        "Complete any required regulatory reporting",
    ],
}


# --------------------------------------------------------------------------
# State classification rules.
#
# Rules are evaluated in REVERSE order (Resolution first, then Litigation,
# then Negotiation, etc.) so the highest applicable state wins. This is
# because a claim that has a signed release is in Resolution regardless
# of what other documents are present.
#
# Each rule returns: (bool, rule_name, conditions_list, satisfied_list, reason)
# --------------------------------------------------------------------------

def _item_is_present(checklist: EvidenceChecklist, item_id: str) -> bool:
    """Check if a checklist item has status PRESENT."""
    for item in checklist.items:
        if item.id == item_id:
            return item.status == EvidenceStatus.PRESENT
    return False


def _item_exists(checklist: EvidenceChecklist, item_id: str) -> bool:
    """Check if a checklist item exists (applicable to this claim type)."""
    return any(
        item.id == item_id and item.status != EvidenceStatus.NOT_APPLICABLE
        for item in checklist.items
    )


def _present_count(checklist: EvidenceChecklist) -> int:
    """Total number of PRESENT items."""
    return checklist.present_count


@dataclass
class RuleResult:
    """Result of evaluating a single state rule."""
    matches: bool
    rule_name: str
    conditions: list[str]
    satisfied: list[bool]
    reason: str


def _check_resolution(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    has_release = _item_is_present(checklist, "release_settlement")

    conditions = ["Release/settlement agreement present"]
    satisfied = [has_release]

    return RuleResult(
        matches=has_release,
        rule_name="RESOLUTION",
        conditions=conditions,
        satisfied=satisfied,
        reason=(
            "Release/settlement agreement confirmed present in claim file."
            if has_release else
            "No release/settlement agreement on file."
        ),
    )


def _check_litigation_track(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    has_attorney = _item_is_present(checklist, "attorney_letter")
    has_demand = _item_is_present(checklist, "settlement_demand")
    elapsed_ge_90 = (elapsed is not None and elapsed >= 90)

    # Litigation track: attorney + demand present, or attorney + 90+ days
    # The combination of represented claimant + prolonged timeline is the signal
    lit_match = has_attorney and (has_demand or elapsed_ge_90)

    conditions = [
        "Attorney letter of representation present",
        "Settlement demand present OR elapsed days >= 90",
    ]
    satisfied = [
        has_attorney,
        has_demand or elapsed_ge_90,
    ]

    parts = []
    if has_attorney:
        parts.append("claimant is represented by counsel")
    if has_demand:
        parts.append("settlement demand on file")
    if elapsed_ge_90:
        parts.append(f"elapsed {elapsed} days (≥90)")

    return RuleResult(
        matches=lit_match,
        rule_name="LITIGATION_TRACK",
        conditions=conditions,
        satisfied=satisfied,
        reason=(
            f"Litigation track indicators: {'; '.join(parts)}."
            if lit_match else
            "Insufficient litigation indicators."
        ),
    )


def _check_negotiation(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    has_attorney = _item_is_present(checklist, "attorney_letter")
    has_demand = _item_is_present(checklist, "settlement_demand")
    has_medical = _item_is_present(checklist, "medical_records")
    elapsed_ge_30 = (elapsed is not None and elapsed >= 30)

    # Negotiation: attorney OR demand present, plus some documentation maturity
    neg_match = (has_attorney or has_demand) and (has_medical or elapsed_ge_30)

    conditions = [
        "Attorney letter OR settlement demand present",
        "Medical records present OR elapsed days >= 30",
    ]
    satisfied = [
        has_attorney or has_demand,
        has_medical or elapsed_ge_30,
    ]

    parts = []
    if has_attorney:
        parts.append("attorney letter on file")
    if has_demand:
        parts.append("settlement demand on file")
    if has_medical:
        parts.append("medical records present")
    if elapsed_ge_30:
        parts.append(f"elapsed {elapsed} days (≥30)")

    return RuleResult(
        matches=neg_match,
        rule_name="NEGOTIATION",
        conditions=conditions,
        satisfied=satisfied,
        reason=(
            f"Negotiation indicators: {'; '.join(parts)}."
            if neg_match else
            "Insufficient negotiation indicators."
        ),
    )


def _check_reserve_setting(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    has_medical = _item_is_present(checklist, "medical_records")
    has_bills = _item_is_present(checklist, "medical_bills")
    has_med_auth = _item_is_present(checklist, "medical_authorization")
    elapsed_ge_14 = (elapsed is not None and elapsed >= 14)

    # Reserve setting: medical records OR (medical auth + bills) present,
    # plus enough time has passed that damages are becoming quantifiable
    damages_quantifiable = has_medical or (has_med_auth and has_bills)
    reserve_match = damages_quantifiable and elapsed_ge_14

    conditions = [
        "Medical records present OR (medical auth + medical bills present)",
        "Elapsed days >= 14",
    ]
    satisfied = [
        damages_quantifiable,
        elapsed_ge_14,
    ]

    parts = []
    if has_medical:
        parts.append("medical records on file")
    if has_bills:
        parts.append("medical bills on file")
    if has_med_auth:
        parts.append("medical authorization obtained")
    if elapsed_ge_14:
        parts.append(f"elapsed {elapsed} days (≥14)")

    return RuleResult(
        matches=reserve_match,
        rule_name="RESERVE_SETTING",
        conditions=conditions,
        satisfied=satisfied,
        reason=(
            f"Reserve-setting indicators: {'; '.join(parts)}."
            if reserve_match else
            "Damages not yet quantifiable or insufficient elapsed time."
        ),
    )


def _check_investigation(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    has_police = _item_is_present(checklist, "police_fire_report")
    has_witness = _item_is_present(checklist, "witness_statements")
    has_photos = _item_is_present(checklist, "photos_location")
    has_product_id = _item_is_present(checklist, "product_identification")
    has_claimant_stmt = _item_is_present(checklist, "claimant_statement")
    elapsed_ge_3 = (elapsed is not None and elapsed >= 3)
    present = _present_count(checklist)

    # Investigation: some evidence gathering has begun beyond the initial ACORD
    # At least one investigative document present + enough time for first contacts
    investigative_docs = any([
        has_police, has_witness, has_photos, has_product_id, has_claimant_stmt
    ])
    # Also trigger if enough docs are present (3+) even without specific types
    sufficient_docs = present >= 3

    inv_match = (investigative_docs or sufficient_docs) and elapsed_ge_3

    conditions = [
        "At least one investigative document present (police/witness/photos/product ID/claimant statement) OR 3+ total docs present",
        "Elapsed days >= 3",
    ]
    satisfied = [
        investigative_docs or sufficient_docs,
        elapsed_ge_3,
    ]

    parts = []
    if has_police:
        parts.append("police report on file")
    if has_witness:
        parts.append("witness statement(s) on file")
    if has_photos:
        parts.append("photos on file")
    if has_product_id:
        parts.append("product identification on file")
    if has_claimant_stmt:
        parts.append("claimant statement on file")
    parts.append(f"{present} total documents present")
    if elapsed_ge_3:
        parts.append(f"elapsed {elapsed} days (≥3)")

    return RuleResult(
        matches=inv_match,
        rule_name="INVESTIGATION",
        conditions=conditions,
        satisfied=satisfied,
        reason=(
            f"Investigation indicators: {'; '.join(parts)}."
            if inv_match else
            "Insufficient investigative evidence or too early in claim lifecycle."
        ),
    )


def _check_intake(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
) -> RuleResult:
    """Intake is the default — it always matches as a fallback."""
    present = _present_count(checklist)
    return RuleResult(
        matches=True,
        rule_name="INTAKE",
        conditions=["Default state — claim has been received"],
        satisfied=[True],
        reason=(
            f"Claim is in initial intake phase. "
            f"{present} document(s) confirmed present, "
            f"{'elapsed ' + str(elapsed) + ' days' if elapsed is not None else 'elapsed time unknown'}."
        ),
    )


# Rules evaluated in priority order (highest state first).
# First match wins — a claim in Resolution stays in Resolution even if
# investigation-level docs are present.
_STATE_RULES = [
    (ClaimState.RESOLUTION, _check_resolution),
    (ClaimState.LITIGATION_TRACK, _check_litigation_track),
    (ClaimState.NEGOTIATION, _check_negotiation),
    (ClaimState.RESERVE_SETTING, _check_reserve_setting),
    (ClaimState.INVESTIGATION, _check_investigation),
    (ClaimState.INTAKE, _check_intake),
]


# --------------------------------------------------------------------------
# Trajectory deviation signals.
#
# These are NOT predictions. They are observations about signals that
# suggest the claim may deviate from typical handling. Framed as
# "signals worth noting" not "risk scores."
# --------------------------------------------------------------------------

def _detect_trajectory_signals(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
    elapsed: Optional[int],
    state: ClaimState,
) -> list[str]:
    """Detect signals that suggest deviation from typical claim handling."""
    signals: list[str] = []

    if elapsed is not None:
        # Late reporting
        report_gap = None
        if record.date_of_loss and record.form_completion_date:
            report_gap = (record.form_completion_date - record.date_of_loss).days
        if report_gap and report_gap > 14:
            signals.append(
                f"Late reporting: {report_gap}-day gap between loss and ACORD filing. "
                f"Typical first notice is within 1-7 days."
            )

        # Missing critical items past their expected window
        for item in checklist.items:
            if (item.status == EvidenceStatus.MISSING
                    and item.priority.value == "critical"
                    and elapsed > item.expected_by_day * 2):
                signals.append(
                    f"Overdue critical evidence: {item.label} expected by day "
                    f"{item.expected_by_day}, now day {elapsed}."
                )

    # No witnesses
    if record.witness_count == 0:
        signals.append(
            "No witnesses listed — claimant's account is currently unverified."
        )

    # Severity indicators
    injury_desc = (record.injured_party.injury_description or "").lower()
    treatment = (record.injured_party.treatment_location or "").lower()
    high_severity_kws = ["fracture", "surgery", "graft", "burn unit", "admitted", "concussion"]
    found_severity = [kw for kw in high_severity_kws if kw in injury_desc or kw in treatment]
    if found_severity:
        signals.append(
            f"Elevated severity indicators in injury description: "
            f"{', '.join(found_severity)}."
        )

    # Early attorney involvement
    has_attorney = _item_is_present(checklist, "attorney_letter")
    if has_attorney and elapsed is not None and elapsed < 30:
        signals.append(
            f"Early attorney involvement — representation letter received "
            f"within {elapsed} days of loss."
        )

    # Policy verification missing
    if not _item_is_present(checklist, "policy_verification"):
        signals.append(
            "Coverage not yet verified — policy number, carrier, or location "
            "code missing from ACORD."
        )

    # Surveillance mentioned but not preserved
    loss_desc = (record.loss_description or "").lower()
    mentions_surveillance = any(
        kw in loss_desc for kw in ["camera", "surveillance", "cctv", "footage"]
    )
    if mentions_surveillance and not _item_is_present(checklist, "surveillance_footage"):
        signals.append(
            "Surveillance mentioned in loss description but footage not yet "
            "confirmed preserved."
        )

    return signals


# --------------------------------------------------------------------------
# Classification result
# --------------------------------------------------------------------------

@dataclass
class StateClassification:
    """Full state classification result with reasoning trace."""
    state: ClaimState
    rule_result: RuleResult                 # the rule that fired
    all_rules_evaluated: list[RuleResult]   # all rules, in eval order
    next_actions: list[str]
    trajectory_signals: list[str]
    elapsed_days: Optional[int]

    def print_report(self) -> None:
        print(f"\n  State: {self.state.value}")
        print(f"  Rule : {self.rule_result.rule_name}")
        print(f"  Why  : {self.rule_result.reason}")
        print(f"\n  Rule evaluation trace (first match wins):")
        for rr in self.all_rules_evaluated:
            match_sym = "→" if rr.rule_name == self.rule_result.rule_name else " "
            passed = "MATCH" if rr.matches else "no"
            print(f"    {match_sym} {rr.rule_name:<20} {passed}")
            for cond, sat in zip(rr.conditions, rr.satisfied):
                sym = "✓" if sat else "✗"
                print(f"        {sym} {cond}")

        if self.trajectory_signals:
            print(f"\n  Trajectory signals:")
            for sig in self.trajectory_signals:
                print(f"    ⚠ {sig}")

        print(f"\n  Typical next actions at this stage:")
        for i, action in enumerate(self.next_actions, 1):
            print(f"    {i}. {action}")


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def classify_state(
    record: ClaimRecord,
    checklist: EvidenceChecklist,
) -> StateClassification:
    """Classify the current state of a claim.

    Uses explicit boolean rules evaluated against the checklist and
    elapsed time. Every rule evaluation is logged for transparency.

    Args:
        record: Parsed ClaimRecord from ACORD.
        checklist: Current evidence checklist (may have items checked off
                  by follow-up documents via Day 3 classifier).

    Returns:
        StateClassification with state, reasoning trace, next actions,
        and trajectory deviation signals.
    """
    elapsed = checklist.elapsed_days

    # Evaluate all rules in priority order
    all_results: list[RuleResult] = []
    matched_state: Optional[ClaimState] = None
    matched_result: Optional[RuleResult] = None

    for state, rule_fn in _STATE_RULES:
        result = rule_fn(record, checklist, elapsed)
        all_results.append(result)
        if result.matches and matched_state is None:
            matched_state = state
            matched_result = result

    # Should never happen (INTAKE always matches), but defensive
    if matched_state is None:
        matched_state = ClaimState.INTAKE
        matched_result = all_results[-1]

    # Detect trajectory signals
    trajectory = _detect_trajectory_signals(record, checklist, elapsed, matched_state)

    # Build classification
    classification = StateClassification(
        state=matched_state,
        rule_result=matched_result,
        all_rules_evaluated=all_results,
        next_actions=NEXT_ACTIONS.get(matched_state, []),
        trajectory_signals=trajectory,
        elapsed_days=elapsed,
    )

    log.info(
        "State classified: %s (rule=%s, elapsed=%s days)",
        matched_state.value, matched_result.rule_name, elapsed
    )

    return classification


def build_state_transition(
    old_state: Optional[str],
    new_classification: StateClassification,
) -> Optional[StateTransition]:
    """Build a StateTransition for the evidence chain if state changed.

    Returns None if the state did not change.
    """
    new_state = new_classification.state.value
    if old_state == new_state:
        return None

    rr = new_classification.rule_result
    return StateTransition(
        old_state=old_state or "NONE",
        new_state=new_state,
        rule_name=rr.rule_name,
        rule_conditions=rr.conditions,
        rule_satisfied=rr.satisfied,
        reason=rr.reason,
    )
