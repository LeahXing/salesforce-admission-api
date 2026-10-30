
# ==========================================
# Admission Service
# ==========================================

import random

from app.repositories.salesforce_admission_repository import (
    get_all_admissions,
    get_admission_by_id,
    create_admission,
    update_admission,
    delete_admission,
    update_customer_document_validation,
)

from app.core.admission_document_config import (
    evaluate_application,
)


# ==========================================
# List Admission Applications
# ==========================================

def list_admissions():
    return get_all_admissions()


# ==========================================
# Get Admission Application
# ==========================================

def get_admission(application_id):
    return get_admission_by_id(application_id)


# ==========================================
# Register Admission Application
# ==========================================

def register_admission(admission_data):

    processed_admission_data = admission_data.copy()

    education_level = processed_admission_data.get(
        "Education_Level__c"
    )
    course = processed_admission_data.get("Course__c")

    if not education_level and course:

        course = course.strip()

        if len(course) == 3 and course.upper().startswith("M"):
            education_level = "Master's"

        elif len(course) == 3 and course.upper().startswith("B"):
            education_level = "Bachelor's"

        else:
            education_level = random.choice([
                "Bachelor's",
                "Diploma",
                "Master's"
            ])

        processed_admission_data["Education_Level__c"] = (
            education_level
        )

    return create_admission(processed_admission_data)


# ==========================================
# Edit Admission Application
# ==========================================

def edit_admission(application_id, admission_data):
    return update_admission(
        application_id,
        admission_data,
    )


# ==========================================
# Remove Admission Application
# ==========================================

def remove_admission(application_id):
    return delete_admission(application_id)


# ==========================================
# Save Document Validation and Eligibility
# ==========================================

def save_admission_document_evaluation(
    customer_id: str,
    program: str,
    document_results: list[dict],
):
    """
    Evaluate application-wide document requirements
    and save the results to Salesforce Customer.

    Salesforce fields:
        Document_Validation_Results__c
        Course_Eligibility__c

    Eligibility mapping:
        All required categories satisfied -> Eligible
        Any required category failed -> Not Eligible
        Otherwise -> Not Evaluated

    IELTS and TOEFL are alternative requirements.
    Only one passing language exam is necessary.

    Document authenticity and applicant-name
    verification are excluded from this demo.
    """

    # --------------------------------------
    # Validate inputs
    # --------------------------------------

    if not customer_id or not customer_id.strip():
        raise ValueError(
            "customer_id is required"
        )

    if not program or not program.strip():
        raise ValueError(
            "program is required"
        )

    if not isinstance(document_results, list):
        raise ValueError(
            "document_results must be a list"
        )

    if not all(
        isinstance(item, dict)
        for item in document_results
    ):
        raise ValueError(
            "Each document result must be a dictionary"
        )

    # --------------------------------------
    # Normalize program
    # --------------------------------------

    program_aliases = {
        "BACHELOR": "BACHELOR",
        "BACHELOR'S": "BACHELOR",
        "BACHELORS": "BACHELOR",
        "MASTER": "MASTER",
        "MASTER'S": "MASTER",
        "MASTERS": "MASTER",
        "MBA": "MBA",
    }

    normalized_program = program_aliases.get(
        program.strip().upper()
    )

    if normalized_program is None:
        raise ValueError(
            f"Unsupported admission program: {program}"
        )

    # --------------------------------------
    # Evaluate required documents
    # --------------------------------------

    evaluation = evaluate_application(
        normalized_program,
        document_results,
    )

    validation_status = evaluation.get(
        "validation_status"
    )

    # --------------------------------------
    # Map to Salesforce eligibility
    # --------------------------------------

    eligibility_mapping = {
        "PASSED": "Eligible",
        "FAILED": "Not Eligible",
        "MISSING": "Not Evaluated",
        "REVIEW_REQUIRED": "Not Evaluated",
    }

    if validation_status not in eligibility_mapping:
        raise ValueError(
            "Unexpected application validation status: "
            f"{validation_status}"
        )

    course_eligibility = eligibility_mapping[
        validation_status
    ]

    # --------------------------------------
    # Update Salesforce Customer
    # --------------------------------------

    result = update_customer_document_validation(
        customer_id=customer_id,
        program=normalized_program,
        document_results=document_results,
        course_eligibility=course_eligibility,
    )

    return {
        **result,
        "validation_status": validation_status,
        "course_eligibility": course_eligibility,
        "evaluation": evaluation,
    }
