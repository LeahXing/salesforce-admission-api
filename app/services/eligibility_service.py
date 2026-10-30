
"""Application-level admission eligibility aggregation.

Consumes document_validation_service.validate_document() results.

Responsibilities:
- Evaluate the four required document categories.
- Support alternative documents such as IELTS or TOEFL.
- Aggregate document statuses into application eligibility.
- Identify missing, failed, and review-required requirements.

This module does not:
- Perform OCR.
- Verify applicant names.
- Check document authenticity.
- Update Salesforce.
- Issue admission offers.

The caller must provide current, application-scoped document results.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.core.admission_document_config import (
    normalize_document_type,
    normalize_program,
    required_documents,
)


# ==========================================
# Constants
# ==========================================

CATEGORIES = (
    "ID_PROOF",
    "ACADEMIC_RECORD",
    "ENTRANCE_EXAM",
    "ENGLISH_PROFICIENCY",
)

VALID_STATUSES = {
    "PASSED",
    "FAILED",
    "REVIEW_REQUIRED",
    "MISSING",
}

# Retained for compatibility with existing imports.
VERIFICATIONS = VALID_STATUSES | {"PROVISIONAL"}

REQUIREMENTS = {
    "SATISFIED",
    "PROVISIONAL",
    "BELOW_THRESHOLD",
    "REVIEW_REQUIRED",
    "NOT_EVALUATED",
}


# ==========================================
# Normalize Document Validation Status
# ==========================================

def _classify(record: Mapping[str, Any]) -> str:
    """Use the single authoritative status stored in Customer JSON."""
    status = str(record.get("validation_status") or "REVIEW_REQUIRED").strip().upper()
    return status if status in VALID_STATUSES else "REVIEW_REQUIRED"


# ==========================================
# Select Best Status for a Requirement
# ==========================================

def _best_status(statuses: list[str]) -> str:
    """
    Select the effective status for a document category.

    Priority:
        PASSED
        FAILED
        REVIEW_REQUIRED
        MISSING

    A passing document satisfies the requirement.

    Example:
        IELTS = FAILED
        TOEFL = PASSED

        English proficiency = PASSED

    Important:
        The caller must supply only current document
        versions. This function does not determine
        which uploaded version is newest.
    """

    if "PASSED" in statuses:
        return "PASSED"

    if "FAILED" in statuses:
        return "FAILED"

    if "REVIEW_REQUIRED" in statuses:
        return "REVIEW_REQUIRED"

    return "MISSING"


# ==========================================
# Evaluate Application Eligibility
# ==========================================

def evaluate_eligibility(
    *,
    application_no: str,
    program: str,
    document_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """
    Evaluate document requirements for one application.

    Program requirements are loaded from
    admission_document_config.required_documents().

    Overall status:
        PASSED:
            All four required categories passed.

        FAILED:
            At least one required category failed.

        REVIEW_REQUIRED:
            No failed category, but at least one
            category requires review.

        MISSING:
            No failed or review-required category,
            but at least one category is missing.

    IELTS and TOEFL are alternative documents.
    A passing alternative satisfies English proficiency.

    No Salesforce updates are performed here.
    """

    # --------------------------------------
    # Validate application number
    # --------------------------------------

    if not str(application_no).strip():
        raise ValueError(
            "application_no is required"
        )

    application_no = str(application_no).strip()

    # --------------------------------------
    # Normalize program and load requirements
    # --------------------------------------

    program_key = normalize_program(program)

    rules = required_documents(program_key)

    # --------------------------------------
    # Normalize incoming document results
    # --------------------------------------

    records: list[dict[str, Any]] = []

    for index, source in enumerate(document_results):

        if not isinstance(source, Mapping):
            raise TypeError(
                f"document_results[{index}] must be a mapping"
            )

        record = dict(source)

        # Reject documents from another application.
        record_application_no = record.get(
            "application_no"
        )

        if (
            record_application_no is not None
            and str(record_application_no) != application_no
        ):
            raise ValueError(
                f"document_results[{index}] belongs "
                "to a different application"
            )

        # Normalize document type.
        try:
            document_type = normalize_document_type(
                str(record.get("document_type") or "")
            )
        except ValueError:
            # Unknown document types cannot satisfy
            # any admission requirement.
            continue

        record["document_type"] = document_type

        record["_classification"] = _classify(record)

        records.append(record)

    # --------------------------------------
    # Evaluate each required category
    # --------------------------------------

    requirements: list[dict[str, Any]] = []

    for category in CATEGORIES:

        allowed = rules[category]

        candidates = [
            record
            for record in records
            if record["document_type"] in allowed
        ]

        statuses = [
            record["_classification"]
            for record in candidates
        ]

        status = _best_status(statuses)

        chosen = next(
            (
                record
                for record in candidates
                if record["_classification"] == status
            ),
            None,
        )

        requirements.append(
            {
                "category": category,
                "accepted_document_types": allowed,
                "status": status,
                "document_type_used": (
                    chosen["document_type"]
                    if chosen
                    else None
                ),
                "document_count": len(candidates),
                "message": _category_message(
                    category,
                    allowed,
                    status,
                ),
                "reason_codes": (
                    list(chosen.get("reason_codes") or [])
                    if chosen
                    else []
                ),
            }
        )

    # --------------------------------------
    # Determine overall validation status
    # --------------------------------------

    states = {
        requirement["status"]
        for requirement in requirements
    }

    if "FAILED" in states:
        overall = "FAILED"

    elif "REVIEW_REQUIRED" in states:
        overall = "REVIEW_REQUIRED"

    elif "MISSING" in states:
        overall = "MISSING"

    else:
        overall = "PASSED"

    # --------------------------------------
    # Identify categories by status
    # --------------------------------------

    missing = [
        requirement["category"]
        for requirement in requirements
        if requirement["status"] == "MISSING"
    ]

    review = [
        requirement["category"]
        for requirement in requirements
        if requirement["status"] == "REVIEW_REQUIRED"
    ]

    failed = [
        requirement["category"]
        for requirement in requirements
        if requirement["status"] == "FAILED"
    ]

    # Retained for backward compatibility.
    provisional: list[str] = []

    # --------------------------------------
    # Map to Salesforce eligibility value
    # --------------------------------------

    salesforce_eligibility_mapping = {
        "PASSED": "Eligible",
        "FAILED": "Not Eligible",
        "REVIEW_REQUIRED": "Not Evaluated",
        "MISSING": "Not Evaluated",
    }

    course_eligibility = (
        salesforce_eligibility_mapping[overall]
    )

    # --------------------------------------
    # Return detailed evaluation
    # --------------------------------------

    return {
        "application_no": application_no,
        "program": program_key,

        "eligibility_status": overall,
        "validation_status": overall,

        "course_eligibility": course_eligibility,

        "requirements": requirements,

        "missing_categories": missing,
        "review_categories": review,
        "below_threshold_categories": failed,
        "provisional_categories": provisional,

        "all_four_categories_satisfied": all(
            requirement["status"] == "PASSED"
            for requirement in requirements
        ),

        "admission_decision": None,
        "offer_letter_authorized": False,

        "message": _overall_message(
            overall,
            missing,
            review,
            failed,
            provisional,
        ),
    }


# ==========================================
# Category Validation Message
# ==========================================

def _category_message(
    category: str,
    allowed: list[str],
    status: str,
) -> str:

    label = category.replace("_", " ").title()

    if status == "PASSED":
        return (
            f"{label} requirement passed."
        )

    if status == "FAILED":
        return (
            f"{label} requirement failed."
        )

    if status == "REVIEW_REQUIRED":
        return (
            f"{label} requires manual review."
        )

    return (
        f"Missing {label}: upload "
        + " or ".join(allowed)
        + "."
    )


# ==========================================
# Overall Validation Message
# ==========================================

def _overall_message(
    status: str,
    missing: list[str],
    review: list[str],
    failed: list[str],
    provisional: list[str],
) -> str:

    if status == "PASSED":
        return (
            "All required document categories "
            "passed demo validation."
        )

    if status == "FAILED":
        return (
            "Admission score requirements failed: "
            + ", ".join(failed)
            + "."
        )

    if status == "REVIEW_REQUIRED":
        return (
            "Review required for: "
            + ", ".join(review)
            + "."
        )

    return (
        "Missing required document categories: "
        + ", ".join(missing)
        + "."
    )


# ==========================================
# Compatibility Alias
# ==========================================

evaluate_application_eligibility = evaluate_eligibility
