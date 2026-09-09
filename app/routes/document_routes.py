# ==========================================
# Document Routes
# ==========================================

import mimetypes

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Response,
)

from app.schemas.document_schema import (
    DocumentResponse,
    UploadInitializeResponse,
    ChunkUploadResponse,
    UploadCompleteResponse,
    DocumentVerificationUpdate,
)

from app.services.document_service import (
    list_documents,
    get_document,
    download_document,
    initialize_document_upload,
    upload_document_chunk,
    complete_document_upload,
    verify_document,
)


# ==========================================
# Router
# ==========================================

router = APIRouter(
    prefix="/admissions",
    tags=["Admission Documents"],
)


# ==========================================
# 1. Get Documents for Application
# ==========================================

@router.get(
    "/{application_no}/documents",
    response_model=list[DocumentResponse],
)
def get_application_documents(
    application_no: str,
):
    """
    Get all uploaded documents for
    one admission application.
    """

    try:
        return list_documents(
            application_no
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 2. Get One Document Metadata
# ==========================================

@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_admission_document(
    document_id: str,
):
    """
    Get metadata for one document.
    """

    try:
        return get_document(
            document_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 3. Get Actual Document Content
# ==========================================

@router.get(
    "/documents/{document_id}/content"
)
def view_document(
    document_id: str,
):
    """
    Return actual PDF/image content so the
    frontend can display the document.
    """

    try:
        document = download_document(
            document_id
        )

        file_content = document[
            "file_content"
        ]

        file_name = document[
            "file_name"
        ]

        # Detect MIME type from filename
        media_type, _ = mimetypes.guess_type(
            file_name
        )

        if media_type is None:
            media_type = (
                "application/octet-stream"
            )

        return Response(
            content=file_content,
            media_type=media_type,
            headers={
                "Content-Disposition":
                    f'inline; filename="{file_name}"'
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# 4. Initialize Document Upload
# ==========================================

@router.post(
    "/{application_no}/documents/uploads",
    response_model=UploadInitializeResponse,
)
async def initialize_upload(
    application_no: str,
    file_name: str = Form(...),
    file_size: int = Form(...),
    total_chunks: int = Form(...),
    document_type: str = Form(...),
    source: str = Form(...),
):
    """
    Start a new document upload session.
    """

    try:
        if not file_name:
            raise HTTPException(
                status_code=400,
                detail="File name is required.",
            )

        if file_size <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "File size must be "
                    "greater than 0."
                ),
            )

        if total_chunks <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Total chunks must be "
                    "greater than 0."
                ),
            )

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
# 5. Upload Document Chunk
# ==========================================

@router.post(
    "/{application_no}/documents/"
    "uploads/{upload_id}/chunks",
    response_model=ChunkUploadResponse,
)
async def upload_chunk(
    application_no: str,
    upload_id: str,
    chunk_number: int = Form(...),
    file: UploadFile = File(...),
):
    """
    Receive and temporarily store
    one document chunk.
    """

    try:
        chunk_content = await file.read()

        if chunk_number <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Chunk number must be "
                    "greater than 0."
                ),
            )

        if not chunk_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded chunk is empty.",
            )

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
# 6. Complete Document Upload
# ==========================================

@router.post(
    "/{application_no}/documents/"
    "uploads/{upload_id}/complete",
    response_model=UploadCompleteResponse,
)
async def complete_upload(
    application_no: str,
    upload_id: str,
):
    """
    Reassemble all chunks and upload
    completed document to Salesforce.
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
# 7. Update Document Verification
# ==========================================

@router.patch(
    "/documents/{document_id}/verification",
    response_model=DocumentResponse,
)
def update_document_verification_status(
    document_id: str,
    verification: DocumentVerificationUpdate,
):
    """
    Set document verification status to
    Pending, Verified, or Rejected.
    """

    try:
        return verify_document(
            content_version_id=document_id,
            verification_status=(
                verification.verification_status
            ),
            rejection_reason=(
                verification.rejection_reason
            ),
            verified_by=(
                verification.verified_by
            ),
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
