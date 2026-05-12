from datetime import datetime, timezone
from typing import Annotated

import httpx
from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists


def _build_diagnostic_report(
    patient_id: str,
    atlas_report: dict,
    phenotype_profile: dict,
    disease_matches: list,
    clinvar_variants: list,
) -> dict:
    """Construct a FHIR R4 DiagnosticReport resource from the ATLAS analysis output."""

    report = atlas_report.get("atlas_report", atlas_report)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    top_candidates = report.get("top_candidates", [])
    executive_summary = report.get("executive_summary", "")
    confidence = report.get("atlas_confidence", "Moderate")
    delay_years = report.get("estimated_diagnostic_delay_years")
    red_flags = report.get("red_flags_missed", [])
    next_steps = report.get("immediate_next_steps", [])
    genetic_panels = report.get("genetic_panels_to_order", [])
    hpo_terms = phenotype_profile.get("hpo_terms", [])

    # Build conclusion text
    conclusion_parts = [f"ATLAS Rare Disease Diagnostic Analysis (Confidence: {confidence})"]
    conclusion_parts.append(f"\nSUMMARY: {executive_summary}")

    if delay_years:
        conclusion_parts.append(f"\nEstimated diagnostic delay: {delay_years} years")

    if top_candidates:
        conclusion_parts.append("\nTOP CANDIDATES:")
        for c in top_candidates[:3]:
            omim = c.get("omim", "")
            genes = ", ".join(c.get("causal_genes", []))
            conclusion_parts.append(
                f"  - {c['disease_name']} (strength: {c.get('match_strength','?')}"
                + (f", {omim}" if omim else "")
                + (f", genes: {genes}" if genes else "") + ")"
            )

    if red_flags:
        conclusion_parts.append("\nMISSED RED FLAGS:")
        for rf in red_flags[:3]:
            conclusion_parts.append(f"  - {rf}")

    if next_steps:
        conclusion_parts.append("\nIMMEDIATE NEXT STEPS:")
        for ns in next_steps[:4]:
            conclusion_parts.append(f"  - {ns}")

    if genetic_panels:
        conclusion_parts.append("\nGENETIC PANELS TO ORDER:")
        for gp in genetic_panels:
            conclusion_parts.append(f"  - {gp}")

    conclusion = "\n".join(conclusion_parts)

    # Build coded results as observation references placeholder
    # Each HPO term becomes a presentedForm entry
    presented_form = [{
        "contentType": "text/plain",
        "data": None,
        "title": "ATLAS Diagnostic Report",
        "creation": now,
    }]

    # Build extension for HPO terms
    hpo_extensions = []
    for term in hpo_terms[:10]:
        if isinstance(term, dict) and term.get("id", "").startswith("HP:"):
            hpo_extensions.append({
                "url": "https://hpo.jax.org/api/hpo/term/" + term["id"],
                "valueString": f"{term.get('name', '')} ({term['id']})",
            })

    # Build coded diagnosis references from top candidates
    coded_diagnoses = []
    for candidate in top_candidates[:3]:
        omim = candidate.get("omim", "")
        coding = [{"system": "https://monarchinitiative.org", "display": candidate["disease_name"]}]
        if omim and omim.startswith("OMIM:"):
            coding.append({
                "system": "https://omim.org",
                "code": omim.replace("OMIM:", ""),
                "display": candidate["disease_name"],
            })
        coded_diagnoses.append({"coding": coding, "text": candidate["disease_name"]})

    fhir_resource = {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "GE",
                        "display": "Genetics",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "81247-9",
                    "display": "Master HL7 genetic variant reporting panel",
                }
            ],
            "text": "ATLAS Rare Disease Diagnostic Analysis",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": now,
        "issued": now,
        "performer": [
            {
                "display": "ATLAS - AI Rare Disease Diagnostic Agent",
            }
        ],
        "conclusion": conclusion,
        "conclusionCode": coded_diagnoses,
        "extension": [
            {
                "url": "https://atlas-diagnostic-agent.onrender.com/fhir/extensions/atlas-confidence",
                "valueString": confidence,
            },
            {
                "url": "https://atlas-diagnostic-agent.onrender.com/fhir/extensions/hpo-terms",
                "extension": hpo_extensions,
            },
        ],
    }

    if delay_years:
        fhir_resource["extension"].append({
            "url": "https://atlas-diagnostic-agent.onrender.com/fhir/extensions/diagnostic-delay-years",
            "valueInteger": delay_years,
        })

    return fhir_resource


