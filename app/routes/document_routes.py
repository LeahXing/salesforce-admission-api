from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.schemas.document_schema import (
    DocumentVerificationUpdate,
)

from app.services.document_service import (
    initialize_document_upload,
    upload_document_chunk,
    complete_document_upload,
    verify_document,
)


# Create router for admission document endpoints
router = APIRouter(
    prefix="/admissions",
    tags=["Admission Documents"],
)


# ==========================================
# 1. Initialize Document Upload
# ==========================================

@router.post("/{application_no}/documents/uploads")
async def initialize_upload(
    application_no: str,
    file_name: str = Form(...),
    file_size: int = Form(...),
    total_chunks: int = Form(...),
    document_type: str = Form(...),
    source: str = Form(...),
):
    """
    Start a new document upload session
    and generate an upload_id.
    """

    try:
        # Validate file metadata
        if not file_name:
            raise HTTPException(
                status_code=400,
                detail="File name is required.",
            )

        if file_size <= 0:
            raise HTTPException(
                status_code=400,
                detail="File size must be greater than 0.",
            )

        if total_chunks <= 0:
            raise HTTPException(
                status_code=400,
                detail="Total chunks must be greater than 0.",
            )

        # Create upload session
        return initialize_document_upload(
            application_no=application_no,
            file_name=file_name,
            file_size=file_size,
            total_chunks=total_chunks,
            document_type=document_type,
            source=source,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 2. Upload Document Chunk
# ==========================================

@router.post(
    "/{application_no}/documents/uploads/{upload_id}/chunks"
)
async def upload_chunk(
    application_no: str,
    upload_id: str,
    chunk_number: int = Form(...),
    file: UploadFile = File(...),
):
    """
    Receive and temporarily store one chunk
    of the document.
    """

    try:
        # Read the current chunk
        chunk_content = await file.read()

        # Validate chunk
        if chunk_number <= 0:
            raise HTTPException(
                status_code=400,
                detail="Chunk number must be greater than 0.",
            )

        if not chunk_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded chunk is empty.",
            )

        # Save chunk
        return upload_document_chunk(
            application_no=application_no,
            upload_id=upload_id,
            chunk_number=chunk_number,
            chunk_content=chunk_content,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 3. Complete Document Upload
# ==========================================

@router.post(
    "/{application_no}/documents/uploads/{upload_id}/complete"
)
async def complete_upload(
    application_no: str,
    upload_id: str,
):
    """
    Verify all chunks, reassemble the file,
    and upload the completed document to Salesforce.
    """

    try:
        return complete_document_upload(
            application_no=application_no,
            upload_id=upload_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 4. Update Document Verification
# ==========================================

@router.patch(
    "/documents/{document_id}/verification"
)
async def update_document_verification(
    document_id: str,
    verification: DocumentVerificationUpdate,
):
    """
    Update document verification status.

    Supported statuses:
    - Pending
    - Verified
    - Rejected
    """

    try:
        return verify_document(
            content_version_id=document_id,
            verification_status=verification.verification_status,
            rejection_reason=verification.rejection_reason,
            verified_by=verification.verified_by,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
