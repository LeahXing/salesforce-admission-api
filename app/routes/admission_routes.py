# ==========================================
# Admission Routes
# ==========================================

from fastapi import APIRouter, HTTPException

from app.schemas.admission_schema import (
    AdmissionCreate,
    AdmissionUpdate,
)

from app.services.admission_service import (
    list_admissions,
    get_admission,
    register_admission,
    edit_admission,
    remove_admission,
)


router = APIRouter(
    prefix="/admissions",
    tags=["Admissions"],
)


# ==========================================
# Get All Admission Applications
# ==========================================

@router.get("")
def get_all_admission_applications():
    try:
        return list_admissions()

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# Get Admission Application by ID
# ==========================================

@router.get("/{application_id}")
def get_admission_application(application_id: str):
    try:
        return get_admission(application_id)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# Create Admission Application
# ==========================================

@router.post("")
def create_admission_application(admission: AdmissionCreate):
    try:
        admission_data = admission.model_dump()

        return register_admission(admission_data)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# Update Admission Application
# ==========================================

@router.patch("/{application_id}")
def update_admission_application(
    application_id: str,
    admission: AdmissionUpdate,
):
    try:
        admission_data = admission.model_dump(
            exclude_unset=True
        )

        return edit_admission(
            application_id,
            admission_data,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# Delete Admission Application
# ==========================================

@router.delete("/{application_id}")
def delete_admission_application(application_id: str):
    try:
        remove_admission(application_id)

        return {
            "message": "Admission application deleted successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
