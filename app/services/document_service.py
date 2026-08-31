from app.repositories.salesforce_document_repository import (
    get_customer_by_application_no,
    create_document,
    get_document_by_id,
)


def upload_admission_document(
    application_no: str,
    file_name: str,
    file_content: bytes,
    document_type: str,
    source: str,
    description: str | None = None,
):
    """
    Upload a document for an admission application.
    """

    # Find Customer using the application number
    customer = get_customer_by_application_no(application_no)

    if customer is None:
        raise ValueError(
            f"Application {application_no} was not found."
        )

    customer_id = customer["Id"]

    # Upload the file to Salesforce ContentVersion
    result = create_document(
        customer_id=customer_id,
        file_name=file_name,
        file_content=file_content,
        document_type=document_type,
        source=source,
        description=description,
    )

    content_version_id = result["id"]

    # Get the uploaded document metadata
    document = get_document_by_id(content_version_id)

    return {
        "application_no": application_no,
        "document": document,
    }
