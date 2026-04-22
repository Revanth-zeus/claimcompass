# """
# ClaimCompass — FastAPI Server (Day 5/6).

# Endpoints:
#   GET  /                    → serves the frontend HTML
#   POST /api/parse-acord     → upload ACORD PDF, returns claim record + checklist + state
#   POST /api/upload-document → upload follow-up doc, returns classification + updated checklist + state + evidence chain
#   GET  /api/state           → current claim state (in-memory session)
#   POST /api/reset           → reset to fresh state

# In-memory session: one claim at a time (demo scope). No database.
# """

# from __future__ import annotations

# import json
# import shutil
# import tempfile
# from datetime import date, datetime
# from pathlib import Path
# from typing import Optional

# from fastapi import FastAPI, File, Form, UploadFile
# from fastapi.responses import HTMLResponse, JSONResponse
# from fastapi.middleware.cors import CORSMiddleware

# from app.acord_parser import parse_acord
# from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
# from app.classifier import classify_document, apply_document_to_checklist, ClassificationResult
# from app.evidence_chain import EvidenceChain, EvidenceChainEntry, ChecklistChange
# from app.state_classifier import classify_state, build_state_transition, ClaimState
# from app.schemas import ClaimRecord

# app = FastAPI(title="ClaimCompass", version="0.1.0")
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# # --------------------------------------------------------------------------
# # In-memory session state (one claim at a time for demo)
# # --------------------------------------------------------------------------
# class Session:
#     record: Optional[ClaimRecord] = None
#     checklist: Optional[EvidenceChecklist] = None
#     chain: EvidenceChain = EvidenceChain()
#     as_of_date: date = date.today()

# session = Session()


# def _record_to_dict(r: ClaimRecord) -> dict:
#     return {
#         "claim_fingerprint": r.claim_fingerprint,
#         "form_completion_date": str(r.form_completion_date) if r.form_completion_date else None,
#         "date_of_loss": str(r.date_of_loss) if r.date_of_loss else None,
#         "time_of_loss": str(r.time_of_loss) if r.time_of_loss else None,
#         "policy_number": r.policy_number,
#         "carrier_name": r.carrier_name,
#         "carrier_naic_code": r.carrier_naic_code,
#         "insured_location_code": r.insured_location_code,
#         "liability_type": r.liability_type.value,
#         "premises_role": r.premises_role.value,
#         "premises_type": r.premises_type,
#         "products_role": r.products_role.value,
#         "product_description": r.product_description,
#         "insured_name": r.insured_name,
#         "property_owner_name": r.property_owner_name,
#         "product_manufacturer_name": r.product_manufacturer_name,
#         "loss_location_city": r.loss_location_city,
#         "loss_location_state": r.loss_location_state,
#         "loss_location_description": r.loss_location_description,
#         "loss_description": r.loss_description,
#         "authority_name": r.authority_contacted.authority_name,
#         "report_number": r.authority_contacted.report_number,
#         "injured_party": {
#             "full_name": r.injured_party.full_name,
#             "age": r.injured_party.age,
#             "occupation": r.injured_party.occupation,
#             "injury_description": r.injured_party.injury_description,
#             "treatment_location": r.injured_party.treatment_location,
#         },
#         "property_damage": {
#             "description": r.property_damage.description,
#             "estimated_amount": r.property_damage.estimated_amount,
#         },
#         "witness_count": r.witness_count,
#         "extraction_path": r.extraction_path.value,
#         "populated_fields": r.populated_field_count(),
#     }


# def _checklist_to_dict(cl: EvidenceChecklist) -> list[dict]:
#     return [
#         {
#             "id": item.id,
#             "label": item.label,
#             "category": item.category.value,
#             "priority": item.priority.value,
#             "expectedByDay": item.expected_by_day,
#             "status": item.status.value,
#             "reason": item.status_reason,
#         }
#         for item in cl.items
#     ]


# def _state_to_dict(sc) -> dict:
#     return {
#         "state": sc.state.value,
#         "rule": sc.rule_result.rule_name,
#         "reason": sc.rule_result.reason,
#         "conditions": [
#             {"condition": c, "satisfied": s}
#             for c, s in zip(sc.rule_result.conditions, sc.rule_result.satisfied)
#         ],
#         "nextActions": sc.next_actions,
#         "trajectorySignals": sc.trajectory_signals,
#         "elapsedDays": sc.elapsed_days,
#     }


# def _chain_to_dict(chain: EvidenceChain) -> list[dict]:
#     entries = []
#     for e in chain.entries:
#         entry = {
#             "document": e.trigger_document,
#             "docType": e.trigger_doc_type,
#             "confidence": e.trigger_confidence,
#             "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
#             "checklistChanges": [
#                 {"itemId": c.item_id, "label": c.item_label, "oldStatus": c.old_status, "newStatus": c.new_status}
#                 for c in e.checklist_changes
#             ],
#             "stateChange": None,
#         }
#         if e.state_transition:
#             entry["stateChange"] = {
#                 "oldState": e.state_transition.old_state,
#                 "newState": e.state_transition.new_state,
#                 "rule": e.state_transition.rule_name,
#                 "reason": e.state_transition.reason,
#             }
#         entries.append(entry)
#     return entries


