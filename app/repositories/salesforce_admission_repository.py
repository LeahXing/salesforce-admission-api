"""Salesforce Customer admission repository with versioned document audit history."""
import json
from datetime import datetime, timezone
from app.core.salesforce import get_salesforce

MAX_FIELD_LENGTH = 32768


def get_all_admissions():
    sf = get_salesforce()
    result = sf.query_all("""SELECT Id, Application_No__c, User_ID__c, Conversation_ID__c,
        Student_ID__c, First_Name__c, Last_Name__c, Email__c, Phone__c, City__c,
        Gender__c, Education_Level__c, Course__c, Major__c, Advising_College__c,
        Intake__c, Semester__c, Residency__c, Academic_Percentage__c,
        Original_CGPA__c, Converted_Percentage__c, IELTS_Overall_Score__c,
        Course_Eligibility__c, Lead_Score__c, Lead_Category__c, Admission_Status__c,
        Approved_By__c, Token_Status__c, Token__c, Sentiment__c, Offer_Status__c,
        Offer_Letter_Released__c, Offer_Letter_Accepted__c, Offer_Sent_At__c,
        University_ID__c, Remarks__c, Created_At__c, Updated_At__c, Testing_Record__c
        FROM Customer ORDER BY CreatedDate DESC""")
    return result["records"]


def get_admission_by_id(application_id):
    return get_salesforce().Customer.get(application_id)


def create_admission(admission_data):
    payload = admission_data.copy()
    payload["Name"] = payload["Application_No__c"]
    return get_salesforce().Customer.create(payload)


def update_admission(application_id, admission_data):
    return get_salesforce().Customer.update(application_id, admission_data)


def delete_admission(application_id):
    return get_salesforce().Customer.delete(application_id)


def read_document_validation_state(customer_id: str, program: str) -> dict:
    """Read the Customer's history without modifying older/unknown schemas."""
    raw = get_admission_by_id(customer_id).get("Document_Validation_Results__c")
    if not raw:
        return {"document_history": []}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid existing Customer validation JSON; migration required") from exc
    if isinstance(data, dict) and isinstance(data.get("document_history"), list) and set(data) == {"document_history"}:
        return data
    raise ValueError("Existing Customer JSON uses a different schema; migrate it before uploading")


def update_customer_document_validation(
    customer_id: str, program: str, document_results: list[dict],
    course_eligibility: str, *, state: dict | None = None,
):
    """Persist exactly one document_history array and the derived eligibility."""
    if course_eligibility not in {"Not Evaluated", "Eligible", "Not Eligible"}:
        raise ValueError(f"Invalid Course_Eligibility__c: {course_eligibility}")
    if state is None:
        raise ValueError("Direct evaluate-and-save is disabled to protect document history; use upload-and-verify")
    if not isinstance(state, dict) or set(state) != {"document_history"} or not isinstance(state["document_history"], list):
        raise ValueError("Expected JSON object containing only document_history")
    encoded = json.dumps(
        state,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    if len(encoded) > MAX_FIELD_LENGTH:
        raise ValueError("Document history exceeds Salesforce field capacity; move history to a child object")
    get_salesforce().Customer.update(customer_id, {
        "Document_Validation_Results__c": encoded,
        "Course_Eligibility__c": course_eligibility,
    })
    return {"customer_id": customer_id, "course_eligibility": course_eligibility,
            "document_results_saved": True, "history_count": len(state["document_history"])}
