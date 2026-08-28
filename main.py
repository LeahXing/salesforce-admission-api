from fastapi import FastAPI

from app.routes.admission_routes import router as admission_router


# ============================================================
# CREATE FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Salesforce Admission API",
    description="FastAPI integration with Salesforce admission data",
    version="1.0.0",
)


# ============================================================
# REGISTER ROUTERS
# ============================================================

app.include_router(admission_router)


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Salesforce Admission API is running"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "Salesforce Admission API",
    }