# def _build_full_response() -> dict:
#     if not session.record:
#         return {"error": "No claim loaded. Upload an ACORD form first."}
#     sc = classify_state(session.record, session.checklist)
#     return {
#         "record": _record_to_dict(session.record),
#         "checklist": _checklist_to_dict(session.checklist),
#         "state": _state_to_dict(sc),
#         "evidenceChain": _chain_to_dict(session.chain),
#     }


# # --------------------------------------------------------------------------
# # Endpoints
# # --------------------------------------------------------------------------

# @app.post("/api/parse-acord")
# async def parse_acord_endpoint(file: UploadFile = File(...)):
#     """Upload an ACORD Form 3 PDF. Resets the session."""
#     with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
#         shutil.copyfileobj(file.file, tmp)
#         tmp_path = Path(tmp.name)

#     try:
#         record = parse_acord(tmp_path)
#         checklist = generate_checklist(record, as_of_date=session.as_of_date)
#         chain = EvidenceChain(claim_fingerprint=record.claim_fingerprint)

#         # Initial state classification
#         sc = classify_state(record, checklist)
#         transition = build_state_transition(None, sc)

#         initial_entry = EvidenceChainEntry(
#             timestamp=datetime.now(),
#             trigger_document=file.filename or "acord_upload.pdf",
#             trigger_doc_type="acord_form_3",
#             trigger_confidence="high",
#             state_transition=transition,
#         )
#         chain.add_entry(initial_entry)

#         # Store in session
#         session.record = record
#         session.checklist = checklist
#         session.chain = chain

#         return JSONResponse(_build_full_response())
#     finally:
#         tmp_path.unlink(missing_ok=True)


# @app.post("/api/upload-document")
# async def upload_document_endpoint(
#     file: UploadFile = File(None),
#     doc_type: str = Form(None),
#     doc_name: str = Form(None),
# ):
#     """Upload a follow-up document or simulate one by doc_type."""
#     if not session.record:
#         return JSONResponse({"error": "No claim loaded."}, status_code=400)

#     filename = doc_name or (file.filename if file else f"{doc_type}_{datetime.now().strftime('%H%M%S')}")

#     if file:
#         # Preserve the original file extension so the classifier handles
#         # .txt, .pdf, etc. correctly instead of forcing everything to .pdf
#         orig_name = file.filename or "upload"
#         suffix = Path(orig_name).suffix or ".pdf"
#         with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = Path(tmp.name)
#         # Rename to preserve original filename for classifier's filename-matching
#         named_path = tmp_path.parent / orig_name
#         try:
#             tmp_path.rename(named_path)
#         except (OSError, FileExistsError):
#             named_path = tmp_path  # fallback if rename fails
#         try:
#             classification = classify_document(named_path)
#         finally:
#             named_path.unlink(missing_ok=True)
#             tmp_path.unlink(missing_ok=True)
#     elif doc_type:
#         # Simulate: create a ClassificationResult directly
#         from app.classifier import DocType, ClassificationPath, DOC_TO_CHECKLIST
#         try:
#             dt = DocType(doc_type)
#         except ValueError:
#             return JSONResponse({"error": f"Unknown doc_type: {doc_type}"}, status_code=400)
#         classification = ClassificationResult(
#             doc_type=dt,
#             confidence="high",
#             classification_path=ClassificationPath.KEYWORD_HEURISTIC,
#         )
#     else:
#         return JSONResponse({"error": "Provide either a file or doc_type."}, status_code=400)

#     # Apply to checklist
#     old_state = session.chain.current_state
#     changes = apply_document_to_checklist(session.checklist, classification, filename)

#     # Re-classify state
#     sc = classify_state(session.record, session.checklist)
#     transition = build_state_transition(old_state, sc)

#     # Log to evidence chain
#     entry = EvidenceChainEntry(
#         timestamp=datetime.now(),
#         trigger_document=filename,
#         trigger_doc_type=classification.doc_type.value,
#         trigger_confidence=classification.confidence,
#         checklist_changes=changes,
#         state_transition=transition,
#     )
#     session.chain.add_entry(entry)

#     return JSONResponse(_build_full_response())


# @app.get("/api/state")
# async def get_state():
#     return JSONResponse(_build_full_response())


# @app.post("/api/reset")
# async def reset():
#     session.record = None
#     session.checklist = None
#     session.chain = EvidenceChain()
#     return JSONResponse({"status": "reset"})


# # --------------------------------------------------------------------------
# # Serve frontend
# # --------------------------------------------------------------------------

# @app.get("/", response_class=HTMLResponse)
# async def serve_frontend():
#     frontend_path = Path(__file__).parent / "frontend.html"
#     if frontend_path.exists():
#         return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
#     return HTMLResponse("<h1>ClaimCompass</h1><p>frontend.html not found.</p>")


# """
# ClaimCompass — FastAPI Server (Day 5/6).