async def write_atlas_report_to_fhir(
    atlas_result: Annotated[
        dict,
        Field(description="The full result dict returned by RunATLASAnalysis"),
    ],
    patientId: Annotated[
        str | None,
        Field(description="Patient ID — optional if FHIR context is available"),
    ] = None,
    ctx: Context = None,
) -> dict:
    """Write the ATLAS diagnostic report back to the FHIR server as a DiagnosticReport resource.

    Takes the output of RunATLASAnalysis and persists it as a structured FHIR R4
    DiagnosticReport resource on the patient's EHR. This closes the loop: ATLAS reads
    from FHIR, reasons over the data, and writes its findings back — making the
    diagnosis available to every clinician who accesses the patient record.

    The report is written with status 'preliminary' and coded with LOINC 81247-9
    (genetic variant reporting panel), with HPO terms and candidate diagnoses
    encoded as structured FHIR extensions and conclusionCodes.
    """

    fhir_context = get_fhir_context(ctx)
    if not fhir_context:
        # Return the FHIR resource as a dry-run if no context available
        patient_id = patientId or "unknown"
        fhir_resource = _build_diagnostic_report(
            patient_id=patient_id,
            atlas_report=atlas_result,
            phenotype_profile=atlas_result.get("phenotype_profile", {}),
            disease_matches=atlas_result.get("disease_matches", []),
            clinvar_variants=atlas_result.get("clinvar_variants", []),
        )
        return {
            "status": "dry_run",
            "note": "No FHIR context available — returning resource without writing to EHR",
            "fhir_resource": fhir_resource,
        }

    if not patientId:
        patientId = get_patient_id_if_context_exists(ctx)
    if not patientId:
        return {"error": "No patient ID found. Cannot write DiagnosticReport without a patient reference."}

    fhir_resource = _build_diagnostic_report(
        patient_id=patientId,
        atlas_report=atlas_result,
        phenotype_profile=atlas_result.get("phenotype_profile", {}),
        disease_matches=atlas_result.get("disease_matches", []),
        clinvar_variants=atlas_result.get("clinvar_variants", []),
    )

    client = FhirClient(base_url=fhir_context.url, token=fhir_context.token)

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.post(
                f"{fhir_context.url.rstrip('/')}/DiagnosticReport",
                headers={
                    "Authorization": f"Bearer {fhir_context.token}",
                    "Content-Type": "application/fhir+json",
                    "Accept": "application/fhir+json",
                },
                json=fhir_resource,
            )

            if response.status_code in (200, 201):
                created = response.json()
                return {
                    "status": "written",
                    "diagnostic_report_id": created.get("id", ""),
                    "fhir_resource_url": f"{fhir_context.url.rstrip('/')}/DiagnosticReport/{created.get('id', '')}",
                    "patient_id": patientId,
                    "top_candidate": (
                        atlas_result.get("atlas_report", {})
                        .get("top_candidates", [{}])[0]
                        .get("disease_name", "")
                        if atlas_result.get("atlas_report", {}).get("top_candidates")
                        else ""
                    ),
                }
            else:
                # EHR rejected write (common on read-only sandboxes) — return dry run
                return {
                    "status": "rejected_by_ehr",
                    "http_status": response.status_code,
                    "note": "EHR returned an error — the FHIR server may be read-only. Returning the resource for review.",
                    "fhir_resource": fhir_resource,
                }

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "fhir_resource": fhir_resource,
        }
