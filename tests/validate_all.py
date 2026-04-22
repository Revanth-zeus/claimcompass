"""Quick validation: parse all 5 scenarios and print a summary."""

import logging
from pathlib import Path
from app.acord_parser import parse_acord

logging.basicConfig(level=logging.WARNING)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

for i in range(1, 6):
    pdf = FIXTURES / f"acord_filled_scenario{i}.pdf"
    r = parse_acord(pdf)
    gap = ""
    if r.date_of_loss and r.form_completion_date:
        gap = f"{(r.form_completion_date - r.date_of_loss).days}d gap"
    print(
        f"S{i}: {r.populated_field_count():>2}/26 fields | "
        f"fp={r.claim_fingerprint or 'NONE':16s} | "
        f"type={r.liability_type.value:10s} | "
        f"role={r.premises_role.value if r.liability_type.value in ('premises','both') else r.products_role.value:12s} | "
        f"witnesses={r.witness_count} | "
        f"police={'YES' if r.authority_contacted.report_number else 'NO ':3s} | "
        f"prop_dmg={'YES' if r.property_damage.estimated_amount else 'NO ':3s} | "
        f"{gap}"
    )
