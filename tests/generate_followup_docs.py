"""
Generate synthetic follow-up documents for Scenario 1 (Maplewood Kitchen slip-and-fall).

Creates text files simulating:
  1. Police report (should → police_fire_report, already PRESENT from ACORD)
  2. Medical authorization / HIPAA release (should → medical_authorization)
  3. Witness statement (should → witness_statements)
  4. Attorney letter of representation (should → attorney_letter)
  5. Repair estimate (should → repair_estimate, no checklist item)
  6. An ambiguous document (should → unknown)

These are plain-text simulations, not real PDFs. The classifier works on
extracted text, so text files exercise the same keyword matching path.

Run: python -m tests.generate_followup_docs
"""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "followups_s1"


DOCS = {
    "police_report_MNPD-2026-031447.txt": """\
METRO NASHVILLE POLICE DEPARTMENT
INCIDENT / OFFENSE REPORT

Report Number: MNPD-2026-031447
Date of Report: 03/14/2026
Reporting Officer: Ofc. J. Williams, Badge #4418

INCIDENT TYPE: Slip and Fall — Commercial Premises
LOCATION: 4812 Charlotte Pike, Nashville, TN 37209

NARRATIVE:
On 03/14/2026 at approximately 1245 hours, officers responded to the above
location (Maplewood Kitchen restaurant) regarding an injury to a customer.
Upon arrival, EMS was on scene attending to the injured party, Patricia A. Reyes
(DOB: XX/XX/1974, age 52). Ms. Reyes stated she slipped on a wet floor
near the restroom corridor. A wet-floor sign was observed at the south end
of the corridor but not the north end where Ms. Reyes entered.

Two witnesses were present and provided contact information:
  - Derek J. Monroe, 918 18th Ave S, Nashville TN
  - Ana-Maria Kovacs, 2310 Blair Blvd, Nashville TN

Shift Manager Jenna Park stated staff had mopped approximately ten minutes
prior. Interior surveillance camera (east-facing, above corridor entrance)
was noted; footage preservation was requested.

Ms. Reyes was transported by ambulance to St. Thomas West Hospital ER.

No citations issued. Report filed for documentation purposes.
""",

    "medical_authorization_reyes.txt": """\
AUTHORIZATION FOR RELEASE OF PROTECTED HEALTH INFORMATION
(HIPAA-Compliant Medical Records Release)

Patient Name: Patricia A. Reyes
Date of Birth: [REDACTED]
Social Security Number: [REDACTED]

I, Patricia A. Reyes, hereby authorize the following healthcare provider(s)
to release my protected health information:

Provider: St. Thomas West Hospital
Address: 4220 Harding Pike, Nashville, TN 37205

Release To:
Continental Guaranty Insurance Company
Claims Department
Re: Claim / Policy CGL-884471-02
Date of Loss: 03/14/2026

Information to be released:
- Emergency department records for visit on 03/14/2026
- Diagnostic imaging (X-ray, CT, MRI) results
- Treatment plans and discharge instructions
- Follow-up appointment records

This authorization is valid for 12 months from the date of signature.

Signature: Patricia A. Reyes
Date: 03/30/2026
Witness: [signed]
""",

    "witness_statement_monroe.txt": """\
WITNESS STATEMENT

Witness Name: Derek J. Monroe
Date: 04/02/2026
Location of Incident: Maplewood Kitchen, 4812 Charlotte Pike, Nashville, TN

Statement:

I, Derek J. Monroe, was dining at the Maplewood Kitchen restaurant on
March 14, 2026, at approximately 12:40 PM. I was seated at a table near
the restroom corridor.

I observed a woman (later identified as Patricia Reyes) walking toward
the restrooms. As she turned the corner into the corridor, her feet
appeared to slip on the floor surface. She fell to her right side and
hit the ground hard. I heard her cry out.

I got up to help. The floor in the corridor was wet — I could see it was
shiny. There was a yellow wet-floor sign at the far end of the corridor
(near the restroom doors) but there was no sign at the entrance where
Ms. Reyes walked in.

A restaurant employee came over quickly and called 911. The ambulance
arrived within about 10 minutes.

I am willing to provide further testimony if needed.

Signed: Derek J. Monroe
Date: 04/02/2026
""",

    "attorney_letter_benton_graves.txt": """\
BENTON & GRAVES LLP
Attorneys at Law
500 Church Street, Suite 1200
Nashville, Tennessee 37219

April 8, 2026

Via Certified Mail

Continental Guaranty Insurance Company
Claims Department
P.O. Box 94100
Nashville, TN 37209

Re: Letter of Representation
    Claimant: Patricia A. Reyes
    Date of Loss: March 14, 2026
    Policy Number: CGL-884471-02
    Insured: Maplewood Kitchen Group, LLC

Dear Claims Representative:

Please be advised that this law firm has been retained to represent
Patricia A. Reyes in connection with injuries sustained on March 14, 2026,
at the Maplewood Kitchen restaurant located at 4812 Charlotte Pike,
Nashville, Tennessee 37209.

Please direct all future communications regarding this matter to our
office. Do not contact our client directly.

We are currently gathering medical records and documentation and will
submit a formal demand at the appropriate time.

Please confirm receipt of this letter and provide us with the assigned
claims adjuster's name and direct contact information.

Very truly yours,

Sarah K. Benton, Esq.
BENTON & GRAVES LLP
(615) 555-0900
sbenton@bentongraves.example
""",

    "repair_estimate_treadmill.txt": """\
RESTORATION ESTIMATE

Prepared by: ProFit Equipment Services, Inc.
Date: April 15, 2026
Estimate Number: EST-2026-04-0892

Customer: Volunteer Fitness Centers, Inc.
Location: 2740 Merchants Dr, Knoxville, TN 37912

Description of Damage:
Two (2) Precor TRM 885 commercial treadmills damaged by falling HVAC
ductwork on April 14, 2026.

Unit 1 (S/N: TRM885-29441):
  - Frame bent, deck cracked, console destroyed
  - Recommendation: Total loss, replacement required
  - Replacement cost: $7,500.00

Unit 2 (S/N: TRM885-29442):
  - Handrail bent, belt torn, minor frame damage
  - Recommendation: Repairable
  - Repair estimate: $2,200.00

Total Estimated Cost: $9,700.00

Note: This estimate does not include the plate-glass window replacement,
which should be assessed by a glazier.
""",

    "random_correspondence.txt": """\
Hi Marcus,

Just following up on our conversation from last week. Can you send me
the updated renewal quote when you get a chance? Also, we need to
schedule the annual review meeting — maybe sometime in May?

Thanks,
David
""",
}


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for filename, content in DOCS.items():
        path = FIXTURES / filename
        path.write_text(content, encoding="utf-8")
        print(f"  [{filename}] written")
    print(f"\n{len(DOCS)} follow-up docs written to {FIXTURES}/")


if __name__ == "__main__":
    main()
