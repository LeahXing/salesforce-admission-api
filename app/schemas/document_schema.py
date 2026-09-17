# ==========================================
# Document Schemas
# ==========================================

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ==========================================
# 1. Initialize Upload Response
# ==========================================

class UploadInitializeResponse(BaseModel):
    """
    Information returned when an upload
    session is created.
    """

    upload_id: str
    application_no: str
    file_name: str
    total_chunks: int
    status: str


# ==========================================
# 2. Chunk Upload Response
# ==========================================

class ChunkUploadResponse(BaseModel):
    """
    Information returned after one chunk
    is uploaded.
    """

    upload_id: str
    chunk_number: int
    received_chunks: int
    total_chunks: int
    status: str


# ==========================================
# 3. Document Response
# ==========================================

class DocumentResponse(BaseModel):
    """
    Document metadata returned by the API.
    """

    document_id: str
    application_id: Optional[str] = None

    file_name: str
    file_extension: Optional[str] = None
    file_size: Optional[int] = None
    upload_datetime: datetime

    document_type: str
    source: str

    # Document verification result
    verification_status: Optional[str] = None

    # Document eligibility result
    eligibility_status: Optional[str] = None

    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None


# ==========================================
# 4. Complete Upload Response
# ==========================================

class UploadCompleteResponse(BaseModel):
    """
    Information returned after the completed
    document is automatically reviewed and
    uploaded to Salesforce.
    """

    upload_id: str
    application_no: str
    status: str

    # Automatic evaluation results
    verification_status: str
    eligibility_status: str

    # Extracted academic score
    score: Optional[float] = None
    score_method: Optional[str] = None

    document: DocumentResponse


# ==========================================
# 5. Update Document Verification
# ==========================================

class DocumentVerificationUpdate(BaseModel):
    """
    Request body for manually updating
    document verification.

    Supported verification statuses:
        Missing
        Verified
        Rejected

    Eligibility is derived automatically:
        Missing  -> PENDING_DOCUMENTS
        Verified -> ELIGIBLE
        Rejected -> NOT_ELIGIBLE
    """

    verification_status: str
    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None