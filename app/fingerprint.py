"""
ClaimCompass — claim fingerprint.

Produces a stable 64-bit hex ID tying a claim across its ACORD intake and
all follow-up documents. The fingerprint is deterministic on three inputs:
normalized insured name, date of loss, and policy number.

Why normalization matters: commercial insured names arrive with
inconsistent formatting ("ABC Corp" / "ABC Corporation" / "ABC Corp.").
Un-normalized, the same real-world claim would produce different
fingerprints across ACORD and a later medical authorization, and Day 3's
auto-checkoff logic would silently fail to match documents to claims.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Optional

# Common legal-entity suffixes stripped during normalization.
# Order matters: longer patterns first to avoid partial matches.
_SUFFIX_PATTERNS = [
    r"\bcorporation\b", r"\bincorporated\b", r"\blimited\b",
    r"\bcompany\b", r"\bcompanies\b",
    r"\bcorp\b", r"\binc\b", r"\bltd\b", r"\bllc\b", r"\bllp\b",
    r"\bpllc\b", r"\blp\b", r"\bplc\b", r"\bco\b", r"\bgmbh\b",
    r"\bthe\b",  # drop leading "The"
]
_SUFFIX_RE = re.compile("|".join(_SUFFIX_PATTERNS), flags=re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Normalize a commercial or personal name for stable hashing.

    Pipeline: lowercase → strip punctuation → strip legal suffixes →
    collapse whitespace. Deliberately conservative — a human reader
    should still recognize the output.

    Examples:
      'ABC Corp.'           -> 'abc'
      'ABC Corporation'     -> 'abc'
      'The ABC Corp, LLC'   -> 'abc'
      'Smith & Jones Inc.'  -> 'smith jones'
    """
    if not name:
        return ""
    s = name.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _SUFFIX_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def compute_fingerprint(
    insured_name: Optional[str],
    date_of_loss: Optional[date],
    policy_number: Optional[str],
) -> Optional[str]:
    """Return a 16-char (64-bit) hex fingerprint, or None if inputs are too sparse.

    Requires at least two of the three inputs to be present — a claim with
    only a name and nothing else is not a reliable dedup key. Returning None
    on sparse input is preferable to generating a collision-prone ID.
    """
    normalized_name = normalize_name(insured_name) if insured_name else ""
    date_str = date_of_loss.isoformat() if date_of_loss else ""
    policy = (policy_number or "").strip().upper()

    present = sum(1 for x in (normalized_name, date_str, policy) if x)
    if present < 2:
        return None

    key = f"{normalized_name}|{date_str}|{policy}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[:16]  # 64 bits is plenty for the demo scale


# Self-test block — runnable standalone as a sanity check.
if __name__ == "__main__":
    variants = [
        "ABC Corp",
        "ABC Corporation",
        "ABC Corp.",
        "The ABC Corporation, LLC",
        "  abc   corp  ",
    ]
    dol = date(2026, 3, 14)
    pol = "CGL-12345"
    fps = {v: compute_fingerprint(v, dol, pol) for v in variants}
    print("Fingerprint stability across name variants:")
    for name, fp in fps.items():
        print(f"  {fp}  <-  {name!r}")
    assert len(set(fps.values())) == 1, "Normalization failed — variants produced different fingerprints"
    print("\nAll variants hash to the same fingerprint. Good.")

    # Sparse-input guard
    assert compute_fingerprint("ABC Corp", None, None) is None, "Sparse input should return None"
    print("Sparse-input guard works. Good.")