# Endpoints:
#   GET  /                    → serves the frontend HTML
#   POST /api/parse-acord     → upload ACORD PDF, returns claim record + checklist + state
#   POST /api/upload-document → upload follow-up doc, returns classification + updated checklist + state + evidence chain
#   GET  /api/state           → current claim state (in-memory session)
#   POST /api/reset           → reset to fresh state

# In-memory session: one claim at a time (demo scope). No database.
# """

# from __future__ import annotations

# import json
# import shutil
# import tempfile
# from datetime import date, datetime
# from pathlib import Path
# from typing import Optional

# from fastapi import FastAPI, File, Form, UploadFile
# from fastapi.responses import HTMLResponse, JSONResponse
# from fastapi.middleware.cors import CORSMiddleware

# from app.acord_parser import parse_acord
# from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
# from app.classifier import classify_document, apply_document_to_checklist, ClassificationResult
# from app.evidence_chain import EvidenceChain, EvidenceChainEntry, ChecklistChange
# from app.state_classifier import classify_state, build_state_transition, ClaimState
# from app.schemas import ClaimRecord

# app = FastAPI(title="ClaimCompass", version="0.1.0")
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# # --------------------------------------------------------------------------
# # In-memory session state (one claim at a time for demo)
# # --------------------------------------------------------------------------
# class Session:
#     record: Optional[ClaimRecord] = None
#     checklist: Optional[EvidenceChecklist] = None
#     chain: EvidenceChain = EvidenceChain()
#     as_of_date: date = date.today()

# session = Session()


# def _record_to_dict(r: ClaimRecord) -> dict:
#     return {
#         "claim_fingerprint": r.claim_fingerprint,
#         "form_completion_date": str(r.form_completion_date) if r.form_completion_date else None,
#         "date_of_loss": str(r.date_of_loss) if r.date_of_loss else None,
#         "time_of_loss": str(r.time_of_loss) if r.time_of_loss else None,
#         "policy_number": r.policy_number,
#         "carrier_name": r.carrier_name,
#         "carrier_naic_code": r.carrier_naic_code,
#         "insured_location_code": r.insured_location_code,
#         "liability_type": r.liability_type.value,
#         "premises_role": r.premises_role.value,
#         "premises_type": r.premises_type,
#         "products_role": r.products_role.value,
#         "product_description": r.product_description,
#         "insured_name": r.insured_name,
#         "property_owner_name": r.property_owner_name,
#         "product_manufacturer_name": r.product_manufacturer_name,
#         "loss_location_city": r.loss_location_city,
#         "loss_location_state": r.loss_location_state,
#         "loss_location_description": r.loss_location_description,
#         "loss_description": r.loss_description,
#         "authority_name": r.authority_contacted.authority_name,
#         "report_number": r.authority_contacted.report_number,
#         "injured_party": {
#             "full_name": r.injured_party.full_name,
#             "age": r.injured_party.age,
#             "occupation": r.injured_party.occupation,
#             "injury_description": r.injured_party.injury_description,
#             "treatment_location": r.injured_party.treatment_location,
#         },
#         "property_damage": {
#             "description": r.property_damage.description,
#             "estimated_amount": r.property_damage.estimated_amount,
#         },
#         "witness_count": r.witness_count,
#         "extraction_path": r.extraction_path.value,
#         "populated_fields": r.populated_field_count(),
#     }


# def _checklist_to_dict(cl: EvidenceChecklist) -> list[dict]:
#     return [
#         {
#             "id": item.id,
#             "label": item.label,
#             "category": item.category.value,
#             "priority": item.priority.value,
#             "expectedByDay": item.expected_by_day,
#             "status": item.status.value,
#             "reason": item.status_reason,
#         }
#         for item in cl.items
#     ]


# def _state_to_dict(sc) -> dict:
#     return {
#         "state": sc.state.value,
#         "rule": sc.rule_result.rule_name,
#         "reason": sc.rule_result.reason,
#         "conditions": [
#             {"condition": c, "satisfied": s}
#             for c, s in zip(sc.rule_result.conditions, sc.rule_result.satisfied)
#         ],
#         "nextActions": sc.next_actions,
#         "trajectorySignals": sc.trajectory_signals,
#         "elapsedDays": sc.elapsed_days,
#     }


# def _chain_to_dict(chain: EvidenceChain) -> list[dict]:
#     entries = []
#     for e in chain.entries:
#         entry = {
#             "document": e.trigger_document,
#             "docType": e.trigger_doc_type,
#             "confidence": e.trigger_confidence,
#             "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
#             "checklistChanges": [
#                 {"itemId": c.item_id, "label": c.item_label, "oldStatus": c.old_status, "newStatus": c.new_status}
#                 for c in e.checklist_changes
#             ],
#             "stateChange": None,
#         }
#         if e.state_transition:
#             entry["stateChange"] = {
#                 "oldState": e.state_transition.old_state,
#                 "newState": e.state_transition.new_state,
#                 "rule": e.state_transition.rule_name,
#                 "reason": e.state_transition.reason,
#             }
#         entries.append(entry)
#     return entries


