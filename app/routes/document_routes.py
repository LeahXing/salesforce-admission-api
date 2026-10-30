"""FastAPI routes for Salesforce admission document management.

Upload responses are intentionally concise. Document extraction, validation,
Salesforce file storage, history and eligibility updates remain in the service.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.schemas.document_schema import DocumentResponse, DocumentVerificationUpdate
from app.services.document_service import (
    list_documents,
    get_document,
    download_document,
    verify_document,
    upload_and_verify_document,
    evaluate_application_documents,
    evaluate_and_save_application_documents,
)

router = APIRouter(prefix="/admissions", tags=["Admission Documents"])
MAX_PDF_BYTES = 10 * 1024 * 1024


class EligibilityEvaluationRequest(BaseModel):
    """Current trusted document validation evidence, not ContentVersion rows."""

    document_results: list[dict[str, Any]] = Field(default_factory=list)


def _error(exc: Exception, *, not_found: bool = False) -> HTTPException:
    if isinstance(exc, ValueError):
        message = str(exc)
        if not_found or "was not found" in message or "not found" in message:
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail="Document service operation failed.")


def _first_present(*values: Any) -> Any:
    """Return the first non-None value (zero is a valid score)."""
    return next((value for value in values if value is not None), None)


def _score_fields(dtype: str | None, extracted: dict, validation: dict) -> dict:
    if dtype == "CLASS_12_MARKSHEET":
        return {
            "extracted_percentage": extracted.get("percentage"),
            "minimum_required_percentage": 70.0,
        }
    if dtype == "UNDERGRADUATE_TRANSCRIPT":
        return {
            "extracted_gpa": _first_present(extracted.get("overall_gpa"), extracted.get("extracted_gpa")),
            "minimum_required_gpa": 3.2,
        }
    if dtype == "IELTS":
        return {
            "extracted_score": _first_present(extracted.get("overall_band"), extracted.get("score"), validation.get("extracted_score")),
            "minimum_required_score": 6.5,
        }
    thresholds = {"SAT": 1100, "GRE": 290, "GMAT": 600, "TOEFL": 72}
    if dtype in thresholds:
        return {
            "extracted_score": _first_present(validation.get("extracted_score"), extracted.get("score"), extracted.get("total_score")),
            "minimum_required_score": thresholds[dtype],
        }
    return {}


def _missing_documents(evaluation: dict) -> list[str]:
    missing = []
    for requirement in evaluation.get("requirements") or []:
        if requirement.get("status") != "MISSING":
            continue
        allowed = requirement.get("accepted_document_types") or []
        if allowed:
            missing.append("_OR_".join(allowed))
    return missing


def _compact_upload_response(result: dict[str, Any]) -> dict[str, Any]:
    extracted = result.get("extracted_data") or {}
    validation = result.get("validation") or {}
    evaluation = result.get("application_evaluation") or {}
    document = result.get("document") or {}
    salesforce_update = result.get("salesforce_update") or {}
    dtype = result.get("document_type")

    # Only use explicit active state; validation PASSED does not prove active.
    is_active = result.get("is_active")
    response = {
        "application_no": result.get("application_no"),
        "document_id": document.get("document_id"),
        "document_type": dtype,
        "detected_document_type": _first_present(
            validation.get("detected_document_type"),
            extracted.get("detected_document_type"),
            extracted.get("academic_level"),
        ),
        **_score_fields(dtype, extracted, validation),
        "validation_status": _first_present(
            result.get("validation_status"),
            validation.get("validation_status"),
            validation.get("verification_status"),
        ),
        "is_active": is_active,
        "reason_codes": validation.get("reason_codes") or [],
        "message": result.get("message") or validation.get("message"),
        "action_required": result.get("action_required") or validation.get("action_required"),
        "course_eligibility": result.get("course_eligibility") or evaluation.get("course_eligibility"),
        "missing_documents": _missing_documents(evaluation),
        "salesforce_updated": salesforce_update.get("document_results_saved") is True,
    }
    return response


@router.get("/{application_no}/documents", response_model=list[DocumentResponse])
def get_application_documents(application_no: str):
    try:
        return list_documents(application_no)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_admission_document(document_id: str):
    try:
        return get_document(document_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/documents/{document_id}/content")
def view_document(document_id: str):
    from fastapi import Response

    try:
        document = download_document(document_id)
        file_name = Path(document["file_name"]).name
        media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        disposition = f"inline; filename*=UTF-8''{quote(file_name, safe='')}"
        return Response(
            content=document["file_content"],
            media_type=media_type,
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/documents/{document_id}/verification", response_model=DocumentResponse)
def update_document_verification_status(
    document_id: str,
    verification: DocumentVerificationUpdate,
):
    try:
        return verify_document(
            content_version_id=document_id,
            verification_status=verification.verification_status,
            failed_reason=verification.failed_reason,
            verified_by=verification.verified_by,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/{application_no}/documents/upload-and-verify")
async def upload_document_and_verify(
    application_no: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    source: str = Form("API"),
):
    """Upload and validate one PDF; return concise feedback.

    Does not approve admission or issue an offer letter.
    """
    file_name = Path(file.filename or "").name
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF file with a .pdf extension.")
    try:
        content = await file.read(MAX_PDF_BYTES + 1)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="PDF exceeds the 10 MB upload limit.")
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
        result = upload_and_verify_document(
            application_no=application_no,
            file_name=file_name,
            file_content=content,
            document_type=document_type,
            source=source,
        )
        return _compact_upload_response(result)
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await file.close()


@router.post("/{application_no}/documents/evaluate-eligibility")
def evaluate_document_eligibility(
    application_no: str,
    payload: EligibilityEvaluationRequest,
):
    try:
        return evaluate_application_documents(
            application_no=application_no,
            document_results=payload.document_results,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/{application_no}/documents/evaluate-and-save")
def evaluate_and_save_document_eligibility(
    application_no: str,
    payload: EligibilityEvaluationRequest,
):
    """Controlled demo endpoint; service decides whether writes are permitted."""
    try:
        return evaluate_and_save_application_documents(
            application_no=application_no,
            document_results=payload.document_results,
        )
    except Exception as exc:
        raise _error(exc) from exc
