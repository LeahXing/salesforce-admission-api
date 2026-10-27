from typing import Optional
from pydantic import BaseModel


# ==========================================
# User Lookup / Create Request
# ==========================================

class UserLookupCreateRequest(BaseModel):
    name: str
    email: str
    phoneNumber: str
    conversationId: str
    course: Optional[str] = None


# ==========================================
# User Response
# ==========================================

class UserResponse(BaseModel):
    userId: str
    name: str
    email: str
    phoneNumber: str
    conversationId: str
    course: Optional[str] = None

    sentiment: Optional[str] = None
    offerLetterReleased: bool = False
    offerLetterAccepted: Optional[str] = None


# ==========================================
# User Status Update Request
# ==========================================

class UserStatusUpdateRequest(BaseModel):
    sentiment: Optional[str] = None
    offerLetterReleased: Optional[bool] = None
    offerLetterAccepted: Optional[str] = None