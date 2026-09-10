from fastapi import APIRouter, HTTPException

from app.schemas.user_schema import (
    UserLookupCreateRequest,
    UserResponse,
    UserStatusUpdateRequest,
)

from app.services.user_service import (
    lookup_or_create_user,
    update_user,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# ==========================================
# Lookup Existing User or Create New User
# ==========================================

@router.post(
    "/lookup-or-create",
    response_model=UserResponse,
)
def lookup_or_create_user_route(
    data: UserLookupCreateRequest,
):
    try:
        return lookup_or_create_user(data)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ==========================================
# Update User Status
# ==========================================

@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
)
def update_user_status_route(
    user_id: str,
    data: UserStatusUpdateRequest,
):
    try:
        return update_user(
            data=data,
            user_id=user_id,
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