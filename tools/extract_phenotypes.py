import json
import os

from google import genai
from google.genai import types
from mcp.server.fastmcp import Context


def _get_client():
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))


async def extract_phenotype_signals(
    patient_history: dict,
    ctx: Context = None,
) -> dict:
    """Convert FHIR clinical findings into HPO phenotype terms for rare disease matching."""

    conditions = patient_history.get("conditions", [])
    abnormal_obs = [o for o in patient_history.get("observations", []) if o.get("abnormal")]
    medications = patient_history.get("medications", [])

    if not conditions and not abnormal_obs:
        return {"hpo_terms": [], "clinical_summary": "No clinical findings found in patient record."}

    conditions_text = "\n".join(
        f"- {c['display']} (onset: {c.get('onset', 'unknown')}, status: {c.get('status', '')})"
        for c in conditions
    )
    abnormal_text = "\n".join(
        f"- {o['name']}: {o['value']} (flag: {o['interpretation']}, date: {o['date']})"
        for o in abnormal_obs[:30]
    )
    meds_text = "\n".join(f"- {m['name']} ({m.get('status', '')})" for m in medications[:20])

    prompt = f"""You are a clinical genetics specialist with expertise in rare disease diagnosis.

Convert the following patient findings into Human Phenotype Ontology (HPO) terms.

DOCUMENTED CONDITIONS:
{conditions_text or "None"}

ABNORMAL LAB / OBSERVATION FINDINGS:
{abnormal_text or "None"}

CURRENT / PAST MEDICATIONS (may hint at underlying conditions):
{meds_text or "None"}

Instructions:
- Map each significant finding to its most specific valid HPO term
- Include phenotypes implied by abnormal labs (e.g., elevated ANA → HP:0003613 Antinuclear antibody positive)
- Focus on phenotypes that could indicate a rare or undiagnosed disease
- Ignore common benign findings

Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "hpo_terms": [
    {{"id": "HP:0001234", "name": "Term name", "source": "brief note on which finding maps to this", "confidence": "high|medium|low"}}
  ],
  "clinical_summary": "2-3 sentence narrative of the patient's phenotype profile and why it warrants rare disease investigation"
}}"""

    client = _get_client()
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)

    text = response.text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "hpo_terms": [],
            "clinical_summary": text,
            "parse_error": "Could not parse structured HPO terms from LLM response",
        }
