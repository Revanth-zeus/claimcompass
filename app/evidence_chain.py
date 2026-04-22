"""
ClaimCompass — Evidence Chain (Trust Anchor 3).

Every time a document arrives and changes the checklist or claim state,
the system logs a full provenance entry showing:
  - What document triggered the change
  - What checklist items changed (before → after)
  - What state transition occurred (if any)
  - Which rule fired and the exact boolean conditions that were true

This is what makes the state classifier feel operational instead of
decorative. Every state transition has a receipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChecklistChange:
    """A single checklist item that changed status."""
    item_id: str
    item_label: str
    old_status: str
    new_status: str


@dataclass
class StateTransition:
    """A state change with the rule that fired."""
    old_state: str
    new_state: str
    rule_name: str               # e.g. "INVESTIGATION_ENTRY"
    rule_conditions: list[str]   # each condition that was evaluated
    rule_satisfied: list[bool]   # True/False for each condition
    reason: str                  # human-readable summary


@dataclass
class EvidenceChainEntry:
    """One entry in the evidence chain — one document arrival event."""
    timestamp: datetime
    trigger_document: str                  # filename
    trigger_doc_type: str                  # classified type
    trigger_confidence: str                # classification confidence
    checklist_changes: list[ChecklistChange] = field(default_factory=list)
    state_transition: Optional[StateTransition] = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line summary for logging."""
        parts = [f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.trigger_document}"]
        parts.append(f"  type={self.trigger_doc_type} ({self.trigger_confidence})")
        if self.checklist_changes:
            changes = ", ".join(
                f"{c.item_id}: {c.old_status}→{c.new_status}"
                for c in self.checklist_changes
            )
            parts.append(f"  checklist: {changes}")
        if self.state_transition:
            st = self.state_transition
            parts.append(f"  state: {st.old_state}→{st.new_state} (rule: {st.rule_name})")
            parts.append(f"  reason: {st.reason}")
        return "\n".join(parts)


@dataclass
class EvidenceChain:
    """Full evidence chain for a claim across its lifecycle."""
    claim_fingerprint: Optional[str] = None
    entries: list[EvidenceChainEntry] = field(default_factory=list)

    def add_entry(self, entry: EvidenceChainEntry) -> None:
        self.entries.append(entry)

    @property
    def current_state(self) -> Optional[str]:
        """The most recent state from the chain."""
        for entry in reversed(self.entries):
            if entry.state_transition:
                return entry.state_transition.new_state
        return None

    def print_chain(self) -> None:
        """Print the full evidence chain for debugging/demo."""
        print(f"\n  Evidence Chain ({len(self.entries)} entries)")
        print(f"  {'─' * 70}")
        for i, entry in enumerate(self.entries):
            print(f"\n  Entry {i + 1}: {entry.trigger_document}")
            print(f"    Type      : {entry.trigger_doc_type} ({entry.trigger_confidence})")
            print(f"    Timestamp : {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

            if entry.checklist_changes:
                print(f"    Checklist changes:")
                for c in entry.checklist_changes:
                    print(f"      {c.item_label}: {c.old_status} → {c.new_status}")

            if entry.state_transition:
                st = entry.state_transition
                print(f"    State     : {st.old_state} → {st.new_state}")
                print(f"    Rule      : {st.rule_name}")
                print(f"    Conditions:")
                for cond, sat in zip(st.rule_conditions, st.rule_satisfied):
                    sym = "✓" if sat else "✗"
                    print(f"      {sym} {cond}")
                print(f"    Reason    : {st.reason}")

            if entry.notes:
                for note in entry.notes:
                    print(f"    Note      : {note}")
