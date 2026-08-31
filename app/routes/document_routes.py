from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.services.document_service import upload_admission_document


router = APIRouter(
    prefix="/admissions",
    tags=["Admission Documents"],
)


@router.post("/{application_no}/documents")
async def upload_document(
    application_no: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    source: str = Form(...),
    description: str | None = Form(None),
):
    try:
        # Read uploaded file
        file_content = await file.read()

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="File name is required.",
            )

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty.",
            )

        return upload_admission_document(
            application_no=application_no,
            file_name=file.filename,
            file_content=file_content,
            document_type=document_type,
            source=source,
            description=description,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
