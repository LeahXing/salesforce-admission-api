# ==========================================
# Admission Schemas
# ==========================================

from typing import Optional
from pydantic import BaseModel


# ==========================================
# Create Admission Application
# ==========================================

class AdmissionCreate(BaseModel):

    # --------------------------------------
    # Application / User
    # --------------------------------------

    Application_No__c: str

    User_ID__c: Optional[str] = None
    Conversation_ID__c: Optional[str] = None


    # --------------------------------------
    # Applicant Information
    # --------------------------------------

    First_Name__c: Optional[str] = None
    Last_Name__c: Optional[str] = None
    Email__c: Optional[str] = None
    Phone__c: Optional[str] = None
    City__c: Optional[str] = None
    Gender__c: Optional[str] = None


    # --------------------------------------
    # Program Information
    # --------------------------------------

    Education_Level__c: Optional[str] = None
    Course__c: Optional[str] = None
    Major__c: Optional[str] = None
    Advising_College__c: Optional[str] = None
    Intake__c: Optional[str] = None
    Semester__c: Optional[str] = None
    Residency__c: Optional[str] = None


    # --------------------------------------
    # Academic / IELTS Evaluation
    # --------------------------------------

    Academic_Percentage__c: Optional[float] = None
    Original_CGPA__c: Optional[float] = None
    Converted_Percentage__c: Optional[float] = None
    IELTS_Overall_Score__c: Optional[float] = None

    Course_Eligibility__c: Optional[str] = None


    # --------------------------------------
    # Lead Evaluation
    # --------------------------------------

    Lead_Score__c: Optional[float] = None
    Lead_Category__c: Optional[str] = None


    # --------------------------------------
    # Admission Decision
    # --------------------------------------

    Admission_Status__c: Optional[str] = None
    Approved_By__c: Optional[str] = None


    # --------------------------------------
    # Token
    # --------------------------------------

    Token_Status__c: Optional[str] = None
    Token__c: Optional[str] = None


    # --------------------------------------
    # Sentiment
    # --------------------------------------

    Sentiment__c: Optional[str] = None


    # --------------------------------------
    # Offer
    # --------------------------------------

    Offer_Status__c: Optional[str] = None
    Offer_Sent_At__c: Optional[str] = None

    Offer_Letter_Released__c: Optional[bool] = None
    Offer_Letter_Accepted__c: Optional[str] = None


    # --------------------------------------
    # University / Other
    # --------------------------------------

    University_ID__c: Optional[str] = None
    Remarks__c: Optional[str] = None

    Created_At__c: Optional[str] = None
    Updated_At__c: Optional[str] = None

    Testing_Record__c: Optional[bool] = False


# ==========================================
# Update Admission Application
# ==========================================

class AdmissionUpdate(BaseModel):

    # --------------------------------------
    # Application / User
    # --------------------------------------

    User_ID__c: Optional[str] = None
    Conversation_ID__c: Optional[str] = None


    # --------------------------------------
    # Applicant Information
    # --------------------------------------

    First_Name__c: Optional[str] = None
    Last_Name__c: Optional[str] = None
    Email__c: Optional[str] = None
    Phone__c: Optional[str] = None
    City__c: Optional[str] = None
    Gender__c: Optional[str] = None


    # --------------------------------------
    # Program Information
    # --------------------------------------

    Education_Level__c: Optional[str] = None
    Course__c: Optional[str] = None
    Major__c: Optional[str] = None
    Advising_College__c: Optional[str] = None
    Intake__c: Optional[str] = None
    Semester__c: Optional[str] = None
    Residency__c: Optional[str] = None


    # --------------------------------------
    # Academic / IELTS Evaluation
    # --------------------------------------

    Academic_Percentage__c: Optional[float] = None
    Original_CGPA__c: Optional[float] = None
    Converted_Percentage__c: Optional[float] = None
    IELTS_Overall_Score__c: Optional[float] = None

    Course_Eligibility__c: Optional[str] = None


    # --------------------------------------
    # Lead Evaluation
    # --------------------------------------

    Lead_Score__c: Optional[float] = None
    Lead_Category__c: Optional[str] = None


    # --------------------------------------
    # Admission Decision
    # --------------------------------------

    Admission_Status__c: Optional[str] = None
    Approved_By__c: Optional[str] = None


    # --------------------------------------
    # Token
    # --------------------------------------

    Token_Status__c: Optional[str] = None
    Token__c: Optional[str] = None


    # --------------------------------------
    # Sentiment
    # --------------------------------------

    Sentiment__c: Optional[str] = None


    # --------------------------------------
    # Offer
    # --------------------------------------

    Offer_Status__c: Optional[str] = None
    Offer_Sent_At__c: Optional[str] = None

    Offer_Letter_Released__c: Optional[bool] = None
    Offer_Letter_Accepted__c: Optional[str] = None


    # --------------------------------------
    # University / Other
    # --------------------------------------

    University_ID__c: Optional[str] = None
    Remarks__c: Optional[str] = None

    Updated_At__c: Optional[str] = None

    Testing_Record__c: Optional[bool] = None
