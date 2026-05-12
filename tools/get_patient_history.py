from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists


async def get_patient_longitudinal_history(
    patientId: Annotated[
        str | None,
        Field(description="Patient ID — optional if FHIR context is provided by the platform"),
    ] = None,
    ctx: Context = None,
) -> dict:
    """Read the patient's full longitudinal FHIR history: conditions, labs, medications, procedures, family history, diagnostic reports, and allergies."""

    fhir_context = get_fhir_context(ctx)
    if not fhir_context:
        return {"error": "No FHIR context available. Enable FHIR context in the platform settings."}

    if not patientId:
        patientId = get_patient_id_if_context_exists(ctx)
    if not patientId:
        return {"error": "No patient ID found in context or arguments."}

    client = FhirClient(base_url=fhir_context.url, token=fhir_context.token)

    history: dict = {
        "patient_id": patientId,
        "conditions": [],
        "observations": [],
        "medications": [],
        "procedures": [],
        "family_history": [],
        "diagnostic_reports": [],
        "allergies": [],
    }

    # --- Conditions ---
    conditions_bundle = await client.search("Condition", {"patient": patientId, "_count": "100"})
    if conditions_bundle and "entry" in conditions_bundle:
        for entry in conditions_bundle["entry"]:
            r = entry.get("resource", {})
            code = r.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            status_coding = (
                r.get("clinicalStatus", {}).get("coding", [{}])[0]
                if r.get("clinicalStatus")
                else {}
            )
            history["conditions"].append({
                "display": coding.get("display") or code.get("text", "Unknown"),
                "code": coding.get("code", ""),
                "system": coding.get("system", ""),
                "onset": r.get("onsetDateTime", r.get("onsetString", r.get("recordedDate", ""))),
                "status": status_coding.get("code", ""),
            })

    # --- Observations (labs + vitals) ---
    obs_bundle = await client.search(
        "Observation",
        {"patient": patientId, "_count": "200", "_sort": "-date"},
    )
    if obs_bundle and "entry" in obs_bundle:
        for entry in obs_bundle["entry"]:
            r = entry.get("resource", {})
            code = r.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            value_qty = r.get("valueQuantity", {})
            interp_list = r.get("interpretation", [])
            interp = (
                interp_list[0].get("coding", [{}])[0].get("code", "")
                if interp_list
                else ""
            )
            history["observations"].append({
                "name": coding.get("display") or code.get("text", "Unknown"),
                "code": coding.get("code", ""),
                "value": (
                    f"{value_qty.get('value', '')} {value_qty.get('unit', '')}".strip()
                    if value_qty
                    else r.get("valueString", "")
                ),
                "interpretation": interp,
                "date": r.get("effectiveDateTime", ""),
                "abnormal": interp in {"H", "L", "A", "HH", "LL", "AA", "POS"},
            })

    # --- Medications ---
    meds_bundle = await client.search("MedicationRequest", {"patient": patientId, "_count": "50"})
    if meds_bundle and "entry" in meds_bundle:
        for entry in meds_bundle["entry"]:
            r = entry.get("resource", {})
            med = r.get("medicationCodeableConcept", {})
            coding = med.get("coding", [{}])[0] if med.get("coding") else {}
            history["medications"].append({
                "name": coding.get("display") or med.get("text", "Unknown"),
                "status": r.get("status", ""),
                "date": r.get("authoredOn", ""),
            })

    # --- Procedures ---
    proc_bundle = await client.search("Procedure", {"patient": patientId, "_count": "50"})
    if proc_bundle and "entry" in proc_bundle:
        for entry in proc_bundle["entry"]:
            r = entry.get("resource", {})
            code = r.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            history["procedures"].append({
                "name": coding.get("display") or code.get("text", "Unknown"),
                "status": r.get("status", ""),
                "date": r.get("performedDateTime", ""),
            })

    # --- Family History (critical for rare/hereditary diseases) ---
    fmh_bundle = await client.search("FamilyMemberHistory", {"patient": patientId, "_count": "50"})
    if fmh_bundle and "entry" in fmh_bundle:
        for entry in fmh_bundle["entry"]:
            r = entry.get("resource", {})
            relationship = r.get("relationship", {})
            rel_coding = relationship.get("coding", [{}])[0] if relationship.get("coding") else {}
            conditions_fmh = []
            for cond in r.get("condition", []):
                c_code = cond.get("code", {})
                c_coding = c_code.get("coding", [{}])[0] if c_code.get("coding") else {}
                conditions_fmh.append(
                    c_coding.get("display") or c_code.get("text", "Unknown condition")
                )
            history["family_history"].append({
                "relationship": rel_coding.get("display") or relationship.get("text", "Unknown"),
                "conditions": conditions_fmh,
                "deceased": r.get("deceasedBoolean", False),
            })

    # --- Diagnostic Reports (genetic tests, imaging, lab panels) ---
    dr_bundle = await client.search(
        "DiagnosticReport",
        {"patient": patientId, "_count": "50", "_sort": "-date"},
    )
    if dr_bundle and "entry" in dr_bundle:
        for entry in dr_bundle["entry"]:
            r = entry.get("resource", {})
            code = r.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            history["diagnostic_reports"].append({
                "name": coding.get("display") or code.get("text", "Unknown"),
                "status": r.get("status", ""),
                "date": r.get("effectiveDateTime", r.get("issued", "")),
                "conclusion": r.get("conclusion", ""),
            })

    # --- Allergies & Intolerances ---
    allergy_bundle = await client.search("AllergyIntolerance", {"patient": patientId, "_count": "50"})
    if allergy_bundle and "entry" in allergy_bundle:
        for entry in allergy_bundle["entry"]:
            r = entry.get("resource", {})
            code = r.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            reactions = []
            for reaction in r.get("reaction", []):
                for manifestation in reaction.get("manifestation", []):
                    m_coding = manifestation.get("coding", [{}])[0] if manifestation.get("coding") else {}
                    reactions.append(m_coding.get("display") or manifestation.get("text", ""))
            history["allergies"].append({
                "substance": coding.get("display") or code.get("text", "Unknown"),
                "type": r.get("type", ""),
                "criticality": r.get("criticality", ""),
                "reactions": reactions,
            })

    return history
