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
    description: str | None = None,
):
    """
    Upload one completed document to Salesforce ContentVersion.

    File chunking and reassembly are handled by the service layer
    before this function is called.
    """

    sf = get_salesforce()

    # Encode the completed file for Salesforce
    encoded_file = base64.b64encode(file_content).decode("utf-8")

    # Example: admission_call.mp3 -> admission_call
    title = Path(file_name).stem

    content_version_data = {
        "Title": title,
        "PathOnClient": file_name,
        "VersionData": encoded_file,

        # Connect the document to the admission application
        "Application__c": customer_id,
        "FirstPublishLocationId": customer_id,

        # Document metadata
        "Document_Type__c": document_type,
        "Source__c": source,
    }

    # Add description only when provided
    if description:
        content_version_data["Description"] = description

    return sf.ContentVersion.create(content_version_data)


# ==========================================
# Get Document Metadata
# ==========================================

def get_document_by_id(content_version_id: str):
    """
    Get metadata for an uploaded Salesforce document.
    """

    sf = get_salesforce()

    query = format_soql(
        """
        SELECT
            Id,
            Title,
            PathOnClient,
            FileExtension,
            ContentSize,
            CreatedDate,
            Description,
            Document_Type__c,
            Source__c,
            Application__c
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
