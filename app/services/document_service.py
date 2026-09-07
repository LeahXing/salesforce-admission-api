import json
import shutil
import uuid
from pathlib import Path

from app.repositories.salesforce_document_repository import (
    get_customer_by_application_no,
    create_document,
    get_document_by_id,
)


# ==========================================
# Temporary Upload Storage
# ==========================================

UPLOAD_DIR = Path("temp_uploads")

# Create the temporary upload directory if it does not exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
    description: str | None = None,
):
    """
    Create a new upload session for a document.
    """

    # Verify that the admission application exists
    customer = get_customer_by_application_no(application_no)

    if customer is None:
        raise ValueError(
            f"Application {application_no} was not found."
        )

    # Generate a unique ID for this upload session
    upload_id = str(uuid.uuid4())

    # Create a folder for this upload
    upload_path = UPLOAD_DIR / upload_id
    upload_path.mkdir(parents=True, exist_ok=False)

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
        "description": description,
        "status": "initiated",
    }

    metadata_path = upload_path / "metadata.json"

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

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

    # Verify that the upload session exists
    if not metadata_path.exists():
        raise ValueError(
            f"Upload session {upload_id} was not found."
        )

    # Load upload metadata
    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    # Verify that the upload belongs to this application
    if metadata["application_no"] != application_no:
        raise ValueError(
            "Upload session does not belong to this application."
        )

    total_chunks = metadata["total_chunks"]

    # Validate chunk number
    if chunk_number < 1 or chunk_number > total_chunks:
        raise ValueError(
            f"Chunk number must be between 1 and {total_chunks}."
        )

    # Save the chunk
    chunk_path = upload_path / f"chunk_{chunk_number}"

    with open(chunk_path, "wb") as f:
        f.write(chunk_content)

    # Update upload status
    metadata["status"] = "uploading"

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    # Count received chunks
    received_chunks = len(
        list(upload_path.glob("chunk_*"))
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
    Verify all chunks, reassemble the document,
    and upload one completed file to Salesforce.
    """

    upload_path = UPLOAD_DIR / upload_id
    metadata_path = upload_path / "metadata.json"

    # Verify that the upload session exists
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
            "Upload session does not belong to this application."
        )

    total_chunks = metadata["total_chunks"]

    # Verify that every expected chunk exists
    missing_chunks = []

    for chunk_number in range(1, total_chunks + 1):
        chunk_path = upload_path / f"chunk_{chunk_number}"

        if not chunk_path.exists():
            missing_chunks.append(chunk_number)

    if missing_chunks:
        raise ValueError(
            f"Missing chunks: {missing_chunks}"
        )

    # Reassemble all chunks into one complete file
    completed_file_path = upload_path / "completed_file"

    with open(completed_file_path, "wb") as completed_file:

        for chunk_number in range(1, total_chunks + 1):

            chunk_path = upload_path / f"chunk_{chunk_number}"

            with open(chunk_path, "rb") as chunk_file:
                shutil.copyfileobj(
                    chunk_file,
                    completed_file,
                )

    # Verify the final file size
    actual_file_size = completed_file_path.stat().st_size
    expected_file_size = metadata["file_size"]

    if actual_file_size != expected_file_size:
        raise ValueError(
            "Completed file size does not match "
            f"the expected size. "
            f"Expected {expected_file_size} bytes, "
            f"received {actual_file_size} bytes."
        )

    # Read the completed file for Salesforce upload
    with open(completed_file_path, "rb") as f:
        file_content = f.read()

    # Upload ONE completed document to Salesforce
    result = create_document(
        customer_id=metadata["customer_id"],
        file_name=metadata["file_name"],
        file_content=file_content,
        document_type=metadata["document_type"],
        source=metadata["source"],
        description=metadata["description"],
    )

    content_version_id = result["id"]

    # Get Salesforce document metadata
    document = get_document_by_id(
        content_version_id
    )

    # Delete temporary chunks after successful upload
    shutil.rmtree(upload_path)

    return {
        "upload_id": upload_id,
        "application_no": application_no,
        "status": "completed",
        "document": document,
    }
