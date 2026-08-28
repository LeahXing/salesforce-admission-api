# ==========================================
# Admission Schemas
# ==========================================

from typing import Optional
from pydantic import BaseModel


# ==========================================
# Create Admission Application
# ==========================================

class AdmissionCreate(BaseModel):
    Application_No__c: str

    First_Name__c: Optional[str] = None
    Last_Name__c: Optional[str] = None
    Email__c: Optional[str] = None
    Phone__c: Optional[str] = None
    City__c: Optional[str] = None
    Gender__c: Optional[str] = None

    Course__c: Optional[str] = None
    Major__c: Optional[str] = None
    Advising_College__c: Optional[str] = None
    Intake__c: Optional[str] = None
    Semester__c: Optional[str] = None
    Residency__c: Optional[str] = None

    Admission_Status__c: Optional[str] = None
    Approved_By__c: Optional[str] = None

    Offer_Status__c: Optional[str] = None
    Offer_Sent_At__c: Optional[str] = None

    Sentiment__c: Optional[str] = None
    University_ID__c: Optional[str] = None
    Remarks__c: Optional[str] = None

    Created_At__c: Optional[str] = None
    Updated_At__c: Optional[str] = None

    Testing_Record__c: Optional[bool] = False


# ==========================================
# Update Admission Application
# ==========================================

class AdmissionUpdate(BaseModel):
    First_Name__c: Optional[str] = None
    Last_Name__c: Optional[str] = None
    Email__c: Optional[str] = None
    Phone__c: Optional[str] = None
    City__c: Optional[str] = None
    Gender__c: Optional[str] = None

    Course__c: Optional[str] = None
    Major__c: Optional[str] = None
    Advising_College__c: Optional[str] = None
    Intake__c: Optional[str] = None
    Semester__c: Optional[str] = None
    Residency__c: Optional[str] = None

    Admission_Status__c: Optional[str] = None
    Approved_By__c: Optional[str] = None

    Offer_Status__c: Optional[str] = None
    Offer_Sent_At__c: Optional[str] = None

    Sentiment__c: Optional[str] = None
    University_ID__c: Optional[str] = None
    Remarks__c: Optional[str] = None

    Updated_At__c: Optional[str] = None
    Testing_Record__c: Optional[bool] = None
