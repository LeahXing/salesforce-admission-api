import base64
from pathlib import Path

from simple_salesforce.format import format_soql

from app.core.salesforce import get_salesforce


def get_customer_by_application_no(application_no: str):
    """
    Find a Customer admission record using Application_No__c.
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


def create_document(
    customer_id: str,
    file_name: str,
    file_content: bytes,
    document_type: str,
    source: str,
    description: str | None = None,
):
    """
    Upload a document to Salesforce ContentVersion.
    """

    sf = get_salesforce()

    # Convert file bytes to base64 for Salesforce
    encoded_file = base64.b64encode(file_content).decode("utf-8")

    # Example:
    # file_name = "admission_call.mp3"
    # title = "admission_call"
    title = Path(file_name).stem

    content_version_data = {
        "Title": title,
        "PathOnClient": file_name,
        "VersionData": encoded_file,

        # Link document to Customer admission application
        "Application__c": customer_id,
        "FirstPublishLocationId": customer_id,

        # Custom document metadata
        "Document_Type__c": document_type,
        "Source__c": source,
    }

    if description:
        content_version_data["Description"] = description

    return sf.ContentVersion.create(content_version_data)


def get_document_by_id(content_version_id: str):
    """
    Get uploaded document metadata from Salesforce.
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
