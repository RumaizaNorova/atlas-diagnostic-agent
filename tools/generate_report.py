import json
import os
from typing import Annotated

import httpx
from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_utilities import get_patient_id_if_context_exists
from tools.extract_phenotypes import _call_claude, extract_phenotype_signals
from tools.get_patient_history import get_patient_longitudinal_history
from tools.match_rare_diseases import match_rare_diseases


async def run_atlas_analysis(
    patientId: Annotated[
        str | None,
        Field(description="Patient ID — optional if FHIR context is provided by the platform"),
    ] = None,
    ctx: Context = None,
) -> dict:
    """Run ATLAS full rare disease diagnostic analysis.

    Reads the patient's complete longitudinal FHIR history, extracts phenotype
    signals, matches against the Monarch Initiative rare disease database, and
    returns a structured diagnostic report with candidate diagnoses, missed red
    flags, and immediate next steps.
    """

    try:
        if not patientId and ctx:
            patientId = get_patient_id_if_context_exists(ctx)

        history = await get_patient_longitudinal_history(patientId=patientId, ctx=ctx)
        if "error" in history:
            return {"error": history["error"]}

        phenotypes = await extract_phenotype_signals(patient_history=history, ctx=ctx)

        disease_matches = await match_rare_diseases(
            hpo_terms=phenotypes.get("hpo_terms", []),
            ctx=ctx,
        )
    except Exception as exc:
        return {"error": f"ATLAS pipeline failed: {type(exc).__name__}: {exc}"}

    conditions = history.get("conditions", [])
    abnormal_obs = [o for o in history.get("observations", []) if o.get("abnormal")]
    onset_dates = sorted([c.get("onset", "") for c in conditions if c.get("onset")])

    conditions_text = "\n".join(
        f"- {c['display']} (onset: {c.get('onset', 'unknown')})"
        for c in conditions
    ) or "None documented"

    abnormal_text = "\n".join(
        f"- {o['name']}: {o['value']} (flag: {o['interpretation']}, date: {o['date']})"
        for o in abnormal_obs
    )[:2000] or "None documented"

    top_matches_text = "\n".join(
        f"- {m['disease_name']} | score: {m['similarity_score']} | {', '.join(m['omim_refs']) or 'no OMIM'}"
        for m in disease_matches.get("matches", [])[:5]
    ) or "No strong matches found"

    phenotype_summary = phenotypes.get("clinical_summary", "")
    earliest_onset = onset_dates[0] if onset_dates else "unknown"

    prompt = f"""You are ATLAS, an AI diagnostic agent specialising in rare disease identification.
A patient with a complex, unresolved clinical picture has been referred for rare disease evaluation.

PATIENT RECORD SUMMARY
Earliest documented symptom onset: {earliest_onset}

Documented conditions:
{conditions_text}

Abnormal findings:
{abnormal_text}

Phenotype profile extracted by ATLAS:
{phenotype_summary}

Top rare disease candidates (Monarch Initiative phenotype similarity):
{top_matches_text}

Generate a structured diagnostic report. Return ONLY valid JSON — no markdown, no explanation:
{{
  "executive_summary": "2-3 sentences summarising the diagnostic picture and why rare disease workup is warranted",
  "estimated_diagnostic_delay_years": <integer or null>,
  "top_candidates": [
    {{
      "disease_name": "...",
      "omim": "OMIM:XXXXXX or null",
      "match_strength": "Strong | Moderate | Weak",
      "supporting_evidence": ["specific finding from this patient's record", "..."],
      "recommended_confirmatory_tests": ["...", "..."]
    }}
  ],
  "red_flags_missed": ["specific finding + why it should have prompted workup", "..."],
  "immediate_next_steps": ["concrete clinical action", "..."],
  "atlas_confidence": "High | Moderate | Low",
  "atlas_confidence_rationale": "one sentence"
}}

Be specific to this patient's data. Top candidates: up to 3. Red flags: 3-5. Next steps: 4-5."""

    try:
        text = await _call_claude(prompt, max_tokens=2048)
    except Exception as exc:
        return {"error": f"Anthropic API failed: {type(exc).__name__}: {exc}"}

    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        report = {"executive_summary": text, "parse_error": True}

    return {
        "atlas_report": report,
        "phenotype_profile": {
            "hpo_terms": phenotypes.get("hpo_terms", []),
            "clinical_summary": phenotype_summary,
        },
        "disease_matches": disease_matches.get("matches", [])[:5],
        "data_points_analyzed": {
            "conditions": len(conditions),
            "total_observations": len(history.get("observations", [])),
            "abnormal_observations": len(abnormal_obs),
            "medications": len(history.get("medications", [])),
            "hpo_terms_extracted": len(phenotypes.get("hpo_terms", [])),
        },
    }