# def _build_full_response() -> dict:
#     if not session.record:
#         return {"error": "No claim loaded. Upload an ACORD form first."}
#     sc = classify_state(session.record, session.checklist)
#     return {
#         "record": _record_to_dict(session.record),
#         "checklist": _checklist_to_dict(session.checklist),
#         "state": _state_to_dict(sc),
#         "evidenceChain": _chain_to_dict(session.chain),
#     }


# # --------------------------------------------------------------------------
# # Endpoints
# # --------------------------------------------------------------------------

# @app.post("/api/parse-acord")
# async def parse_acord_endpoint(file: UploadFile = File(...)):
#     """Upload an ACORD Form 3 PDF. Resets the session."""
#     with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
#         shutil.copyfileobj(file.file, tmp)
#         tmp_path = Path(tmp.name)

#     try:
#         record = parse_acord(tmp_path)
#         checklist = generate_checklist(record, as_of_date=session.as_of_date)
#         chain = EvidenceChain(claim_fingerprint=record.claim_fingerprint)

#         # Initial state classification
#         sc = classify_state(record, checklist)
#         transition = build_state_transition(None, sc)

#         initial_entry = EvidenceChainEntry(
#             timestamp=datetime.now(),
#             trigger_document=file.filename or "acord_upload.pdf",
#             trigger_doc_type="acord_form_3",
#             trigger_confidence="high",
#             state_transition=transition,
#         )
#         chain.add_entry(initial_entry)

#         # Store in session
#         session.record = record
#         session.checklist = checklist
#         session.chain = chain

#         return JSONResponse(_build_full_response())
#     finally:
#         tmp_path.unlink(missing_ok=True)


# @app.post("/api/upload-document")
# async def upload_document_endpoint(
#     file: UploadFile = File(None),
#     doc_type: str = Form(None),
#     doc_name: str = Form(None),
# ):
#     """Upload a follow-up document or simulate one by doc_type."""
#     if not session.record:
#         return JSONResponse({"error": "No claim loaded."}, status_code=400)

#     filename = doc_name or (file.filename if file else f"{doc_type}_{datetime.now().strftime('%H%M%S')}")

#     if file:
#         # Preserve the original file extension so the classifier handles
#         # .txt, .pdf, etc. correctly instead of forcing everything to .pdf
#         orig_name = file.filename or "upload"
#         suffix = Path(orig_name).suffix or ".pdf"
#         with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = Path(tmp.name)
#         # Rename to preserve original filename for classifier's filename-matching
#         named_path = tmp_path.parent / orig_name
#         try:
#             tmp_path.rename(named_path)
#         except (OSError, FileExistsError):
#             named_path = tmp_path  # fallback if rename fails
#         try:
#             classification = classify_document(named_path)
#         finally:
#             named_path.unlink(missing_ok=True)
#             tmp_path.unlink(missing_ok=True)
#     elif doc_type:
#         # Simulate: create a ClassificationResult directly
#         from app.classifier import DocType, ClassificationPath, DOC_TO_CHECKLIST
#         try:
#             dt = DocType(doc_type)
#         except ValueError:
#             return JSONResponse({"error": f"Unknown doc_type: {doc_type}"}, status_code=400)
#         classification = ClassificationResult(
#             doc_type=dt,
#             confidence="high",
#             classification_path=ClassificationPath.KEYWORD_HEURISTIC,
#         )
#     else:
#         return JSONResponse({"error": "Provide either a file or doc_type."}, status_code=400)

#     # Apply to checklist
#     old_state = session.chain.current_state
#     changes = apply_document_to_checklist(session.checklist, classification, filename)

#     # Re-classify state
#     sc = classify_state(session.record, session.checklist)
#     transition = build_state_transition(old_state, sc)

#     # Log to evidence chain
#     entry = EvidenceChainEntry(
#         timestamp=datetime.now(),
#         trigger_document=filename,
#         trigger_doc_type=classification.doc_type.value,
#         trigger_confidence=classification.confidence,
#         checklist_changes=changes,
#         state_transition=transition,
#     )
#     session.chain.add_entry(entry)

#     return JSONResponse(_build_full_response())


# @app.get("/api/state")
# async def get_state():
#     return JSONResponse(_build_full_response())


# @app.post("/api/reset")
# async def reset():
#     session.record = None
#     session.checklist = None
#     session.chain = EvidenceChain()
#     return JSONResponse({"status": "reset"})


# # --------------------------------------------------------------------------
# # Serve frontend
# # --------------------------------------------------------------------------

# @app.get("/", response_class=HTMLResponse)
# async def serve_frontend():
#     frontend_path = Path(__file__).parent / "frontend.html"
#     if frontend_path.exists():
#         return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
#     return HTMLResponse("<h1>ClaimCompass</h1><p>frontend.html not found.</p>")



# """
# ClaimCompass — FastAPI Server (Day 5/6).

# Endpoints:
#   GET  /                    → serves the frontend HTML
#   POST /api/parse-acord     → upload ACORD PDF, returns claim record + checklist + state
#   POST /api/upload-document → upload follow-up doc, returns classification + updated checklist + state + evidence chain
#   GET  /api/state           → current claim state (in-memory session)
#   POST /api/reset           → reset to fresh state

# In-memory session: one claim at a time (demo scope). No database.
# """

# from __future__ import annotations

