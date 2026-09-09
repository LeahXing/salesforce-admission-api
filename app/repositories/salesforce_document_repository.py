import base64
from pathlib import Path

from simple_salesforce.format import format_soql

from app.core.salesforce import get_salesforce


# ==========================================
# Get Admission Application
# ==========================================

def get_customer_by_application_no(application_no: str):
    """
    Find the Customer record representing the admission application.
    """

    sf = get_salesforce()

    query = format_soql(
        """
        SELECT
            Id,
            Application_No__c
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
# Create Document
# ==========================================

def create_document(
    customer_id: str,
    file_name: str,
    file_content: bytes,
    document_type: str,
    source: str,
):
    """
    Upload one completed document to Salesforce ContentVersion.

    File chunking and reassembly are handled by the service layer
    before this function is called.
    """

    sf = get_salesforce()

    # Encode completed file for Salesforce
    encoded_file = base64.b64encode(
        file_content
    ).decode("utf-8")

    # Example:
    # transcript.pdf -> transcript
    title = Path(file_name).stem

    content_version_data = {
        "Title": title,
        "PathOnClient": file_name,
        "VersionData": encoded_file,

        # Link document to admission application
        "Application__c": customer_id,

        # Document metadata
        "Document_Type__c": document_type,
        "Source__c": source,

        # New documents start as Pending
        "Verification_Status__c": "Pending",
    }

    return sf.ContentVersion.create(
        content_version_data
    )


# ==========================================
# Get Document Metadata
# ==========================================

def get_document_by_id(content_version_id: str):
    """
    Get metadata for one Salesforce document.
    """

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
            Rejection_Reason__c,
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
# Update Document Verification
# ==========================================

def update_document_verification(
    content_version_id: str,
    verification_data: dict,
):
    """
    Update document verification fields.
    """

    sf = get_salesforce()

    return sf.ContentVersion.update(
        content_version_id,
        verification_data,
    )
