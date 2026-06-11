"""
F2 — Patient health report (PDF).

Aggregates the patient's recent blood pressure, medication adherence and
biometric alerts into a single PDF intended to be taken to the doctor.
Generated server-side with fpdf2 (pure Python, no system dependencies, so it
deploys cleanly on Fly/Vercel).
"""
from datetime import datetime, timezone
from typing import Any, Dict

from fpdf import FPDF

from src._config.logger import get_logger
from src.domains.health.services import HealthService
from src.domains.medications.services import MedicationService
from src.domains.events.models import BiometricEventDB

logger = get_logger(__name__)

_STAGE_LABELS = {
    "normal": "Normal",
    "elevated": "Elevada",
    "stage_1": "Hipertension 1",
    "stage_2": "Hipertension 2",
    "hypertensive_crisis": "Crisis",
}
_SEVERITY_LABELS = {"critical": "CRITICA", "warning": "Alerta", "info": "Info"}


def _safe(value: Any) -> str:
    """Render any value as a latin-1-safe string (fpdf2 core fonts use latin-1)."""
    return str(value if value is not None else "").encode("latin-1", "replace").decode("latin-1")


def build_patient_report_pdf(data: Dict[str, Any]) -> bytes:
    """Render the aggregated report dict into PDF bytes."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def h1(t):
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 11, text=_safe(t), new_x="LMARGIN", new_y="NEXT")

    def h2(t):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, text=_safe(t), new_x="LMARGIN", new_y="NEXT")

    def para(t, size=11, style=""):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, 6, text=_safe(t))

    def trow(cells, widths, header=False):
        pdf.set_font("Helvetica", "B" if header else "", 10)
        if header:
            pdf.set_fill_color(235, 235, 245)
        for txt, w in zip(cells, widths):
            pdf.cell(w, 7, text=_safe(txt), border=1, fill=header)
        pdf.ln()

    # --- Header ---
    h1("Reporte de salud")
    para(f"Paciente: {data.get('patient_name', 'Paciente')}", style="B")
    para(f"Generado: {data.get('generated_at', '')}   |   Periodo: ultimos 30 dias")

    # --- Blood pressure ---
    h2("Presion arterial")
    bp = data.get("bp") or {}
    if bp.get("count"):
        avg_s, avg_d = bp.get("avg_systolic"), bp.get("avg_diastolic")
        if avg_s and avg_d:
            para(f"Promedio: {avg_s}/{avg_d} mmHg  ({bp['count']} mediciones)")
        trow(["Fecha", "Sis/Dia", "Pulso", "Clasificacion"], [45, 35, 25, 75], header=True)
        for r in bp.get("readings", [])[:15]:
            trow([
                r.get("date", ""),
                f"{r.get('systolic', '-')}/{r.get('diastolic', '-')}",
                r.get("pulse") if r.get("pulse") is not None else "-",
                _STAGE_LABELS.get(r.get("stage"), r.get("stage") or "-"),
            ], [45, 35, 25, 75])
    else:
        para("Sin mediciones de presion en el periodo.")

    # --- Adherence ---
    h2("Adherencia a la medicacion")
    adh = data.get("adherence")
    if adh and adh.get("medications"):
        para(f"Adherencia general: {adh.get('overall', 0)}%")
        trow(["Medicamento", "Adherencia", "Dias tomados"], [95, 45, 40], header=True)
        for m in adh["medications"]:
            trow(
                [m.get("name", ""), f"{m.get('pct', 0)}%", f"{m.get('days_taken', 0)}/{m.get('total_days', 0)}"],
                [95, 45, 40],
            )
    else:
        para("Sin medicamentos registrados.")

    # --- Alerts / events ---
    h2("Alertas y eventos recientes")
    events = data.get("events") or []
    if events:
        for e in events:
            sev = _SEVERITY_LABELS.get(e.get("severity"), e.get("severity", ""))
            para(f"- [{sev}] {e.get('date', '')}: {e.get('message', '')}", size=10)
    else:
        para("Sin alertas recientes.")

    # --- Footer ---
    pdf.ln(5)
    para("Generado por Hacking Health. Documento informativo; no sustituye la valoracion medica.", size=9, style="I")

    return bytes(pdf.output())


class PatientReportService:
    """Builds the patient health report PDF from existing domain services."""

    def __init__(self, db):
        self.db = db

    async def gather_report_data(self, patient_id: str) -> Dict[str, Any]:
        """Pull BP, adherence and recent events. Each section degrades gracefully."""
        now = datetime.now(timezone.utc)
        data: Dict[str, Any] = {
            "patient_name": "Paciente",
            "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
            "bp": {"count": 0, "avg_systolic": None, "avg_diastolic": None, "readings": []},
            "adherence": None,
            "events": [],
        }

        # Blood pressure (last 30 days)
        try:
            bp = await HealthService(self.db).get_patient_blood_pressure_readings(patient_id, days=30, limit=50)
            data["patient_name"] = bp.get("patient_name") or "Paciente"
            readings = bp.get("readings") or []
            sys_vals = [r["systolic"] for r in readings if r.get("systolic")]
            dia_vals = [r["diastolic"] for r in readings if r.get("diastolic")]
            data["bp"] = {
                "count": len(readings),
                "avg_systolic": round(sum(sys_vals) / len(sys_vals)) if sys_vals else None,
                "avg_diastolic": round(sum(dia_vals) / len(dia_vals)) if dia_vals else None,
                "readings": readings,
            }
        except Exception as e:
            logger.warning(f"report: BP section failed for {patient_id}: {e}")

        # Medication adherence (current month)
        try:
            rep = await MedicationService(self.db).get_monthly_report(patient_id, now.year, now.month)
            data["adherence"] = {
                "overall": round(rep.get("overallAdherence", 0), 1),
                "medications": [
                    {
                        "name": m.get("medicationName", ""),
                        "pct": round(m.get("adherencePercentage", 0), 1),
                        "days_taken": m.get("daysTaken", 0),
                        "total_days": m.get("totalDays", 0),
                    }
                    for m in (rep.get("medications") or [])
                ],
            }
        except Exception as e:
            logger.warning(f"report: adherence section failed for {patient_id}: {e}")

        # Recent biometric events / alerts (read-only — does not mark them read)
        try:
            cursor = (
                self.db[BiometricEventDB.COLLECTION_NAME]
                .find({"patientId": patient_id})
                .sort("recordedAt", -1)
                .limit(15)
            )
            async for ev in cursor:
                ra = ev.get("recordedAt")
                data["events"].append({
                    "severity": ev.get("severity", "info"),
                    "message": ev.get("message", ""),
                    "date": ra.strftime("%Y-%m-%d %H:%M") if hasattr(ra, "strftime") else "",
                })
        except Exception as e:
            logger.warning(f"report: events section failed for {patient_id}: {e}")

        return data

    async def generate_pdf(self, patient_id: str) -> bytes:
        data = await self.gather_report_data(patient_id)
        return build_patient_report_pdf(data)