# import json
# import shutil
# import tempfile
# from datetime import date, datetime
# from pathlib import Path
# from typing import Optional

# from fastapi import FastAPI, File, Form, UploadFile
# from fastapi.responses import HTMLResponse, JSONResponse
# from fastapi.middleware.cors import CORSMiddleware

# from app.acord_parser import parse_acord
# from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
# from app.classifier import classify_document, apply_document_to_checklist, ClassificationResult
# from app.evidence_chain import EvidenceChain, EvidenceChainEntry, ChecklistChange
# from app.state_classifier import classify_state, build_state_transition, ClaimState
# from app.schemas import ClaimRecord

# app = FastAPI(title="ClaimCompass", version="0.1.0")
# app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# # --------------------------------------------------------------------------
# # In-memory session state (one claim at a time for demo)
# # --------------------------------------------------------------------------
# class Session:
#     record: Optional[ClaimRecord] = None
#     checklist: Optional[EvidenceChecklist] = None
#     chain: EvidenceChain = EvidenceChain()
#     as_of_date: date = date.today()

# session = Session()


# def _record_to_dict(r: ClaimRecord) -> dict:
#     return {
#         "claim_fingerprint": r.claim_fingerprint,
#         "form_completion_date": str(r.form_completion_date) if r.form_completion_date else None,
#         "date_of_loss": str(r.date_of_loss) if r.date_of_loss else None,
#         "time_of_loss": str(r.time_of_loss) if r.time_of_loss else None,
#         "policy_number": r.policy_number,
#         "carrier_name": r.carrier_name,
#         "carrier_naic_code": r.carrier_naic_code,
#         "insured_location_code": r.insured_location_code,
#         "liability_type": r.liability_type.value,
#         "premises_role": r.premises_role.value,
#         "premises_type": r.premises_type,
#         "products_role": r.products_role.value,
#         "product_description": r.product_description,
#         "insured_name": r.insured_name,
#         "property_owner_name": r.property_owner_name,
#         "product_manufacturer_name": r.product_manufacturer_name,
#         "loss_location_city": r.loss_location_city,
#         "loss_location_state": r.loss_location_state,
#         "loss_location_description": r.loss_location_description,
#         "loss_description": r.loss_description,
#         "authority_name": r.authority_contacted.authority_name,
#         "report_number": r.authority_contacted.report_number,
#         "injured_party": {
#             "full_name": r.injured_party.full_name,
#             "age": r.injured_party.age,
#             "occupation": r.injured_party.occupation,
#             "injury_description": r.injured_party.injury_description,
#             "treatment_location": r.injured_party.treatment_location,
#         },
#         "property_damage": {
#             "description": r.property_damage.description,
#             "estimated_amount": r.property_damage.estimated_amount,
#         },
#         "witness_count": r.witness_count,
#         "extraction_path": r.extraction_path.value,
#         "populated_fields": r.populated_field_count(),
#     }


# def _checklist_to_dict(cl: EvidenceChecklist) -> list[dict]:
#     return [
#         {
#             "id": item.id,
#             "label": item.label,
#             "category": item.category.value,
#             "priority": item.priority.value,
#             "expectedByDay": item.expected_by_day,
#             "status": item.status.value,
#             "reason": item.status_reason,
#         }
#         for item in cl.items
#     ]


# def _state_to_dict(sc) -> dict:
#     return {
#         "state": sc.state.value,
#         "rule": sc.rule_result.rule_name,
#         "reason": sc.rule_result.reason,
#         "conditions": [
#             {"condition": c, "satisfied": s}
#             for c, s in zip(sc.rule_result.conditions, sc.rule_result.satisfied)
#         ],
#         "nextActions": sc.next_actions,
#         "trajectorySignals": sc.trajectory_signals,
#         "elapsedDays": sc.elapsed_days,
#     }


# def _chain_to_dict(chain: EvidenceChain) -> list[dict]:
#     entries = []
#     for e in chain.entries:
#         entry = {
#             "document": e.trigger_document,
#             "docType": e.trigger_doc_type,
#             "confidence": e.trigger_confidence,
#             "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
#             "checklistChanges": [
#                 {"itemId": c.item_id, "label": c.item_label, "oldStatus": c.old_status, "newStatus": c.new_status}
#                 for c in e.checklist_changes
#             ],
#             "stateChange": None,
#         }
#         if e.state_transition:
#             entry["stateChange"] = {
#                 "oldState": e.state_transition.old_state,
#                 "newState": e.state_transition.new_state,
#                 "rule": e.state_transition.rule_name,
#                 "reason": e.state_transition.reason,
#             }
#         entries.append(entry)
#     return entries


# def _build_full_response() -> dict:
#     if not session.record:
#         return {"error": "No claim loaded. Upload an ACORD form first."}
#     sc = classify_state(session.record, session.checklist)

#     # Trust Anchors
#     from app.trust_anchors import validate_naic, get_tx_doi
#     naic_result = validate_naic(session.record.carrier_naic_code)
#     tx_doi = get_tx_doi()
#     tx_doi_result = tx_doi.lookup(
#         carrier_name=session.record.carrier_name,
#         naic_code=session.record.carrier_naic_code,
#     )

