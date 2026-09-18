# ==========================================
# Document Service
# ==========================================

import json
import os
import re
import shutil
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pypdf import PdfReader

from app.repositories.salesforce_document_repository import (
    get_customer_by_application_no,
    get_documents_by_application,
    get_document_by_id,
    get_document_content,
    create_document,
    update_document_verification,
)


# ==========================================
# Constants
# ==========================================

SCORE_CUTOFF = 70.0
IELTS_CUTOFF = 6.0

UPLOAD_DIR = Path("temp_uploads")

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ==========================================
# Helper: Format Document Response
# ==========================================

def format_document_response(document):
    """
    Convert Salesforce fields into
    API response fields.
    """

    return {
        "document_id": document["Id"],

        "application_id": document.get(
            "Application__c"
        ),

        "file_name": document["PathOnClient"],

        "file_extension": document.get(
            "FileExtension"
        ),

        "file_size": document.get(
            "ContentSize"
        ),

        "upload_datetime": document[
            "CreatedDate"
        ],

        "document_type": document[
            "Document_Type__c"
        ],

        "source": document[
            "Source__c"
        ],

        "verification_status": document.get(
            "Verification_Status__c"
        ),

        "failed_reason": document.get(
            "Failed_Reason__c"
        ),

        "verified_by": document.get(
            "Verified_By__c"
        ),

        "verified_at": document.get(
            "Verified_At__c"
        ),
    }


# ==========================================
# 1. List Documents for Application
# ==========================================

def list_documents(
    application_no: str,
):
    """
    Get all documents for one admission
    application.
    """

    customer = get_customer_by_application_no(
        application_no
    )

    if customer is None:
        raise ValueError(
            f"Application {application_no} "
            "was not found."
        )

    documents = get_documents_by_application(
        customer["Id"]
    )

    return [
        format_document_response(document)
        for document in documents
    ]


# ==========================================
# 2. Get One Document
# ==========================================

def get_document(
    content_version_id: str,
):
    """
    Get metadata for one document.
    """

    document = get_document_by_id(
        content_version_id
    )

    if document is None:
        raise ValueError(
            f"Document {content_version_id} "
            "was not found."
        )

    return format_document_response(
        document
    )


# ==========================================
# 3. Get Actual Document File
# ==========================================

def download_document(
    content_version_id: str,
):
    """
    Get the actual PDF/image content
    and its metadata.
    """

    document = get_document_by_id(
        content_version_id
    )

    if document is None:
        raise ValueError(
            f"Document {content_version_id} "
            "was not found."
        )

    file_content = get_document_content(
        content_version_id
    )

    return {
        "file_content": file_content,
        "file_name": document["PathOnClient"],
        "file_extension": document.get(
            "FileExtension"
        ),
    }


# ==========================================
# 4. Initialize Document Upload
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
    Create a new upload session.
    """

    customer = get_customer_by_application_no(
        application_no
    )

    if customer is None:
        raise ValueError(
            f"Application {application_no} "
            "was not found."
        )

    if file_size <= 0:
        raise ValueError(
            "File size must be greater than 0."
        )

    if total_chunks <= 0:
        raise ValueError(
            "Total chunks must be greater than 0."
        )

    upload_id = str(
        uuid.uuid4()
    )

    upload_path = (
        UPLOAD_DIR /
        upload_id
    )

    upload_path.mkdir(
        parents=True,
        exist_ok=False,
    )

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

    metadata_path = (
        upload_path /
        "metadata.json"
    )

    with open(
        metadata_path,
        "w",
    ) as f:
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
# 5. Upload Document Chunk
# ==========================================

def upload_document_chunk(
    application_no: str,
    upload_id: str,
    chunk_number: int,
    chunk_content: bytes,
):
    """
    Save one uploaded chunk temporarily.
    """

    upload_path = (
        UPLOAD_DIR /
        upload_id
    )

    metadata_path = (
        upload_path /
        "metadata.json"
    )

    if not metadata_path.exists():
        raise ValueError(
            f"Upload session {upload_id} "
            "was not found."
        )

    with open(
        metadata_path,
        "r",
    ) as f:
        metadata = json.load(f)

    if (
        metadata["application_no"]
        != application_no
    ):
        raise ValueError(
            "Upload session does not belong "
            "to this application."
        )

    total_chunks = metadata[
        "total_chunks"
    ]

    if (
        chunk_number < 1
        or chunk_number > total_chunks
    ):
        raise ValueError(
            f"Chunk number must be between "
            f"1 and {total_chunks}."
        )

    chunk_path = (
        upload_path /
        f"chunk_{chunk_number}"
    )

    with open(
        chunk_path,
        "wb",
    ) as f:
        f.write(
            chunk_content
        )

    metadata["status"] = "uploading"

    with open(
        metadata_path,
        "w",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=4,
        )

    received_chunks = len(
        list(
            upload_path.glob(
                "chunk_*"
            )
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
# Helper: PDF Text Extraction
# ==========================================

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract plain text from all pages
    of a PDF using pypdf.
    """

    if (
        not file_path
        or not os.path.isfile(file_path)
    ):
        return ""

    try:
        reader = PdfReader(file_path)

        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages)

    except Exception as exc:
        print(
            f"[PDF_EXTRACTOR] Error reading "
            f"{file_path}: {exc}"
        )

        return ""


