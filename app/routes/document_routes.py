"""FastAPI routes for Salesforce admissions document management.

Preserves document retrieval and manual verification while providing single-file
verification and caller-supplied application eligibility evaluation.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.schemas.document_schema import (
    DocumentResponse,
    DocumentVerificationUpdate,
)
from app.services.document_service import (
    list_documents,
    get_document,
    download_document,
    verify_document,
    upload_and_verify_document,
    evaluate_application_documents,
)

router = APIRouter(prefix="/admissions", tags=["Admission Documents"])

# This is intentionally not read from Salesforce: the current repository does
# not persist the structured validation evidence required to re-evaluate it.
class EligibilityEvaluationRequest(BaseModel):
    document_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Current validation results for this application, not raw ContentVersion rows.",
    )


def _error(exc: Exception, *, not_found: bool = False) -> HTTPException:
    if isinstance(exc, ValueError):
        message = str(exc)
        if not_found or "was not found" in message or "not found" in message:
            return HTTPException(status_code=404, detail=message)
        return HTTPException(status_code=400, detail=message)
    # Avoid exposing Salesforce credentials, request payloads, or stack traces.
    return HTTPException(status_code=500, detail="Document service operation failed.")


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
        # RFC 5987 encoding avoids unsafe quotes/newlines in response headers.
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
    """Manually update verification status.

    The DocumentVerificationUpdate schema must permit PASSED, FAILED and
    REVIEW_REQUIRED; legacy Salesforce statuses may also be supported.
    """
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
    """Upload one PDF and return extraction, verification and eligibility feedback.

    This endpoint does not approve admission or generate an offer letter.
    """
    file_name = Path(file.filename or "").name
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF file with a .pdf extension.")
    try:
        # Read at most one byte beyond the limit to reject oversized uploads.
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="PDF exceeds the 10 MB upload limit.")
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
        return upload_and_verify_document(
            application_no=application_no,
            file_name=file_name,
            file_content=content,
            document_type=document_type,
            source=source,
        )
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
    """Evaluate supplied current validation evidence; does not read historic scores.

    The caller must supply results belonging to this application. A persisted,
    authenticated eligibility endpoint requires a structured Salesforce store.
    """
    try:
        return evaluate_application_documents(
            application_no=application_no,
            document_results=payload.document_results,
        )
    except Exception as exc:
        raise _error(exc) from exc