#     return {
#         "record": _record_to_dict(session.record),
#         "checklist": _checklist_to_dict(session.checklist),
#         "state": _state_to_dict(sc),
#         "evidenceChain": _chain_to_dict(session.chain),
#         "trustAnchors": {
#             "naicValidation": naic_result.to_dict(),
#             "txDOI": tx_doi_result.to_dict(),
#         },
#     }


# # --------------------------------------------------------------------------
# # Endpoints
# # --------------------------------------------------------------------------

# @app.post("/api/parse-acord")
# async def parse_acord_endpoint(file: UploadFile = File(...)):
#     """Upload an ACORD Form 3 PDF. Resets the session."""
#     with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
#         shutil.copyfileobj(file.file, tmp)
#         tmp_path = Path(tmp.name)

#     try:
#         record = parse_acord(tmp_path)
#         checklist = generate_checklist(record, as_of_date=session.as_of_date)
#         chain = EvidenceChain(claim_fingerprint=record.claim_fingerprint)

#         # Initial state classification
#         sc = classify_state(record, checklist)
#         transition = build_state_transition(None, sc)

#         initial_entry = EvidenceChainEntry(
#             timestamp=datetime.now(),
#             trigger_document=file.filename or "acord_upload.pdf",
#             trigger_doc_type="acord_form_3",
#             trigger_confidence="high",
#             state_transition=transition,
#         )
#         chain.add_entry(initial_entry)

#         # Store in session
#         session.record = record
#         session.checklist = checklist
#         session.chain = chain

#         return JSONResponse(_build_full_response())
#     finally:
#         tmp_path.unlink(missing_ok=True)


# @app.post("/api/upload-document")
# async def upload_document_endpoint(
#     file: UploadFile = File(None),
#     doc_type: str = Form(None),
#     doc_name: str = Form(None),
# ):
#     """Upload a follow-up document or simulate one by doc_type."""
#     if not session.record:
#         return JSONResponse({"error": "No claim loaded."}, status_code=400)

#     filename = doc_name or (file.filename if file else f"{doc_type}_{datetime.now().strftime('%H%M%S')}")

#     if file:
#         # Preserve the original file extension so the classifier handles
#         # .txt, .pdf, etc. correctly instead of forcing everything to .pdf
#         orig_name = file.filename or "upload"
#         suffix = Path(orig_name).suffix or ".pdf"
#         with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = Path(tmp.name)
#         # Rename to preserve original filename for classifier's filename-matching
#         named_path = tmp_path.parent / orig_name
#         try:
#             tmp_path.rename(named_path)
#         except (OSError, FileExistsError):
#             named_path = tmp_path  # fallback if rename fails
#         try:
#             classification = classify_document(named_path)
#         finally:
#             named_path.unlink(missing_ok=True)
#             tmp_path.unlink(missing_ok=True)
#     elif doc_type:
#         # Simulate: create a ClassificationResult directly
#         from app.classifier import DocType, ClassificationPath, DOC_TO_CHECKLIST
#         try:
#             dt = DocType(doc_type)
#         except ValueError:
#             return JSONResponse({"error": f"Unknown doc_type: {doc_type}"}, status_code=400)
#         classification = ClassificationResult(
#             doc_type=dt,
#             confidence="high",
#             classification_path=ClassificationPath.KEYWORD_HEURISTIC,
#         )
#     else:
#         return JSONResponse({"error": "Provide either a file or doc_type."}, status_code=400)

#     # Apply to checklist
#     old_state = session.chain.current_state
#     changes = apply_document_to_checklist(session.checklist, classification, filename)

#     # Re-classify state
#     sc = classify_state(session.record, session.checklist)
#     transition = build_state_transition(old_state, sc)

#     # Log to evidence chain
#     entry = EvidenceChainEntry(
#         timestamp=datetime.now(),
#         trigger_document=filename,
#         trigger_doc_type=classification.doc_type.value,
#         trigger_confidence=classification.confidence,
#         checklist_changes=changes,
#         state_transition=transition,
#     )
#     session.chain.add_entry(entry)

#     return JSONResponse(_build_full_response())


# @app.get("/api/state")
# async def get_state():
#     return JSONResponse(_build_full_response())


# @app.post("/api/reset")
# async def reset():
#     session.record = None
#     session.checklist = None
#     session.chain = EvidenceChain()
#     return JSONResponse({"status": "reset"})


# # --------------------------------------------------------------------------
# # Serve frontend
# # --------------------------------------------------------------------------

# @app.get("/", response_class=HTMLResponse)
# async def serve_frontend():
#     frontend_path = Path(__file__).parent / "frontend.html"
#     if frontend_path.exists():
#         return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
#     return HTMLResponse("<h1>ClaimCompass</h1><p>frontend.html not found.</p>")



