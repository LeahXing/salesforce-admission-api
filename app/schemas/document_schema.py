"""Schemas for Salesforce admissions document APIs.

Replace only after checking any other imports from your existing schema file.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VerificationStatus = Literal["PASSED", "REVIEW_REQUIRED", "FAILED"]


class DocumentResponse(BaseModel):
    document_id: str
    application_id: str | None = None
    file_name: str
    file_extension: str | None = None
    file_size: int | None = None
    upload_datetime: datetime | str | None = None
    document_type: str
    source: str
    verification_status: str | None = None
    failed_reason: str | None = None
    verified_by: str | None = None
    verified_at: datetime | str | None = None


class DocumentVerificationUpdate(BaseModel):
    verification_status: VerificationStatus
    failed_reason: str | None = None
    verified_by: str | None = None


class DocumentUploadVerificationResponse(BaseModel):
    application_no: str
    document_type: str
    verification_status: VerificationStatus
    requirement_status: str
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    message: str
    action_required: str | None = None
    document: DocumentResponse | dict[str, Any]
