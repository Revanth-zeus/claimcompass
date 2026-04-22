"""
ClaimCompass — Follow-up Document Classifier (Day 3).

Classifies incoming follow-up documents (PDFs, text) into document types
that map to evidence checklist items. When a doc is classified, the
corresponding checklist item(s) flip from MISSING/NOT_YET_DUE → PRESENT.

Architecture (same two-path philosophy as the ACORD parser):
  1. Keyword/heuristic classification — deterministic, 0 LLM calls.
     Works on text-extractable PDFs with clear indicators (letterheads,
     form titles, standard headers).
  2. Gemini vision fallback — for scanned/ambiguous docs (stubbed Day 3,
     wired when Gemini client is integrated).

Document types and their checklist mappings:
  police_report        → police_fire_report
  fire_report          → police_fire_report
  claimant_statement   → claimant_statement
  witness_statement    → witness_statements
  medical_authorization→ medical_authorization
  medical_records      → medical_records
  medical_bills        → medical_bills
  insured_statement    → insured_statement
  attorney_letter      → attorney_letter
  settlement_demand    → settlement_demand
  release_agreement    → release_settlement
  photos               → photos_location (premises) or product_inspection (products)
  incident_report      → incident_report_internal
  maintenance_records  → maintenance_records
  surveillance_footage → surveillance_footage
  lease_agreement      → lease_ownership_proof
  product_id_records   → product_identification
  inspection_report    → product_inspection
  purchase_receipt     → product_purchase_records
  recall_bulletin      → recall_history
  product_manual       → product_manual_warnings
  manufacturer_notice  → manufacturer_notice
  repair_estimate      → (no direct checklist item — informational)
  unknown              → (no auto-checkoff, flagged for manual review)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

log = logging.getLogger("claimcompass.classifier")


# --------------------------------------------------------------------------
# Document type enum + checklist mapping
# --------------------------------------------------------------------------

class DocType(str, Enum):
    POLICE_REPORT = "police_report"
    FIRE_REPORT = "fire_report"
    CLAIMANT_STATEMENT = "claimant_statement"
    WITNESS_STATEMENT = "witness_statement"
    MEDICAL_AUTHORIZATION = "medical_authorization"
    MEDICAL_RECORDS = "medical_records"
    MEDICAL_BILLS = "medical_bills"
    INSURED_STATEMENT = "insured_statement"
    ATTORNEY_LETTER = "attorney_letter"
    SETTLEMENT_DEMAND = "settlement_demand"
    RELEASE_AGREEMENT = "release_agreement"
    PHOTOS = "photos"
    INCIDENT_REPORT = "incident_report"
    MAINTENANCE_RECORDS = "maintenance_records"
    SURVEILLANCE_FOOTAGE = "surveillance_footage"
    LEASE_AGREEMENT = "lease_agreement"
    PRODUCT_ID_RECORDS = "product_id_records"
    INSPECTION_REPORT = "inspection_report"
    PURCHASE_RECEIPT = "purchase_receipt"
    RECALL_BULLETIN = "recall_bulletin"
    PRODUCT_MANUAL = "product_manual"
    MANUFACTURER_NOTICE = "manufacturer_notice"
    REPAIR_ESTIMATE = "repair_estimate"
    UNKNOWN = "unknown"


# Maps DocType → evidence checklist item ID(s) it satisfies.
# A single document can satisfy multiple checklist items.
DOC_TO_CHECKLIST: dict[DocType, list[str]] = {
    DocType.POLICE_REPORT:          ["police_fire_report"],
    DocType.FIRE_REPORT:            ["police_fire_report"],
    DocType.CLAIMANT_STATEMENT:     ["claimant_statement"],
    DocType.WITNESS_STATEMENT:      ["witness_statements"],
    DocType.MEDICAL_AUTHORIZATION:  ["medical_authorization"],
    DocType.MEDICAL_RECORDS:        ["medical_records"],
    DocType.MEDICAL_BILLS:          ["medical_bills"],
    DocType.INSURED_STATEMENT:      ["insured_statement"],
    DocType.ATTORNEY_LETTER:        ["attorney_letter"],
    DocType.SETTLEMENT_DEMAND:      ["settlement_demand"],
    DocType.RELEASE_AGREEMENT:      ["release_settlement"],
    DocType.PHOTOS:                 ["photos_location"],  # also product_inspection for products
    DocType.INCIDENT_REPORT:        ["incident_report_internal"],
    DocType.MAINTENANCE_RECORDS:    ["maintenance_records"],
    DocType.SURVEILLANCE_FOOTAGE:   ["surveillance_footage"],
    DocType.LEASE_AGREEMENT:        ["lease_ownership_proof"],
    DocType.PRODUCT_ID_RECORDS:     ["product_identification"],
    DocType.INSPECTION_REPORT:      ["product_inspection"],
    DocType.PURCHASE_RECEIPT:       ["product_purchase_records"],
    DocType.RECALL_BULLETIN:        ["recall_history"],
    DocType.PRODUCT_MANUAL:         ["product_manual_warnings"],
    DocType.MANUFACTURER_NOTICE:    ["manufacturer_notice"],
    DocType.REPAIR_ESTIMATE:        [],       # informational, no checklist item
    DocType.UNKNOWN:                [],
}


class ClassificationPath(str, Enum):
    KEYWORD_HEURISTIC = "keyword_heuristic"
    GEMINI_VISION = "gemini_vision"
    FILENAME_ONLY = "filename_only"
    FAILED = "failed"


@dataclass
class ClassificationResult:
    """Result of classifying a follow-up document."""
    doc_type: DocType
    confidence: str                          # "high", "medium", "low"
    classification_path: ClassificationPath
    matched_keywords: list[str] = field(default_factory=list)
    extracted_entities: dict = field(default_factory=dict)
    checklist_items_satisfied: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.checklist_items_satisfied = DOC_TO_CHECKLIST.get(self.doc_type, []).copy()


# --------------------------------------------------------------------------
# Keyword rules.
# Each rule: (DocType, confidence, list of keyword sets).
# A keyword set matches if ALL keywords in the set appear in the text.
# Multiple sets per rule = OR logic (any set matching is enough).
#
# These are ordered by specificity — more specific rules first so they
# match before generic ones.
# --------------------------------------------------------------------------

_KEYWORD_RULES: list[tuple[DocType, str, list[list[str]]]] = [
    # --- Highly specific document headers ---
    (DocType.MEDICAL_AUTHORIZATION, "high", [
        ["hipaa", "authorization"],
        ["medical", "records", "authorization"],
        ["release", "medical", "information"],
        ["consent", "release", "health"],
        ["protected health information", "authorization"],
    ]),
    (DocType.ATTORNEY_LETTER, "high", [
        ["letter of representation"],
        ["retained", "counsel", "represent"],
        ["attorney", "client", "represent"],
        ["law firm", "behalf of", "client"],
        ["legal representation", "notice"],
    ]),
    (DocType.SETTLEMENT_DEMAND, "high", [
        ["demand", "settlement"],
        ["demand letter", "damages"],
        ["demand for payment", "claim"],
    ]),
    (DocType.RELEASE_AGREEMENT, "high", [
        ["release", "settlement", "agreement"],
        ["general release", "claims"],
        ["release of all claims"],
        ["settlement agreement", "release"],
    ]),
    (DocType.RECALL_BULLETIN, "high", [
        ["recall", "notice", "consumer"],
        ["safety recall", "product"],
        ["cpsc", "recall"],
        ["recall", "bulletin"],
    ]),

    # --- Police / fire reports ---
    (DocType.POLICE_REPORT, "high", [
        ["police", "report"],
        ["incident report", "police department"],
        ["officer", "report", "badge"],
        ["law enforcement", "report"],
        ["offense report"],
    ]),
    (DocType.FIRE_REPORT, "high", [
        ["fire department", "report"],
        ["fire marshal", "report"],
        ["fire investigation", "report"],
    ]),

    # --- Medical ---
    (DocType.MEDICAL_RECORDS, "high", [
        ["medical record"],
        ["patient", "diagnosis", "treatment"],
        ["discharge summary"],
        ["operative report"],
        ["history and physical"],
        ["progress note", "patient"],
        ["emergency department", "report", "patient"],
    ]),
    (DocType.MEDICAL_BILLS, "high", [
        ["medical bill"],
        ["itemized charges"],
        ["statement of charges", "patient"],
        ["billing statement", "medical"],
        ["explanation of benefits"],
        ["hospital bill"],
    ]),

    # --- Statements ---
    (DocType.WITNESS_STATEMENT, "high", [
        ["witness", "statement"],
        ["witness", "account"],
        ["deposition", "witness"],
    ]),
    (DocType.CLAIMANT_STATEMENT, "high", [
        ["claimant", "statement"],
        ["recorded statement", "claimant"],
        ["injured party", "statement"],
    ]),
    (DocType.INSURED_STATEMENT, "high", [
        ["insured", "statement"],
        ["policyholder", "statement"],
        ["named insured", "account"],
    ]),

    # --- Premises-specific ---
    (DocType.INCIDENT_REPORT, "medium", [
        ["incident report"],
        ["accident report", "internal"],
        ["injury report", "employee"],
    ]),
    (DocType.MAINTENANCE_RECORDS, "medium", [
        ["maintenance", "record"],
        ["maintenance", "log"],
        ["inspection", "maintenance"],
        ["repair log"],
        ["work order", "maintenance"],
    ]),
    (DocType.LEASE_AGREEMENT, "high", [
        ["lease", "agreement"],
        ["rental agreement"],
        ["lease", "tenant", "landlord"],
        ["commercial lease"],
    ]),

    # --- Products-specific ---
    (DocType.PRODUCT_ID_RECORDS, "medium", [
        ["serial number", "batch"],
        ["lot number", "manufacturing"],
        ["product identification"],
        ["batch record", "product"],
    ]),
    (DocType.INSPECTION_REPORT, "medium", [
        ["product inspection"],
        ["inspection report", "product"],
        ["expert", "inspection", "examination"],
    ]),
    (DocType.PURCHASE_RECEIPT, "medium", [
        ["receipt", "purchase"],
        ["invoice", "sale"],
        ["proof of purchase"],
        ["sales receipt"],
    ]),
    (DocType.PRODUCT_MANUAL, "medium", [
        ["product manual"],
        ["user manual", "warning"],
        ["instruction manual"],
        ["safety instructions"],
        ["owner's manual"],
    ]),
    (DocType.MANUFACTURER_NOTICE, "medium", [
        ["notice", "manufacturer"],
        ["tender", "defense", "manufacturer"],
        ["notification", "manufacturer", "claim"],
    ]),

    # --- General ---
    (DocType.REPAIR_ESTIMATE, "medium", [
        ["repair estimate"],
        ["estimate", "repair", "cost"],
        ["damage estimate"],
        ["restoration estimate"],
    ]),
    (DocType.PHOTOS, "low", [
        ["photograph"],
        ["photo", "evidence"],
        ["photographic documentation"],
    ]),
]


# Filename-based fallback patterns (when text extraction fails or is empty)
_FILENAME_PATTERNS: list[tuple[DocType, str, re.Pattern]] = [
    (DocType.POLICE_REPORT, "medium", re.compile(r"police[_\-\s]?report", re.I)),
    (DocType.FIRE_REPORT, "medium", re.compile(r"fire[_\-\s]?report", re.I)),
    (DocType.MEDICAL_AUTHORIZATION, "medium", re.compile(r"(hipaa|med[_\-\s]?auth|medical[_\-\s]?auth)", re.I)),
    (DocType.MEDICAL_RECORDS, "medium", re.compile(r"med[_\-\s]?record", re.I)),
    (DocType.MEDICAL_BILLS, "medium", re.compile(r"med[_\-\s]?bill|medical[_\-\s]?bill", re.I)),
    (DocType.WITNESS_STATEMENT, "medium", re.compile(r"witness[_\-\s]?stat", re.I)),
    (DocType.CLAIMANT_STATEMENT, "medium", re.compile(r"claimant[_\-\s]?stat", re.I)),
    (DocType.INSURED_STATEMENT, "medium", re.compile(r"insured[_\-\s]?stat", re.I)),
    (DocType.ATTORNEY_LETTER, "medium", re.compile(r"attorney[_\-\s]?letter|letter[_\-\s]?of[_\-\s]?rep", re.I)),
    (DocType.SETTLEMENT_DEMAND, "medium", re.compile(r"demand[_\-\s]?letter|settlement[_\-\s]?demand", re.I)),
    (DocType.INCIDENT_REPORT, "medium", re.compile(r"incident[_\-\s]?report", re.I)),
    (DocType.LEASE_AGREEMENT, "medium", re.compile(r"lease", re.I)),
    (DocType.PHOTOS, "low", re.compile(r"photo|img|image|pic", re.I)),
    (DocType.REPAIR_ESTIMATE, "medium", re.compile(r"estimate|repair", re.I)),
    (DocType.PURCHASE_RECEIPT, "medium", re.compile(r"receipt|invoice", re.I)),
    (DocType.MAINTENANCE_RECORDS, "medium", re.compile(r"maintenance", re.I)),
    (DocType.RECALL_BULLETIN, "medium", re.compile(r"recall", re.I)),
    (DocType.PRODUCT_MANUAL, "medium", re.compile(r"manual|instruction", re.I)),
]


# --------------------------------------------------------------------------
# Classification logic
# --------------------------------------------------------------------------

def _extract_text_from_pdf(pdf_path: Path, max_pages: int = 3) -> str:
    """Extract text from the first N pages for classification.

    We don't need the full document — classification signals are almost
    always in the first 1-3 pages (headers, letterheads, form titles).
    """
    try:
        reader = PdfReader(str(pdf_path))
        text_parts = []
        for page in reader.pages[:max_pages]:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        log.warning("PDF text extraction failed for %s: %s", pdf_path, e)
        return ""


def _classify_by_keywords(text: str) -> Optional[tuple[DocType, str, list[str]]]:
    """Run keyword rules against extracted text. Returns (type, confidence, matched_kws) or None."""
    text_lower = text.lower()

    for doc_type, confidence, keyword_sets in _KEYWORD_RULES:
        for kw_set in keyword_sets:
            if all(kw.lower() in text_lower for kw in kw_set):
                return doc_type, confidence, kw_set
    return None


def _classify_by_filename(filename: str) -> Optional[tuple[DocType, str]]:
    """Fallback: match filename against known patterns."""
    for doc_type, confidence, pattern in _FILENAME_PATTERNS:
        if pattern.search(filename):
            return doc_type, confidence
    return None


def _extract_entities_from_text(text: str, doc_type: DocType) -> dict:
    """Extract basic entities relevant to the doc type.

    This is deliberately minimal — just enough to be useful in the
    checklist status reason. Full entity extraction would use the LLM.
    """
    entities: dict = {}

    # Try to extract dates (MM/DD/YYYY or YYYY-MM-DD patterns)
    date_patterns = re.findall(
        r'\b(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})\b', text
    )
    if date_patterns:
        entities["dates_found"] = date_patterns[:5]  # cap at 5

    # Dollar amounts
    amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
    if amounts:
        entities["amounts_found"] = amounts[:5]

    # For police/fire reports, try to find report numbers
    if doc_type in (DocType.POLICE_REPORT, DocType.FIRE_REPORT):
        report_nums = re.findall(
            r'(?:report|case|incident)\s*(?:#|number|no\.?)\s*:?\s*([\w\-]+)',
            text, re.IGNORECASE
        )
        if report_nums:
            entities["report_number"] = report_nums[0]

    # For attorney letters, try to find law firm name
    if doc_type == DocType.ATTORNEY_LETTER:
        # Common pattern: "Law Offices of X" or "X & Y, LLP/LLC"
        firm = re.findall(
            r'(?:law offices? of|law firm)\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if firm:
            entities["law_firm"] = firm[0].strip()

    return entities


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def classify_document(
    file_path: str | Path,
    text_override: Optional[str] = None,
) -> ClassificationResult:
    """Classify a follow-up document.

    Args:
        file_path: Path to the PDF or text file.
        text_override: If provided, use this text instead of extracting
                      from the file. Useful for testing or when text has
                      already been extracted.

    Returns:
        ClassificationResult with doc_type, confidence, and checklist mapping.
    """
    file_path = Path(file_path)
    filename = file_path.name

    # Step 1: Extract text
    if text_override is not None:
        text = text_override
    elif file_path.suffix.lower() == ".pdf":
        text = _extract_text_from_pdf(file_path)
    elif file_path.suffix.lower() in (".txt", ".text", ".md"):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
    else:
        text = ""

    # Step 2: Keyword classification on text
    if text.strip():
        kw_result = _classify_by_keywords(text)
        if kw_result:
            doc_type, confidence, matched_kws = kw_result
            entities = _extract_entities_from_text(text, doc_type)
            log.info(
                "Classified %s as %s (confidence=%s, path=keyword_heuristic, matched=%s)",
                filename, doc_type.value, confidence, matched_kws
            )
            return ClassificationResult(
                doc_type=doc_type,
                confidence=confidence,
                classification_path=ClassificationPath.KEYWORD_HEURISTIC,
                matched_keywords=matched_kws,
                extracted_entities=entities,
            )

    # Step 3: Filename fallback
    fn_result = _classify_by_filename(filename)
    if fn_result:
        doc_type, confidence = fn_result
        log.info(
            "Classified %s as %s (confidence=%s, path=filename_only)",
            filename, doc_type.value, confidence
        )
        return ClassificationResult(
            doc_type=doc_type,
            confidence=confidence,
            classification_path=ClassificationPath.FILENAME_ONLY,
            notes=["Classified by filename pattern only — text extraction "
                   "was empty or did not match any keyword rules."],
        )

    # Step 4: Unknown
    log.info("Could not classify %s — marking as unknown.", filename)
    return ClassificationResult(
        doc_type=DocType.UNKNOWN,
        confidence="low",
        classification_path=ClassificationPath.FAILED,
        notes=["No keyword matches in text, no filename pattern match. "
               "Manual review recommended."],
    )


# --------------------------------------------------------------------------
# Checklist integration — the Day 3 deliverable.
# Evidence chain integration — Trust Anchor 3 (Day 4).
# --------------------------------------------------------------------------

from app.checklist import EvidenceChecklist, EvidenceStatus
from app.evidence_chain import ChecklistChange, EvidenceChain, EvidenceChainEntry


def apply_document_to_checklist(
    checklist: EvidenceChecklist,
    classification: ClassificationResult,
    filename: str = "",
) -> list[ChecklistChange]:
    """Apply a classified document to the checklist, flipping items to PRESENT.

    Returns list of ChecklistChange objects for the evidence chain.
    """
    changes: list[ChecklistChange] = []

    for item_id in classification.checklist_items_satisfied:
        for item in checklist.items:
            if item.id == item_id and item.status != EvidenceStatus.NOT_APPLICABLE:
                old_status = item.status
                item.status = EvidenceStatus.PRESENT
                item.status_reason = (
                    f"Confirmed present — {classification.doc_type.value} "
                    f"document received ({filename or 'unnamed'}). "
                    f"Classification: {classification.confidence} confidence via "
                    f"{classification.classification_path.value}."
                )
                if old_status != EvidenceStatus.PRESENT:
                    changes.append(ChecklistChange(
                        item_id=item_id,
                        item_label=item.label,
                        old_status=old_status.value,
                        new_status=EvidenceStatus.PRESENT.value,
                    ))
                    log.info(
                        "Checklist item '%s' updated: %s → PRESENT (from %s)",
                        item_id, old_status.value, filename
                    )

    return changes


def process_document(
    file_path: str | Path,
    record: "ClaimRecord",
    checklist: EvidenceChecklist,
    evidence_chain: EvidenceChain,
    text_override: Optional[str] = None,
) -> ClassificationResult:
    """Full pipeline: classify a document → update checklist → classify state → log to evidence chain.

    This is the single entry point for processing follow-up documents.
    It ties together Days 3 and 4 into one operation.

    Args:
        file_path: Path to the follow-up document.
        record: Parsed ClaimRecord from ACORD.
        checklist: Current evidence checklist (mutated in place).
        evidence_chain: Evidence chain to log to (mutated in place).
        text_override: Optional text override for testing.

    Returns:
        ClassificationResult for the document.
    """
    from datetime import datetime
    from app.state_classifier import classify_state, build_state_transition

    file_path = Path(file_path)

    # Step 1: Classify the document
    classification = classify_document(file_path, text_override=text_override)

    # Step 2: Apply to checklist and capture changes
    old_state = evidence_chain.current_state
    changes = apply_document_to_checklist(checklist, classification, file_path.name)

    # Step 3: Re-classify state after checklist update
    state_result = classify_state(record, checklist)
    transition = build_state_transition(old_state, state_result)

    # Step 4: Log to evidence chain
    entry = EvidenceChainEntry(
        timestamp=datetime.now(),
        trigger_document=file_path.name,
        trigger_doc_type=classification.doc_type.value,
        trigger_confidence=classification.confidence,
        checklist_changes=changes,
        state_transition=transition,
    )
    evidence_chain.add_entry(entry)

    return classification

