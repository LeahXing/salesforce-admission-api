import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.repositories.salesforce_document_repository import (
    get_customer_by_application_no,
    create_document,
    get_document_by_id,
    update_document_verification,
)


# ==========================================
# Temporary Upload Storage
# ==========================================

UPLOAD_DIR = Path("temp_uploads")

# Create temporary upload directory if needed
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# Helper: Format Salesforce Document
# ==========================================

def format_document_response(document):
    """
    Convert Salesforce ContentVersion fields
    into API response fields.
    """

    return {
        "document_id": document["Id"],
        "application_id": document.get("Application__c"),

        "file_name": document["PathOnClient"],
        "file_extension": document.get("FileExtension"),
        "file_size": document.get("ContentSize"),
        "upload_datetime": document["CreatedDate"],

        "document_type": document["Document_Type__c"],
        "source": document["Source__c"],

        "verification_status": document.get(
            "Verification_Status__c"
        ),
        "rejection_reason": document.get(
            "Rejection_Reason__c"
        ),
        "verified_by": document.get(
            "Verified_By__c"
        ),
        "verified_at": document.get(
            "Verified_At__c"
        ),
    }


# ==========================================
# 1. Initialize Document Upload
# ==========================================

def initialize_document_upload(
    application_no: str,
    file_name: str,
    file_size: int,
    total_chunks: int,
    document_type: str,
    source: str,
):
    """
    Create a new upload session for a document.
    """

    # Verify that the admission application exists
    customer = get_customer_by_application_no(
        application_no
    )

    if customer is None:
        raise ValueError(
            f"Application {application_no} was not found."
        )

    if file_size <= 0:
        raise ValueError(
            "File size must be greater than 0."
        )

    if total_chunks <= 0:
        raise ValueError(
            "Total chunks must be greater than 0."
        )

    # Generate unique upload session ID
    upload_id = str(uuid.uuid4())

    # Create temporary folder for this upload
    upload_path = UPLOAD_DIR / upload_id
    upload_path.mkdir(
        parents=True,
        exist_ok=False,
    )

    # Store upload metadata
    metadata = {
        "upload_id": upload_id,
        "application_no": application_no,
        "customer_id": customer["Id"],
        "file_name": file_name,
        "file_size": file_size,
        "total_chunks": total_chunks,
        "document_type": document_type,
        "source": source,
        "status": "initiated",
    }

    metadata_path = upload_path / "metadata.json"

    with open(metadata_path, "w") as f:
        json.dump(
            metadata,
            f,
            indent=4,
        )

    return {
        "upload_id": upload_id,
        "application_no": application_no,
        "file_name": file_name,
        "total_chunks": total_chunks,
        "status": "initiated",
    }


# ==========================================
# 2. Upload Document Chunk
# ==========================================

def upload_document_chunk(
    application_no: str,
    upload_id: str,
    chunk_number: int,
    chunk_content: bytes,
):
    """
    Save one uploaded file chunk temporarily.
    """

    upload_path = UPLOAD_DIR / upload_id
    metadata_path = upload_path / "metadata.json"

    # Verify upload session exists
    if not metadata_path.exists():
        raise ValueError(
            f"Upload session {upload_id} was not found."
        )

    # Load upload metadata
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Verify application
    if metadata["application_no"] != application_no:
        raise ValueError(
            "Upload session does not belong "
            "to this application."
        )

    total_chunks = metadata["total_chunks"]

    # Validate chunk number
    if (
        chunk_number < 1
        or chunk_number > total_chunks
    ):
        raise ValueError(
            f"Chunk number must be between "
            f"1 and {total_chunks}."
        )

    # Save chunk
    chunk_path = (
        upload_path /
        f"chunk_{chunk_number}"
    )

    with open(chunk_path, "wb") as f:
        f.write(chunk_content)

    # Update upload status
    metadata["status"] = "uploading"

    with open(metadata_path, "w") as f:
        json.dump(
            metadata,
            f,
            indent=4,
        )

    # Count received chunks
    received_chunks = len(
        list(
            upload_path.glob("chunk_*")
        )
    )

    return {
        "upload_id": upload_id,
        "chunk_number": chunk_number,
        "received_chunks": received_chunks,
        "total_chunks": total_chunks,
        "status": "uploaded",
    }


# ==========================================
# 3. Complete Document Upload
# ==========================================

