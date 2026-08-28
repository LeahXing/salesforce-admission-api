# ==========================================
# Admission Service
# ==========================================

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
    return create_admission(admission_data)


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
