from mcp.server.fastmcp import Context
from tools.extract_phenotypes import _call_claude


async def generate_patient_summary(
    atlas_result: dict,
    ctx: Context = None,
) -> dict:
    """Generate a plain-language summary of the ATLAS diagnostic findings for the patient.

    Translates the clinical diagnostic report into clear, compassionate language
    a patient can understand — no medical jargon, no HPO codes, no OMIM references.
    Explains what was found, what it might mean, and what happens next.
    """

    report = atlas_result.get("atlas_report", atlas_result)
    if not report or "executive_summary" not in report:
        return {"error": "Invalid ATLAS report. Run RunATLASAnalysis first."}

    top_candidates = report.get("top_candidates", [])
    next_steps = report.get("immediate_next_steps", [])
    delay_years = report.get("estimated_diagnostic_delay_years")
    confidence = report.get("atlas_confidence", "Moderate")
    executive_summary = report.get("executive_summary", "")
    red_flags = report.get("red_flags_missed", [])
    genetic_panels = report.get("genetic_panels_to_order", [])

    phenotype_profile = atlas_result.get("phenotype_profile", {})
    clinical_summary = phenotype_profile.get("clinical_summary", "")

    candidates_text = "\n".join(
        f"- {c['disease_name']}: {'; '.join(c.get('supporting_evidence', [])[:2])}"
        for c in top_candidates[:3]
    ) or "No specific candidates identified yet"

    steps_text = "\n".join(f"- {s}" for s in next_steps[:4]) or "Further workup needed"

    prompt = f"""You are writing a medical summary for a patient, not a clinician.
The patient may be scared, confused, and has likely been undiagnosed for a long time.
Write with warmth, clarity, and honesty. No jargon, no Latin terms, no abbreviations.

CLINICAL FINDINGS (translate these for the patient):
{executive_summary}

PATIENT'S SYMPTOM PATTERN:
{clinical_summary}

POSSIBLE CONDITIONS BEING INVESTIGATED:
{candidates_text}

TIME WITHOUT A DIAGNOSIS: {f"approximately {delay_years} years" if delay_years else "unclear"}
CONFIDENCE IN THESE FINDINGS: {confidence}

WHAT DOCTORS RECOMMEND NEXT:
{steps_text}

GENETIC TESTS THAT MAY HELP:
{chr(10).join(f"- {p}" for p in genetic_panels[:3]) or "Blood tests and specialist referrals"}

Write a patient summary with these sections:
1. **What we found** (2-3 sentences, what patterns ATLAS identified, in plain language)
2. **What this might mean** (explain the top 1-2 candidate conditions simply — what they are, not medical definitions)
3. **Why this took so long** (gentle explanation of diagnostic delays in rare diseases, validating their experience)
4. **What happens next** (next steps explained simply — what each test is and why it matters)
5. **A note of reassurance** (2-3 sentences — empathetic, honest, not falsely optimistic)

Use simple language. Avoid: HPO codes, OMIM numbers, medical abbreviations, Latin terms.
Write as if speaking directly to the patient ("you", "your symptoms").
Keep it under 400 words."""

    try:
        text = await _call_claude(prompt, max_tokens=1000)
    except Exception as exc:
        return {"error": f"Summary generation failed: {exc}"}

    return {
        "patient_summary": text,
        "top_candidate": top_candidates[0]["disease_name"] if top_candidates else "Under investigation",
        "confidence": confidence,
        "diagnostic_delay_years": delay_years,
        "word_count": len(text.split()),
    }
