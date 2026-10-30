# ==========================================
# Document Service
# ==========================================

import os
import re

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pypdf import PdfReader

from app.core.admission_document_config import VERIFY_APPLICANT_NAME

from app.repositories.salesforce_admission_repository import (
    update_customer_document_validation,
    read_document_validation_state,
)

from app.repositories.salesforce_document_repository import (
    get_customer_by_application_no,
    get_documents_by_application,
    get_document_by_id,
    get_document_content,
    create_document,
    update_document_verification,
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



# ==========================================
# 5. Upload Document Chunk
# ==========================================



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
    from a real IELTS Test Report Form.

    Supports layouts such as:

        Overall Band Score 6.5

    and:

        Overall
        Band
        Score
        3.5

    Returns:
        (score, method)

    Example:
        (3.5, "IELTS Overall Band (3.5)")
    """

    text = extract_text_from_pdf(
        file_path
    )

    if not text:
        return None, None

    # --------------------------------------
    # 1. Real IELTS TRF format
    #
    # Overall
    # Band
    # Score
    # 3.5
    #
    # or:
    #
    # Overall Band Score 6.5
    # --------------------------------------

    match = re.search(
        (
            r"\bOverall\s+"
            r"Band\s+"
            r"Score\s*"
            r"[:\-]?\s*"
            r"([0-9](?:\.[05])?)\b"
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

    # --------------------------------------
    # 2. Alternative IELTS format
    #
    # Overall Band 6.5
    # --------------------------------------

    match = re.search(
        (
            r"\bOverall\s+"
            r"Band\s*"
            r"[:\-]?\s*"
            r"([0-9](?:\.[05])?)\b"
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



# ==========================================
# Helper: Auto Review IELTS
# ==========================================



# ==========================================
# 6. Complete Document Upload
# ==========================================



# ==========================================
# 6a. Single-file upload and verification
# ==========================================

def _admission_modules():
    """Load integration modules lazily to keep document listing usable without OCR packages."""
    from app.core.admission_document_config import normalize_document_type, normalize_program
    from app.services.document_validation_service import validate_document
    from app.services.eligibility_service import evaluate_eligibility
    return normalize_document_type, normalize_program, validate_document, evaluate_eligibility


def _customer_program(customer: Dict[str, Any]) -> str:
    """Use explicit program classification; never guess from course initials."""
    _, normalize_program, _, _ = _admission_modules()
    course = str(customer.get("Course__c") or "").strip().upper()
    if course == "MBA":
        return "MBA"
    for field in ("Program__c", "Education_Level__c"):
        if customer.get(field):
            try:
                return normalize_program(str(customer[field]))
            except ValueError:
                pass
    course = str(customer.get("Course__c") or "").strip().upper()
    if course == "MBA" or "BUSINESS ADMINISTRATION" in course and "MASTER" in course:
        return "MBA"
    if course.startswith(("B.TECH", "BTECH", "B.SC", "BSC", "BACHELOR")):
        return "BACHELOR"
    if course.startswith(("M.TECH", "MTECH", "M.SC", "MSC", "MASTER")):
        return "MASTER"
    raise ValueError("Unable to identify Bachelor, Master, or MBA program from Salesforce Customer. Set Program__c or Education_Level__c explicitly.")


def _customer_name(customer: Dict[str, Any]) -> str:
    first = customer.get("First_Name__c") or customer.get("FirstName") or ""
    last = customer.get("Last_Name__c") or customer.get("LastName") or ""
    name = f"{first} {last}".strip() or str(customer.get("Name") or "").strip()
    if not name and VERIFY_APPLICANT_NAME:
        raise ValueError("Applicant name is missing from Salesforce Customer.")
    return name


def _extract_ielts(pdf_bytes: bytes) -> Dict[str, Any]:
    """Conservative IELTS text parser; uncertain/scanned reports require manual review."""
    import io
    text = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        pass
    match = re.search(r"\bOverall\s+Band\s+(?:Score\s*)?[:\-]?\s*([0-9](?:\.[05])?)\b", text, re.I)
    score = float(match.group(1)) if match else None
    # Do not fabricate a candidate name from other names on the form.
    return {"document_type": "IELTS", "detected_document_type": "IELTS" if re.search(r"\bIELTS\b|\bOverall\s+Band\b", text, re.I) else None,
            "overall_band": score, "student_name": None,
            "extraction_status": "REVIEW_REQUIRED" if score is None else "EXTRACTED",
            "warnings": ([] if not VERIFY_APPLICANT_NAME else ["Applicant name not reliably extracted from IELTS report"]),
            "issuer_authenticity_verified": False}


def _extract_document(pdf_bytes: bytes, dtype: str, applicant_name: str) -> Dict[str, Any]:
    """Extract document evidence; avoid name-dependent checks in test mode."""
    if dtype == "ID_PROOF":
        from app.services.identity_document_extractor import extract_identity_document

        return extract_identity_document(
            pdf_bytes,
            applicant_name if VERIFY_APPLICANT_NAME else None,
        )
    if dtype in {"CLASS_12_MARKSHEET", "UNDERGRADUATE_TRANSCRIPT"}:
        from app.services.academic_score_extractor import extract_academic_record
        return extract_academic_record(pdf_bytes, dtype)
    if dtype == "IELTS":
        return _extract_ielts(pdf_bytes)
    from app.services.exam_score_extractor import extract_exam_score
    # Avoid passing the Salesforce name when comparison is disabled.
    # The exam extractor may still need updating if it requires a name.
    return extract_exam_score(
        pdf_bytes, dtype, applicant_name if VERIFY_APPLICANT_NAME else ""
    )



def _record_upload_and_recalculate(*, application_no: str, customer_id: str,
                                   program: str, document_id: str, dtype: str,
                                   file_name: str, validation: dict, extracted: dict):
    """Append one attempt, select active evidence, and recalculate eligibility."""
    _, _, _, evaluate_eligibility = _admission_modules()
    state = read_document_validation_state(customer_id, program)
    history = state["document_history"]
    if any(row.get("document_id") == document_id for row in history):
        raise ValueError("This ContentVersion is already in document history")

    verification = str(validation.get("verification_status") or "REVIEW_REQUIRED").upper()
    requirement = str(validation.get("requirement_status") or "NOT_EVALUATED").upper()
    codes = list(validation.get("reason_codes") or [])
    detected = validation.get("detected_document_type") or extracted.get("detected_document_type")
    mismatch = any(code in codes for code in ("DOCUMENT_TYPE_MISMATCH", "ACADEMIC_LEVEL_MISMATCH", "DOCUMENT_NOT_ACCEPTED_FOR_PROGRAM"))
    if mismatch:
        status = "FAILED"
    elif verification == "REVIEW_REQUIRED":
        status = "REVIEW_REQUIRED"
    elif verification == "FAILED" or requirement == "BELOW_THRESHOLD":
        status = "FAILED"
    elif verification == "PASSED" and requirement == "SATISFIED":
        status = "PASSED"
    else:
        status = "REVIEW_REQUIRED"

    previous = next((r for r in reversed(history)
                     if r.get("document_type") == dtype and r.get("is_active") is True), None)
    previous_passed = bool(previous and previous.get("validation_status") == "PASSED")
    # Preserve an existing passing document if a later attempt fails.
    # A valid below-threshold document may be active when no passing one exists.
    promote = (not mismatch and verification == "PASSED" and
               (status == "PASSED" or (requirement == "BELOW_THRESHOLD" and not previous_passed)))

    entry = {
        "document_id": document_id,
        "document_type": dtype,
        "detected_document_type": detected,
        "validation_status": status,
        "reason_codes": codes,
        "reason": validation.get("message") or "",
        "is_active": False,
    }
    # Retain useful scores without duplicating entire OCR results.
    score_map = {
        "CLASS_12_MARKSHEET": ("percentage", "minimum_required_percentage", 70.0),
        "UNDERGRADUATE_TRANSCRIPT": ("extracted_gpa", "minimum_required_gpa", 3.2),
        "SAT": ("extracted_score", "minimum_required_score", 1100),
        "GRE": ("extracted_score", "minimum_required_score", 290),
        "GMAT": ("extracted_score", "minimum_required_score", 600),
        "IELTS": ("extracted_score", "minimum_required_score", 6.5),
        "TOEFL": ("extracted_score", "minimum_required_score", 72),
    }
    if dtype in score_map and not mismatch:
        key, threshold_key, threshold = score_map[dtype]
        value = validation.get(key)
        if value is None and validation.get("extracted_score") is not None:
            value = validation["extracted_score"]
        if value is None:
            for source_key in ("extracted_score", "score", "percentage", "overall_gpa", "gpa", "overall_band", "total_score"):
                if source_key in extracted and extracted[source_key] is not None:
                    value = extracted[source_key]
                    break
        if value is not None:
            entry[key] = value
        entry[threshold_key] = threshold
    # Keep the exact requirement classification for eligibility, but not in Customer JSON.
    # The public JSON has only one status field.
    if promote:
        if previous:
            previous["is_active"] = False
        entry["is_active"] = True
    history.append(entry)

    active_results = []
    for row in history:
        if row.get("is_active") is not True:
            continue
        active_results.append({
            "document_type": row["document_type"],
            "validation_status": row["validation_status"],
        })
    evaluation = evaluate_eligibility(
        application_no=application_no, program=program, document_results=active_results
    )
    saved = update_customer_document_validation(
        customer_id=customer_id, program=program,
        document_results=active_results,
        course_eligibility=evaluation["course_eligibility"], state=state,
    )
    return evaluation, saved, entry["is_active"]


def upload_and_verify_document(
    application_no: str,
    file_name: str,
    file_content: bytes,
    document_type: str,
    source: str = "API",
) -> Dict[str, Any]:
    """Upload one PDF to Salesforce with document-level verification feedback.

    This function does NOT issue an offer, approve admission, or assert issuer authenticity.
    It does NOT persist structured eligibility evidence: the existing repository has
    only verification status and failure-reason fields. Add dedicated storage before
    implementing application-wide eligibility from Salesforce history.
    """
    normalize_type, _, validate_document, _ = _admission_modules()
    dtype = normalize_type(document_type)
    if not isinstance(file_content, bytes) or not file_content:
        raise ValueError("A nonempty PDF file is required.")
    if len(file_content) > 10 * 1024 * 1024:
        raise ValueError("PDF exceeds the 10 MB upload limit.")
    if not file_content.lstrip().startswith(b"%PDF-"):
        raise ValueError("Only PDF files are supported for automatic verification.")
    if not file_name or Path(file_name).suffix.lower() != ".pdf":
        raise ValueError("File name must have a .pdf extension.")
    customer = get_customer_by_application_no(application_no)
    if customer is None:
        raise ValueError(f"Application {application_no} was not found.")
    program = _customer_program(customer)
    applicant_name = ""  # Demo: name matching disabled for every document type
    try:
        extracted = _extract_document(file_content, dtype, applicant_name)
    except Exception as exc:
        # OCR/parser failures are reviewable, never proof of an invalid document.
        extracted = {"extraction_status": "REVIEW_REQUIRED", "warnings": [f"Extraction error: {type(exc).__name__}"],
                     "document_type": dtype}
    validation = validate_document(document_type=dtype, applicant_name=applicant_name,
                                   extracted_data=extracted, program=program,
                                   verify_applicant_name=False)
    if extracted.get("extraction_status") == "REVIEW_REQUIRED" and validation["verification_status"] == "PASSED":
        validation["verification_status"] = "REVIEW_REQUIRED"
        validation["reason_codes"] = list(dict.fromkeys(validation["reason_codes"] + ["EXTRACTION_UNCERTAIN"]))
        validation["message"] = "Document extraction needs manual verification before approval."
        validation["action_required"] = "MANUAL_REVIEW"
    verification_status = validation["verification_status"]
    # Confirm Salesforce picklist includes PASSED, FAILED, REVIEW_REQUIRED before deployment.
    reason = "; ".join(validation["reason_codes"]) or None
    created = create_document(customer_id=customer["Id"], file_name=Path(file_name).name,
                              file_content=file_content, document_type=dtype, source=source,
                              verification_status=verification_status, failed_reason=reason,
                              verified_by="Auto Evaluation Engine")
    document_id = created["id"]
    stored = get_document_by_id(document_id)
    # Persist audit history and automatically evaluate only active evidence.
    # A Salesforce update failure is reported; it is NOT silently ignored.
    evaluation, saved, is_active = _record_upload_and_recalculate(
        application_no=application_no, customer_id=customer["Id"],
        program=program, document_id=document_id, dtype=dtype,
        file_name=Path(file_name).name, validation=validation,
        extracted=extracted,
    )
    return {"application_no": application_no, "document_type": dtype,
            "is_active": is_active,
            "course_eligibility": evaluation["course_eligibility"],
            "application_evaluation": evaluation,
            "salesforce_update": saved,
            "name_match_status": validation["name_match_status"],
            "validation_status": ("FAILED" if "DOCUMENT_TYPE_MISMATCH" in validation.get("reason_codes", []) else ("REVIEW_REQUIRED" if verification_status == "REVIEW_REQUIRED" else ("FAILED" if verification_status == "FAILED" or validation.get("requirement_status") == "BELOW_THRESHOLD" else "PASSED"))),
            "requirement_status": validation["requirement_status"],
            "extracted_data": extracted, "validation": validation,
            "message": validation["message"], "action_required": validation["action_required"],
            "document": format_document_response(stored) if stored else {"document_id": document_id}}


def evaluate_application_documents(application_no: str, document_results: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate caller-supplied, CURRENT validated evidence for this application.

    Do not pass raw Salesforce ContentVersion rows: they lack requirement_status.
    """
    customer = get_customer_by_application_no(application_no)
    if customer is None:
        raise ValueError(f"Application {application_no} was not found.")
    _, _, _, evaluate_eligibility = _admission_modules()
    normalized = []
    for item in document_results:
        result = dict(item.get("validation") or item)
        result["application_no"] = application_no
        normalized.append(result)
    return evaluate_eligibility(application_no=application_no, program=_customer_program(customer),
                                document_results=normalized)



# ==========================================
# 6b. Evaluate and Save Application Eligibility
# ==========================================

def evaluate_and_save_application_documents(
    application_no: str,
    document_results: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluate trusted current evidence and save two Salesforce Customer fields.

    Only use this for controlled demo data. The supplied validation results
    are not independently verified against Salesforce document content.
    Uploading a single document does not automatically trigger this write.
    """
    if not isinstance(application_no, str) or not application_no.strip():
        raise ValueError("application_no is required")
    application_no = application_no.strip()

    if not isinstance(document_results, list):
        raise ValueError("document_results must be a list")

    customer = get_customer_by_application_no(application_no)
    if customer is None:
        raise ValueError(f"Application {application_no} was not found.")
    customer_id = customer.get("Id")
    if not customer_id:
        raise ValueError("Salesforce Customer ID is missing.")

    program = _customer_program(customer)
    normalize_type, _, _, evaluate_eligibility = _admission_modules()
    normalized_results: list[Dict[str, Any]] = []

    for index, item in enumerate(document_results):
        if not isinstance(item, dict):
            raise ValueError(f"document_results[{index}] must be an object")
        nested = item.get("validation")
        if nested is not None and not isinstance(nested, dict):
            raise ValueError(f"document_results[{index}].validation must be an object")
        result = dict(nested if nested is not None else item)

        for supplied in (item.get("application_no"), result.get("application_no")):
            if supplied is not None and str(supplied) != application_no:
                raise ValueError(
                    f"document_results[{index}] belongs to a different application"
                )

        outer_type = item.get("document_type")
        inner_type = result.get("document_type")
        if outer_type and inner_type:
            if normalize_type(str(outer_type)) != normalize_type(str(inner_type)):
                raise ValueError(
                    f"document_results[{index}] has conflicting document types"
                )
        dtype = inner_type or outer_type
        if not dtype:
            raise ValueError(f"document_results[{index}] lacks document_type")
        result["document_type"] = normalize_type(str(dtype))
        result["application_no"] = application_no
        normalized_results.append(result)

    evaluation = evaluate_eligibility(
        application_no=application_no,
        program=program,
        document_results=normalized_results,
    )
    course_eligibility = evaluation["course_eligibility"]

    saved = update_customer_document_validation(
        customer_id=customer_id,
        program=program,
        document_results=normalized_results,
        course_eligibility=course_eligibility,
    )

    return {
        "application_no": application_no,
        "customer_id": customer_id,
        "program": program,
        "validation_status": evaluation["validation_status"],
        "course_eligibility": course_eligibility,
        "evaluation": evaluation,
        "document_results": normalized_results,
        "salesforce_update": saved,
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

    Supported statuses: PASSED, REVIEW_REQUIRED, FAILED.
    """

    allowed_statuses = {
        "PASSED",
        "REVIEW_REQUIRED",
        "FAILED",
    }

    if (
        verification_status
        not in allowed_statuses
    ):
        raise ValueError(
            "Verification status must be "
            "PASSED, REVIEW_REQUIRED, or FAILED."
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