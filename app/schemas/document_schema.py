from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ==========================================
# 1. Initialize Upload Response
# ==========================================

class UploadInitializeResponse(BaseModel):
    """
    Information returned when an upload session is created.
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
    Information returned after one chunk is uploaded.
    """

    upload_id: str
    chunk_number: int
    received_chunks: int
    total_chunks: int
    status: str


# ==========================================
# 3. Document Information
# ==========================================

class DocumentResponse(BaseModel):
    """
    Final document information stored in Salesforce.
    """

    document_id: str

    application_id: Optional[str] = None

    file_name: str
    file_extension: Optional[str] = None
    file_size: Optional[int] = None
    upload_datetime: datetime

    document_type: str
    source: str

    verification_status: Optional[str] = None
    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None


# ==========================================
# 4. Complete Upload Response
# ==========================================

class UploadCompleteResponse(BaseModel):
    """
    Information returned after the complete document
    is uploaded to Salesforce.
    """

    upload_id: str
    application_no: str
    status: str
    document: DocumentResponse


# ==========================================
# 5. Update Document Verification
# ==========================================

class DocumentVerificationUpdate(BaseModel):
    """
    Update the verification status of a document.
    """

    verification_status: str

    rejection_reason: Optional[str] = None
    verified_by: Optional[str] = None
