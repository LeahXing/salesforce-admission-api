# ==========================================
# Salesforce Document Repository
# ==========================================

import base64
from pathlib import Path

from simple_salesforce.format import format_soql

from app.core.salesforce import get_salesforce


# ==========================================
# 1. Get Admission Application
# ==========================================

def get_customer_by_application_no(
    application_no: str,
):
    """
    Find the Customer record representing
    the admission application.
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
# 2. Get Documents by Application
# ==========================================

def get_documents_by_application(
    customer_id: str,
):
    """
    Get all uploaded documents belonging
    to one admission application.
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

def get_document_by_id(
    content_version_id: str,
):
    """
    Get metadata for one Salesforce
    ContentVersion record.
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
# 4. Get Actual Document File Content
# ==========================================

def get_document_content(
    content_version_id: str,
):
    """
    Download the actual file content
    from Salesforce VersionData.
    """

    sf = get_salesforce()

    # Salesforce REST endpoint for the
    # binary ContentVersion file
    content_url = (
        f"{sf.base_url}"
        f"sobjects/ContentVersion/"
        f"{content_version_id}/VersionData"
    )

    response = sf.session.get(
        content_url,
        headers=sf.headers,
        timeout=60,
    )

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
):
    """
    Upload one completed document
    to Salesforce ContentVersion.
    """

    sf = get_salesforce()

    encoded_file = base64.b64encode(
        file_content
    ).decode("utf-8")

    title = Path(file_name).stem

    content_version_data = {
        "Title": title,
        "PathOnClient": file_name,
        "VersionData": encoded_file,

        # Link the document to Customer
        "Application__c": customer_id,

        "Document_Type__c": document_type,
        "Source__c": source,

        # New document starts as Pending
        "Verification_Status__c": "Pending",
    }

    return sf.ContentVersion.create(
        content_version_data
    )


# ==========================================
# 6. Update Document Verification
# ==========================================

def update_document_verification(
    content_version_id: str,
    verification_data: dict,
):
    """
    Update verification fields
    on a ContentVersion record.
    """

    sf = get_salesforce()

    return sf.ContentVersion.update(
        content_version_id,
        verification_data,
    )
#====test2====