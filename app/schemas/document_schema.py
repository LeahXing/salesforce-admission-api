from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """
    Document information returned by the API.
    """

    application_no: str
    document_id: str
    file_name: str
    file_extension: Optional[str] = None
    upload_datetime: datetime
    document_type: str
    source: str
    description: Optional[str] = None