"""
ClaimCompass — FastAPI Server (Day 5/6).

Endpoints:
  GET  /                    → serves the frontend HTML
  POST /api/parse-acord     → upload ACORD PDF, returns claim record + checklist + state
  POST /api/upload-document → upload follow-up doc, returns classification + updated checklist + state + evidence chain
  GET  /api/state           → current claim state (in-memory session)
  POST /api/reset           → reset to fresh state

In-memory session: one claim at a time (demo scope). No database.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.acord_parser import parse_acord
from app.checklist import EvidenceChecklist, EvidenceStatus, generate_checklist
from app.classifier import classify_document, apply_document_to_checklist, ClassificationResult
from app.evidence_chain import EvidenceChain, EvidenceChainEntry, ChecklistChange
from app.state_classifier import classify_state, build_state_transition, ClaimState
from app.schemas import ClaimRecord

app = FastAPI(title="ClaimCompass", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --------------------------------------------------------------------------
# In-memory session state (one claim at a time for demo)
# --------------------------------------------------------------------------
class Session:
    record: Optional[ClaimRecord] = None
    checklist: Optional[EvidenceChecklist] = None
    chain: EvidenceChain = EvidenceChain()
    as_of_date: date = date.today()

session = Session()


def _record_to_dict(r: ClaimRecord) -> dict:
    return {
        "claim_fingerprint": r.claim_fingerprint,
        "form_completion_date": str(r.form_completion_date) if r.form_completion_date else None,
        "date_of_loss": str(r.date_of_loss) if r.date_of_loss else None,
        "time_of_loss": str(r.time_of_loss) if r.time_of_loss else None,
        "policy_number": r.policy_number,
        "carrier_name": r.carrier_name,
        "carrier_naic_code": r.carrier_naic_code,
        "insured_location_code": r.insured_location_code,
        "liability_type": r.liability_type.value,
        "premises_role": r.premises_role.value,
        "premises_type": r.premises_type,
        "products_role": r.products_role.value,
        "product_description": r.product_description,
        "insured_name": r.insured_name,
        "property_owner_name": r.property_owner_name,
        "product_manufacturer_name": r.product_manufacturer_name,
        "loss_location_city": r.loss_location_city,
        "loss_location_state": r.loss_location_state,
        "loss_location_description": r.loss_location_description,
        "loss_description": r.loss_description,
        "authority_name": r.authority_contacted.authority_name,
        "report_number": r.authority_contacted.report_number,
        "injured_party": {
            "full_name": r.injured_party.full_name,
            "age": r.injured_party.age,
            "occupation": r.injured_party.occupation,
            "injury_description": r.injured_party.injury_description,
            "treatment_location": r.injured_party.treatment_location,
        },
        "property_damage": {
            "description": r.property_damage.description,
            "estimated_amount": r.property_damage.estimated_amount,
        },
        "witness_count": r.witness_count,
        "extraction_path": r.extraction_path.value,
        "populated_fields": r.populated_field_count(),
    }


def _checklist_to_dict(cl: EvidenceChecklist) -> list[dict]:
    return [
        {
            "id": item.id,
            "label": item.label,
            "category": item.category.value,
            "priority": item.priority.value,
            "expectedByDay": item.expected_by_day,
            "status": item.status.value,
            "reason": item.status_reason,
        }
        for item in cl.items
    ]


def _state_to_dict(sc) -> dict:
    return {
        "state": sc.state.value,
        "rule": sc.rule_result.rule_name,
        "reason": sc.rule_result.reason,
        "conditions": [
            {"condition": c, "satisfied": s}
            for c, s in zip(sc.rule_result.conditions, sc.rule_result.satisfied)
        ],
        "nextActions": sc.next_actions,
        "trajectorySignals": sc.trajectory_signals,
        "elapsedDays": sc.elapsed_days,
    }


def _chain_to_dict(chain: EvidenceChain) -> list[dict]:
    entries = []
    for e in chain.entries:
        entry = {
            "document": e.trigger_document,
            "docType": e.trigger_doc_type,
            "confidence": e.trigger_confidence,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M"),
            "checklistChanges": [
                {"itemId": c.item_id, "label": c.item_label, "oldStatus": c.old_status, "newStatus": c.new_status}
                for c in e.checklist_changes
            ],
            "stateChange": None,
        }
        if e.state_transition:
            entry["stateChange"] = {
                "oldState": e.state_transition.old_state,
                "newState": e.state_transition.new_state,
                "rule": e.state_transition.rule_name,
                "reason": e.state_transition.reason,
            }
        entries.append(entry)
    return entries


def _build_full_response() -> dict:
    if not session.record:
        return {"error": "No claim loaded. Upload an ACORD form first."}
    sc = classify_state(session.record, session.checklist)

    # Trust Anchors
    from app.trust_anchors import validate_naic, get_tx_doi, lookup_cpsc_recalls
    naic_result = validate_naic(session.record.carrier_naic_code)
    tx_doi = get_tx_doi()
    tx_doi_result = tx_doi.lookup(
        carrier_name=session.record.carrier_name,
        naic_code=session.record.carrier_naic_code,
    )

    trust_anchors = {
        "naicValidation": naic_result.to_dict(),
        "txDOI": tx_doi_result.to_dict(),
    }

    # CPSC only for products liability claims
    from app.schemas import LiabilityType
    if session.record.liability_type in (LiabilityType.PRODUCTS, LiabilityType.BOTH):
        cpsc_result = lookup_cpsc_recalls(session.record.product_description)
        trust_anchors["cpsc"] = cpsc_result.to_dict()

        # Auto-resolve the recall_history checklist item
        if session.checklist:
            from app.checklist import EvidenceStatus
            for item in session.checklist.items:
                if item.id == "recall_history" and item.status != EvidenceStatus.PRESENT:
                    item.status = EvidenceStatus.PRESENT
                    if cpsc_result.found:
                        item.status_reason = (
                            f"CPSC recall search completed — {cpsc_result.recall_count} "
                            f"recall(s) found for '{cpsc_result.product_query}'. "
                            f"Source: {cpsc_result.source}"
                        )
                    else:
                        item.status_reason = (
                            f"CPSC recall search completed — no recalls found for "
                            f"'{cpsc_result.product_query}'. "
                            f"Source: {cpsc_result.source}"
                        )

    return {
        "record": _record_to_dict(session.record),
        "checklist": _checklist_to_dict(session.checklist),
        "state": _state_to_dict(sc),
        "evidenceChain": _chain_to_dict(session.chain),
        "trustAnchors": trust_anchors,
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.post("/api/parse-acord")
async def parse_acord_endpoint(file: UploadFile = File(...)):
    """Upload an ACORD Form 3 PDF. Resets the session."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        record = parse_acord(tmp_path)
        checklist = generate_checklist(record, as_of_date=session.as_of_date)
        chain = EvidenceChain(claim_fingerprint=record.claim_fingerprint)

        # Initial state classification
        sc = classify_state(record, checklist)
        transition = build_state_transition(None, sc)

        initial_entry = EvidenceChainEntry(
            timestamp=datetime.now(),
            trigger_document=file.filename or "acord_upload.pdf",
            trigger_doc_type="acord_form_3",
            trigger_confidence="high",
            state_transition=transition,
        )
        chain.add_entry(initial_entry)

        # Store in session
        session.record = record
        session.checklist = checklist
        session.chain = chain

        return JSONResponse(_build_full_response())
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/upload-document")
async def upload_document_endpoint(
    file: UploadFile = File(None),
    doc_type: str = Form(None),
    doc_name: str = Form(None),
):
    """Upload a follow-up document or simulate one by doc_type."""
    if not session.record:
        return JSONResponse({"error": "No claim loaded."}, status_code=400)

    filename = doc_name or (file.filename if file else f"{doc_type}_{datetime.now().strftime('%H%M%S')}")

    if file:
        # Preserve the original file extension so the classifier handles
        # .txt, .pdf, etc. correctly instead of forcing everything to .pdf
        orig_name = file.filename or "upload"
        suffix = Path(orig_name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
        # Rename to preserve original filename for classifier's filename-matching
        named_path = tmp_path.parent / orig_name
        try:
            tmp_path.rename(named_path)
        except (OSError, FileExistsError):
            named_path = tmp_path  # fallback if rename fails
        try:
            classification = classify_document(named_path)
        finally:
            named_path.unlink(missing_ok=True)
            tmp_path.unlink(missing_ok=True)
    elif doc_type:
        # Simulate: create a ClassificationResult directly
        from app.classifier import DocType, ClassificationPath, DOC_TO_CHECKLIST
        try:
            dt = DocType(doc_type)
        except ValueError:
            return JSONResponse({"error": f"Unknown doc_type: {doc_type}"}, status_code=400)
        classification = ClassificationResult(
            doc_type=dt,
            confidence="high",
            classification_path=ClassificationPath.KEYWORD_HEURISTIC,
        )
    else:
        return JSONResponse({"error": "Provide either a file or doc_type."}, status_code=400)

    # Apply to checklist
    old_state = session.chain.current_state
    changes = apply_document_to_checklist(session.checklist, classification, filename)

    # Re-classify state
    sc = classify_state(session.record, session.checklist)
    transition = build_state_transition(old_state, sc)

    # Log to evidence chain
    entry = EvidenceChainEntry(
        timestamp=datetime.now(),
        trigger_document=filename,
        trigger_doc_type=classification.doc_type.value,
        trigger_confidence=classification.confidence,
        checklist_changes=changes,
        state_transition=transition,
    )
    session.chain.add_entry(entry)

    return JSONResponse(_build_full_response())


@app.get("/api/state")
async def get_state():
    return JSONResponse(_build_full_response())


@app.post("/api/reset")
async def reset():
    session.record = None
    session.checklist = None
    session.chain = EvidenceChain()
    return JSONResponse({"status": "reset"})


# --------------------------------------------------------------------------
# Serve frontend + landing page + static files
# --------------------------------------------------------------------------

from fastapi.staticfiles import StaticFiles

# Mount static directory for video background
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    landing_path = Path(__file__).parent / "landing.html"
    if landing_path.exists():
        return HTMLResponse(landing_path.read_text(encoding="utf-8"))
    # Fall back to frontend if no landing page
    return await serve_frontend()

@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    frontend_path = Path(__file__).parent / "frontend.html"
    if frontend_path.exists():
        return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ClaimCompass</h1><p>frontend.html not found.</p>")