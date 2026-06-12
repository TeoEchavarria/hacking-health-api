"""
F2 — Patient health report (PDF) endpoints.

- GET /reports/me/pdf                      → the patient's own report
- GET /reports/patients/{patient_id}/pdf   → a caregiver's report for a LINKED patient

The caregiver path is authorized with require_caregiver_access (404 if the
patient is unknown, 403 if there is no active pairing).
"""
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.core.database import get_database
from src.core.authorization import require_caregiver_access
from src.domains.auth.routes import verify_token, verify_token_jwt
from src.domains.reports.service import PatientReportService

router = APIRouter(prefix="/reports", tags=["reports"])


def _pdf_response(pdf_bytes: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/me/pdf")
async def my_report_pdf(user_id: str = Depends(verify_token), db=Depends(get_database)):
    """Generate the authenticated patient's own health report PDF."""
    pdf = await PatientReportService(db).generate_pdf(user_id)
    return _pdf_response(pdf, "reporte-salud.pdf")


@router.get("/patients/{patient_id}/pdf")
async def patient_report_pdf(
    patient_id: str,
    user_id: str = Depends(verify_token_jwt),
    db=Depends(get_database),
):
    """Generate a linked patient's health report PDF (caregiver-facing)."""
    await require_caregiver_access(patient_id, user_id, db)  # 404/403 if not linked
    pdf = await PatientReportService(db).generate_pdf(patient_id)
    return _pdf_response(pdf, f"reporte-{patient_id}.pdf")
