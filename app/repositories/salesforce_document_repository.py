# ==========================================
# Salesforce Document Repository
# ==========================================

import base64
from datetime import datetime, timezone
from pathlib import Path

from simple_salesforce.format import format_soql

from app.core.salesforce import get_salesforce


# ==========================================
# Salesforce Picklist Value Mappings
# ==========================================

DOCUMENT_TYPE_TO_SF = {
    "ID_PROOF": "ID Document",
    "CLASS_12_MARKSHEET": "12th Marksheet",
    "UNDERGRADUATE_TRANSCRIPT": "Academic Transcript",
    "SAT": "Test Score",
    "GRE": "Test Score",
    "GMAT": "Test Score",
    "TOEFL": "Test Score",
    "IELTS": "IELTS",
}

SOURCE_TO_SF = {
    "API": "Internal Upload",
    "WEB": "Web",
    "WHATSAPP": "WhatsApp",
    "CHATBOT": "Chatbot",
    "EMAIL": "Email",
    "INTERNAL UPLOAD": "Internal Upload",
    "OTHER": "Other",
}

VERIFICATION_TO_SF = {
    "PASSED": "ELIGIBLE",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
    "FAILED": "FAILED",
    "ELIGIBLE": "ELIGIBLE",
    "NOT_ELIGIBLE": "NOT_ELIGIBLE",
}


def _map_value(value: str, mapping: dict[str, str], field_name: str) -> str:
    """Translate an API value to an allowed Salesforce picklist value."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string; received {value!r}")
    mapped = mapping.get(value.strip().upper())
    if mapped is None:
        raise ValueError(f"Unsupported {field_name}: {value!r}")
    return mapped


# ==========================================
# 1. Get Admission Application
# ==========================================

def get_customer_by_application_no(application_no: str):
    """Find the Customer record representing the admission application."""
    sf = get_salesforce()
    query = format_soql(
        """
        SELECT
            Id,
            Application_No__c,
            Course__c,
            Education_Level__c
        FROM Customer
        WHERE Application_No__c = {}
        LIMIT 1
        """,
        application_no,
    )
    result = sf.query(query)
    if result["totalSize"] == 0:
        return None
    return result["records"][0]


# ==========================================
# 2. Get Documents by Application
# ==========================================

def get_documents_by_application(customer_id: str):
    """Get all uploaded documents belonging to one admission application."""
    sf = get_salesforce()
    query = format_soql(
        """
        SELECT
            Id,
            ContentDocumentId,
            Title,
            PathOnClient,
            FileExtension,
            ContentSize,
            CreatedDate,
            Application__c,
            Document_Type__c,
            Source__c,
            Verification_Status__c,
            Failed_Reason__c,
            Verified_By__c,
            Verified_At__c
        FROM ContentVersion
        WHERE Application__c = {}
        ORDER BY CreatedDate DESC
        """,
        customer_id,
    )
    result = sf.query_all(query)
    return result["records"]


# ==========================================
# 3. Get Document by ID
# ==========================================

def get_document_by_id(content_version_id: str):
    """Get metadata for one Salesforce ContentVersion record."""
    sf = get_salesforce()
    query = format_soql(
        """
        SELECT
            Id,
            ContentDocumentId,
            Title,
            PathOnClient,
            FileExtension,
            ContentSize,
            CreatedDate,
            Application__c,
            Document_Type__c,
            Source__c,
            Verification_Status__c,
            Failed_Reason__c,
            Verified_By__c,
            Verified_At__c
        FROM ContentVersion
        WHERE Id = {}
        LIMIT 1
        """,
        content_version_id,
    )
    result = sf.query(query)
    if result["totalSize"] == 0:
        return None
    return result["records"][0]


# ==========================================
# 4. Get Actual Document File Content
# ==========================================

def get_document_content(content_version_id: str):
    """Download the actual file content from Salesforce VersionData."""
    sf = get_salesforce()
    content_url = (
        f"{sf.base_url}"
        f"sobjects/ContentVersion/"
        f"{content_version_id}/VersionData"
    )
    response = sf.session.get(content_url, headers=sf.headers, timeout=60)
    response.raise_for_status()
    return response.content


# ==========================================
# 5. Create Document
# ==========================================

def create_document(
    customer_id: str,
    file_name: str,
    file_content: bytes,
    document_type: str,
    source: str,
    verification_status: str,
    failed_reason: str | None = None,
    verified_by: str | None = None,
):
    """Upload an evaluated document to Salesforce ContentVersion."""
    # Validate all restricted picklist values before making a Salesforce write.
    sf_document_type = _map_value(document_type, DOCUMENT_TYPE_TO_SF, "document_type")
    sf_source = _map_value(source, SOURCE_TO_SF, "source")
    sf_status = _map_value(
        verification_status, VERIFICATION_TO_SF, "verification_status"
    )

    sf = get_salesforce()
    encoded_file = base64.b64encode(file_content).decode("utf-8")
    title = Path(file_name).stem

    content_version_data = {
        "Title": title,
        "PathOnClient": file_name,
        "VersionData": encoded_file,
        "Application__c": customer_id,
        "Document_Type__c": sf_document_type,
        "Source__c": sf_source,
        "Verification_Status__c": sf_status,
    }

    if sf_status in {"FAILED", "NOT_ELIGIBLE", "REVIEW_REQUIRED"} and failed_reason:
        content_version_data["Failed_Reason__c"] = failed_reason

    if verified_by:
        content_version_data["Verified_By__c"] = verified_by

    # The upload-and-verify service has completed evaluation before calling us.
    content_version_data["Verified_At__c"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    return sf.ContentVersion.create(content_version_data)


# ==========================================
# 6. Update Document Verification
# ==========================================

def update_document_verification(
    content_version_id: str,
    verification_data: dict,
):
    """Update verification fields on a ContentVersion record."""
    update_data = dict(verification_data)
    if "Verification_Status__c" in update_data:
        update_data["Verification_Status__c"] = _map_value(
            update_data["Verification_Status__c"],
            VERIFICATION_TO_SF,
            "verification_status",
        )
    sf = get_salesforce()
    return sf.ContentVersion.update(content_version_id, update_data)
