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

    education_level = processed_admission_data.get("Education_Level__c")
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

        processed_admission_data["Education_Level__c"] = education_level

    return create_admission(processed_admission_data)

# ==========================================
# Edit Admission Application
# ==========================================

def edit_admission(application_id, admission_data):
    return update_admission(application_id, admission_data)


# ==========================================
# Remove Admission Application
# ==========================================

def remove_admission(application_id):
    return delete_admission(application_id)