def complete_document_upload(
    application_no: str,
    upload_id: str,
):
    """
    Reassemble all chunks and upload one
    completed document to Salesforce.
    """

    upload_path = UPLOAD_DIR / upload_id
    metadata_path = upload_path / "metadata.json"

    # Verify upload session exists
    if not metadata_path.exists():
        raise ValueError(
            f"Upload session {upload_id} was not found."
        )

    # Load upload metadata
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Verify application
    if metadata["application_no"] != application_no:
        raise ValueError(
            "Upload session does not belong "
            "to this application."
        )

    total_chunks = metadata["total_chunks"]

    # Verify every expected chunk exists
    missing_chunks = []

    for chunk_number in range(
        1,
        total_chunks + 1,
    ):
        chunk_path = (
            upload_path /
            f"chunk_{chunk_number}"
        )

        if not chunk_path.exists():
            missing_chunks.append(
                chunk_number
            )

    if missing_chunks:
        raise ValueError(
            f"Missing chunks: {missing_chunks}"
        )

    # Reassemble chunks
    completed_file_path = (
        upload_path /
        "completed_file"
    )

    with open(
        completed_file_path,
        "wb",
    ) as completed_file:

        for chunk_number in range(
            1,
            total_chunks + 1,
        ):
            chunk_path = (
                upload_path /
                f"chunk_{chunk_number}"
            )

            with open(
                chunk_path,
                "rb",
            ) as chunk_file:

                shutil.copyfileobj(
                    chunk_file,
                    completed_file,
                )

    # Verify completed file size
    actual_file_size = (
        completed_file_path
        .stat()
        .st_size
    )

    expected_file_size = metadata[
        "file_size"
    ]

    if actual_file_size != expected_file_size:
        raise ValueError(
            "Completed file size does not match "
            f"the expected size. "
            f"Expected {expected_file_size} bytes, "
            f"received {actual_file_size} bytes."
        )

    # Read completed file
    with open(
        completed_file_path,
        "rb",
    ) as f:
        file_content = f.read()

    # Upload ONE completed document
    result = create_document(
        customer_id=metadata["customer_id"],
        file_name=metadata["file_name"],
        file_content=file_content,
        document_type=metadata["document_type"],
        source=metadata["source"],
    )

    content_version_id = result["id"]

    # Get Salesforce document metadata
    document = get_document_by_id(
        content_version_id
    )

    # Format Salesforce fields for API response
    document_response = (
        format_document_response(
            document
        )
    )

    # Delete temporary chunks after success
    shutil.rmtree(upload_path)

    return {
        "upload_id": upload_id,
        "application_no": application_no,
        "status": "completed",
        "document": document_response,
    }


# ==========================================
# 4. Update Document Verification
# ==========================================

def verify_document(
    content_version_id: str,
    verification_status: str,
    rejection_reason: str | None = None,
    verified_by: str | None = None,
):
    """
    Verify or reject an uploaded document.
    """

    allowed_statuses = {
        "Pending",
        "Verified",
        "Rejected",
    }

    if verification_status not in allowed_statuses:
        raise ValueError(
            "Verification status must be "
            "Pending, Verified, or Rejected."
        )

    # Rejection requires a reason
    if (
        verification_status == "Rejected"
        and not rejection_reason
    ):
        raise ValueError(
            "Rejection reason is required "
            "when a document is rejected."
        )

    # Verify document exists
    document = get_document_by_id(
        content_version_id
    )

    if document is None:
        raise ValueError(
            f"Document {content_version_id} "
            "was not found."
        )

    verification_data = {
        "Verification_Status__c":
            verification_status,
    }

    # Verified / Rejected
    if verification_status in {
        "Verified",
        "Rejected",
    }:
        verification_data[
            "Verified_At__c"
        ] = datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        if verified_by:
            verification_data[
                "Verified_By__c"
            ] = verified_by

    # Rejected
    if verification_status == "Rejected":
        verification_data[
            "Rejection_Reason__c"
        ] = rejection_reason

    # Verified
    elif verification_status == "Verified":
        verification_data[
            "Rejection_Reason__c"
        ] = None

    # Pending
    else:
        verification_data[
            "Rejection_Reason__c"
        ] = None

        verification_data[
            "Verified_By__c"
        ] = None

        verification_data[
            "Verified_At__c"
        ] = None

    # Update Salesforce
    update_document_verification(
        content_version_id,
        verification_data,
    )

    # Get updated document
    updated_document = get_document_by_id(
        content_version_id
    )

    return format_document_response(
        updated_document
    )