# ==========================================
# Helper: PDF Readability Check
# ==========================================

def check_document_readability(
    file_path: str,
) -> Dict[str, Any]:
    """
    Determine whether a PDF contains enough
    extractable text to be considered readable.
    """

    if (
        not file_path
        or not os.path.isfile(file_path)
    ):
        return {
            "readable": False,
            "char_count": 0,
            "reason": (
                "File not found or inaccessible."
            ),
        }

    text = extract_text_from_pdf(
        file_path
    )

    char_count = len(
        text.replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
    )

    if char_count < 50:
        return {
            "readable": False,
            "char_count": char_count,
            "reason": (
                f"Only {char_count} characters "
                "could be extracted from the "
                "document. The file appears to "
                "be a scanned image or blurry PDF "
                "with no readable text."
            ),
        }

    return {
        "readable": True,
        "char_count": char_count,
        "reason": "",
    }


# ==========================================
# Helper: Academic Percentage Extractor
# ==========================================

def extract_academic_percentage_from_pdf(
    file_path: str,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract academic percentage from a
    12th Marksheet PDF.
    """

    text = extract_text_from_pdf(
        file_path
    )

    if not text:
        return None, None

    return _parse_percentage_from_text(
        text
    )


def _parse_percentage_from_text(
    text: str,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse percentage or CGPA from extracted
    PDF text using the existing rule priority.
    """

    if not text:
        return None, None

    # --------------------------------------
    # 1. Aggregate Score: X.X%
    # --------------------------------------

    match = re.search(
        r"Aggregate\s+Score:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*%",
        text,
        re.IGNORECASE,
    )

    if match:
        value = float(
            match.group(1)
        )

        if 0.0 <= value <= 100.0:
            return (
                round(value, 2),
                f"Aggregate Score ({value}%)",
            )

    # --------------------------------------
    # 2. Grand Total Percentage
    # --------------------------------------

    match = re.search(
        r"GRAND\s+TOTAL.*?"
        r"(?:PERCENTAGE:|\()\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*%",
        text,
        re.IGNORECASE,
    )

    if match:
        value = float(
            match.group(1)
        )

        if 0.0 <= value <= 100.0:
            return (
                round(value, 2),
                (
                    "Grand Total Percentage "
                    f"({value}%)"
                ),
            )

    # --------------------------------------
    # 3. Explicit Percentage field
    # --------------------------------------

    match = re.search(
        r"\bPercentage\b\s*[:\n]?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*%?",
        text,
        re.IGNORECASE,
    )

    if match:
        value = float(
            match.group(1)
        )

        if 0.0 <= value <= 100.0:
            return (
                round(value, 2),
                f"Percentage Field ({value}%)",
            )

    # --------------------------------------
    # 4. CGPA / SGPA / GPA field
    # --------------------------------------

    match = re.search(
        r"\b(?:CGPA|SGPA|GPA|CPI|OGPA|"
        r"Cumulative\s+Grade\s+Point\s+Average)"
        r"\s*[:\s]*"
        r"([0-9]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE,
    )

    if match:
        cgpa = float(
            match.group(1)
        )

        if 0.0 < cgpa <= 10.0:
            percentage = round(
                (cgpa / 10.0) * 100.0,
                2,
            )

            return (
                percentage,
                (
                    f"CGPA ({cgpa}/10.0 × 100 "
                    f"= {percentage}%)"
                ),
            )

        if 10.0 < cgpa <= 100.0:
            return (
                round(cgpa, 2),
                (
                    "CGPA as Percentage "
                    f"({cgpa}%)"
                ),
            )

    # --------------------------------------
    # 4b. CGPA fraction, e.g. 9.5 / 10.0
    # --------------------------------------

    match = re.search(
        r"\b([0-9]+(?:\.[0-9]+)?)"
        r"\s*/\s*10(?:\.0+)?\b",
        text,
        re.IGNORECASE,
    )

    if match:
        cgpa = float(
            match.group(1)
        )

        if 0.0 < cgpa <= 10.0:
            percentage = round(
                (cgpa / 10.0) * 100.0,
                2,
            )

            return (
                percentage,
                (
                    "CGPA Fraction "
                    f"({cgpa}/10.0 × 100 "
                    f"= {percentage}%)"
                ),
            )

    # --------------------------------------
    # 5. Tabular subject marks average
    # --------------------------------------

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    if (
        "subject" in text.lower()
        and "marks" in text.lower()
    ):
        subject_marks = []

        for line in lines:
            if re.match(
                r"^\d{2,3}(\.\d+)?$",
                line,
            ):
                value = float(
                    line
                )

                if 0 <= value <= 100:
                    subject_marks.append(
                        value
                    )

        if len(subject_marks) >= 3:
            average = round(
                sum(subject_marks)
                / len(subject_marks),
                2,
            )

            return (
                average,
                (
                    "Subject Marks Average "
                    f"({len(subject_marks)} subjects "
                    f"→ {average}%)"
                ),
            )

    # --------------------------------------
    # 6. Total / Max Marks ratio
    # --------------------------------------

    match = re.search(
        r"TOTAL\s*\n.*?\b(\d{3,4})\s*\n"
        r"\s*(\d{2,4}(?:\.[0-9]+)?)\b",
        text,
        re.IGNORECASE,
    )

    if match:
        max_marks = float(
            match.group(1)
        )

        obtained_marks = float(
            match.group(2)
        )

        if (
            max_marks > 0
            and 0 <= obtained_marks <= max_marks
        ):
            percentage = round(
                (
                    obtained_marks
                    / max_marks
                )
                * 100,
                2,
            )

            return (
                percentage,
                (
                    "Total/Max Marks "
                    f"({obtained_marks}/"
                    f"{max_marks} = "
                    f"{percentage}%)"
                ),
            )

    return None, None


# ==========================================
# Helper: IELTS Overall Band Extractor
# ==========================================

def extract_ielts_overall_band_from_pdf(
    file_path: str,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract IELTS Overall Band Score
    from an IELTS Test Report Form.

    Returns:
        (score, method)

    Example:
        (8.0, "IELTS Overall Band (8.0)")
    """

    text = extract_text_from_pdf(
        file_path
    )

    if not text:
        return None, None

    # --------------------------------------
    # 1. IELTS results table
    #
    # Listening Reading Writing Speaking
    # Overall Band CEFR Level
    # 8.5 8.0 7.5 8.5 8.0 C1
    # --------------------------------------

    match = re.search(
        (
            r"Listening\s+"
            r"Reading\s+"
            r"Writing\s+"
            r"Speaking\s+"
            r"Overall\s+Band"
            r"(?:\s+CEFR\s+Level)?"
            r"\s+"
            r"([0-9](?:\.[05])?)\s+"
            r"([0-9](?:\.[05])?)\s+"
            r"([0-9](?:\.[05])?)\s+"
            r"([0-9](?:\.[05])?)\s+"
            r"([0-9](?:\.[05])?)"
        ),
        text,
        re.IGNORECASE,
    )

    if match:
        overall_band = float(
            match.group(5)
        )

        if 0.0 <= overall_band <= 9.0:
            return (
                round(overall_band, 1),
                (
                    "IELTS Overall Band "
                    f"({overall_band})"
                ),
            )

    # --------------------------------------
    # 2. Explicit Overall Band field
    #
    # Overall Band: 6.5
    # Overall Band Score: 6.5
    # --------------------------------------

    match = re.search(
        (
            r"Overall\s+Band"
            r"(?:\s+Score)?"
            r"\s*[:\-]?\s*"
            r"([0-9](?:\.[05])?)"
        ),
        text,
        re.IGNORECASE,
    )

    if match:
        overall_band = float(
            match.group(1)
        )

        if 0.0 <= overall_band <= 9.0:
            return (
                round(overall_band, 1),
                (
                    "IELTS Overall Band "
                    f"({overall_band})"
                ),
            )

    return None, None


# ==========================================
# Helper: Auto Review 12th Marksheet
# ==========================================

def evaluate_uploaded_pdf(
    file_path: Path,
):
    """
    Automatically review an uploaded
    12th Marksheet PDF.

    Results:

        ELIGIBLE
            Score extracted successfully
            and score >= 70%.

        NOT_ELIGIBLE
            Score extracted successfully
            but score < 70%.

        FAILED
            Score could not be extracted.
    """

    verified_by = "Auto Evaluation Engine"

    # --------------------------------------
    # 1. Check PDF readability
    # --------------------------------------

    readability = check_document_readability(
        str(file_path)
    )

    if not readability["readable"]:

        failed_reason = (
            "Unable to extract academic score. "
            f"{readability['reason']} "
            "Please upload a clear, "
            "high-quality scan of your "
            "12th Marksheet."
        )

        return {
            "verification_status": "FAILED",
            "failed_reason": failed_reason,
            "verified_by": verified_by,
            "score": None,
            "score_method": None,
        }

    # --------------------------------------
    # 2. Extract academic percentage
    # --------------------------------------

    score, method = (
        extract_academic_percentage_from_pdf(
            str(file_path)
        )
    )

    if score is None:

        failed_reason = (
            "Unable to extract academic score. "
            "The document does not contain a "
            "recognizable percentage or CGPA."
        )

        return {
            "verification_status": "FAILED",
            "failed_reason": failed_reason,
            "verified_by": verified_by,
            "score": None,
            "score_method": None,
        }

    # --------------------------------------
    # 3. Check score against cutoff
    # --------------------------------------

    if score < SCORE_CUTOFF:

        return {
            "verification_status":
                "NOT_ELIGIBLE",
            "failed_reason": None,
            "verified_by": verified_by,
            "score": score,
            "score_method": method,
        }

    # --------------------------------------
    # 4. Score meets cutoff
    # --------------------------------------

    return {
        "verification_status": "ELIGIBLE",
        "failed_reason": None,
        "verified_by": verified_by,
        "score": score,
        "score_method": method,
    }


# ==========================================
# Helper: Auto Review IELTS
# ==========================================

def evaluate_ielts_pdf(
    file_path: Path,
):
    """
    Automatically review an uploaded
    IELTS Test Report Form.

    Results:

        ELIGIBLE
            Overall Band extracted successfully
            and score >= 6.0.

        NOT_ELIGIBLE
            Overall Band extracted successfully
            but score < 6.0.

        FAILED
            Overall Band could not be extracted.
    """

    verified_by = "Auto Evaluation Engine"

    # --------------------------------------
    # 1. Check PDF readability
    # --------------------------------------

    readability = check_document_readability(
        str(file_path)
    )

    if not readability["readable"]:

        failed_reason = (
            "Unable to extract IELTS score. "
            f"{readability['reason']} "
            "Please upload a clear, readable "
            "IELTS Test Report Form."
        )

        return {
            "verification_status": "FAILED",
            "failed_reason": failed_reason,
            "verified_by": verified_by,
            "score": None,
            "score_method": None,
        }

    # --------------------------------------
    # 2. Extract IELTS Overall Band
    # --------------------------------------

    score, method = (
        extract_ielts_overall_band_from_pdf(
            str(file_path)
        )
    )

    if score is None:

        failed_reason = (
            "Unable to extract IELTS Overall "
            "Band score from the document."
        )

        return {
            "verification_status": "FAILED",
            "failed_reason": failed_reason,
            "verified_by": verified_by,
            "score": None,
            "score_method": None,
        }

    # --------------------------------------
    # 3. Check IELTS score against cutoff
    # --------------------------------------

    if score < IELTS_CUTOFF:

        return {
            "verification_status":
                "NOT_ELIGIBLE",
            "failed_reason": None,
            "verified_by": verified_by,
            "score": score,
            "score_method": method,
        }

    # --------------------------------------
    # 4. IELTS score meets cutoff
    # --------------------------------------

    return {
        "verification_status": "ELIGIBLE",
        "failed_reason": None,
        "verified_by": verified_by,
        "score": score,
        "score_method": method,
    }


# ==========================================
# 6. Complete Document Upload
# ==========================================

def complete_document_upload(
    application_no: str,
    upload_id: str,
):
    """
    Reassemble all chunks.

    Automatically review supported documents:

        12th Marksheet
        IELTS

    Upload the PDF and generated
    verification result to Salesforce.
    """

    upload_path = (
        UPLOAD_DIR /
        upload_id
    )

    metadata_path = (
        upload_path /
        "metadata.json"
    )

    if not metadata_path.exists():
        raise ValueError(
            f"Upload session {upload_id} "
            "was not found."
        )

    with open(
        metadata_path,
        "r",
    ) as f:
        metadata = json.load(f)

    if (
        metadata["application_no"]
        != application_no
    ):
        raise ValueError(
            "Upload session does not belong "
            "to this application."
        )

    total_chunks = metadata[
        "total_chunks"
    ]

    # --------------------------------------
    # Check missing chunks
    # --------------------------------------

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

    # --------------------------------------
    # Reassemble file
    # --------------------------------------

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

    # --------------------------------------
    # Verify file size
    # --------------------------------------

    actual_file_size = (
        completed_file_path
        .stat()
        .st_size
    )

    expected_file_size = metadata[
        "file_size"
    ]

    if (
        actual_file_size
        != expected_file_size
    ):
        raise ValueError(
            "Completed file size does not "
            "match expected size. "
            f"Expected {expected_file_size} "
            f"bytes, received "
            f"{actual_file_size} bytes."
        )

    # --------------------------------------
    # Automatically review document
    # --------------------------------------

    document_type = metadata[
        "document_type"
    ]

    normalized_document_type = (
        document_type
        .strip()
        .lower()
    )

    # --------------------------------------
    # 12th Marksheet
    # --------------------------------------

    if normalized_document_type == (
        "12th marksheet"
    ):

        evaluation = evaluate_uploaded_pdf(
            completed_file_path
        )

    # --------------------------------------
    # IELTS
    # --------------------------------------

    elif normalized_document_type in {
        "ielts",
        "ielts score",
        "ielts score report",
        "ielts test report form",
    }:

        evaluation = evaluate_ielts_pdf(
            completed_file_path
        )

    # --------------------------------------
    # Unsupported document type
    # --------------------------------------

    else:
        raise ValueError(
            "Automatic document evaluation "
            "currently supports "
            "12th Marksheet and IELTS only."
        )

    verification_status = evaluation[
        "verification_status"
    ]

    failed_reason = evaluation[
        "failed_reason"
    ]

    verified_by = evaluation[
        "verified_by"
    ]

    # --------------------------------------
    # Read final file
    # --------------------------------------

    with open(
        completed_file_path,
        "rb",
    ) as f:
        file_content = f.read()

    # --------------------------------------
    # Upload file + evaluation to Salesforce
    # --------------------------------------

    result = create_document(
        customer_id=metadata[
            "customer_id"
        ],

        file_name=metadata[
            "file_name"
        ],

        file_content=file_content,

        document_type=document_type,

        source=metadata[
            "source"
        ],

        verification_status=(
            verification_status
        ),

        failed_reason=(
            failed_reason
        ),

        verified_by=(
            verified_by
        ),
    )

    content_version_id = result[
        "id"
    ]

    # --------------------------------------
    # Retrieve created Salesforce document
    # --------------------------------------

    document = get_document_by_id(
        content_version_id
    )

    document_response = (
        format_document_response(
            document
        )
    )

    # --------------------------------------
    # Delete temporary upload files
    # --------------------------------------

    shutil.rmtree(
        upload_path
    )

    # --------------------------------------
    # Return API response
    # --------------------------------------

    return {
        "upload_id": upload_id,
        "application_no": application_no,
        "status": "completed",

        "verification_status":
            verification_status,

        "score": evaluation[
            "score"
        ],

        "score_method": evaluation[
            "score_method"
        ],

        "document": document_response,
    }


# ==========================================
# 7. Update Document Verification
# ==========================================

def verify_document(
    content_version_id: str,
    verification_status: str,
    failed_reason: str | None = None,
    verified_by: str | None = None,
):
    """
    Manually update document verification.

    Supported statuses:

        ELIGIBLE
        NOT_ELIGIBLE
        FAILED
    """

    allowed_statuses = {
        "ELIGIBLE",
        "NOT_ELIGIBLE",
        "FAILED",
    }

    if (
        verification_status
        not in allowed_statuses
    ):
        raise ValueError(
            "Verification status must be "
            "ELIGIBLE, NOT_ELIGIBLE, or FAILED."
        )

    if (
        verification_status == "FAILED"
        and not failed_reason
    ):
        raise ValueError(
            "Failed reason is required when "
            "verification status is FAILED."
        )

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

        "Verified_At__c":
            datetime.now(
                timezone.utc
            ).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
    }

    if verified_by:
        verification_data[
            "Verified_By__c"
        ] = verified_by

    if verification_status == "FAILED":

        verification_data[
            "Failed_Reason__c"
        ] = failed_reason

    else:

        verification_data[
            "Failed_Reason__c"
        ] = None

    update_document_verification(
        content_version_id,
        verification_data,
    )

    updated_document = (
        get_document_by_id(
            content_version_id
        )
    )

    return format_document_response(
        updated_document
    )