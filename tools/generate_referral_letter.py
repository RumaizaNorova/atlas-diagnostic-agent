from mcp.server.fastmcp import Context
from tools.extract_phenotypes import _call_claude


async def generate_referral_letter(
    atlas_report: dict,
    patient_id: str = "",
    referring_provider: str = "The Referring Clinician",
    ctx: Context = None,
) -> dict:
    """Generate a ready-to-send genetics specialist referral letter based on the ATLAS diagnostic report.

    Produces a professionally written clinical referral letter addressed to a medical
    genetics specialist, summarising the patient's presentation, key findings, top
    candidate diagnoses, and requested workup — ready for the clinician to review
    and send without editing.
    """

    report = atlas_report.get("atlas_report", atlas_report)
    if not report or "executive_summary" not in report:
        return {"error": "Invalid ATLAS report provided. Run RunATLASAnalysis first."}

    top_candidates = report.get("top_candidates", [])
    red_flags = report.get("red_flags_missed", [])
    next_steps = report.get("immediate_next_steps", [])
    genetic_panels = report.get("genetic_panels_to_order", [])
    delay_years = report.get("estimated_diagnostic_delay_years")
    confidence = report.get("atlas_confidence", "Moderate")
    executive_summary = report.get("executive_summary", "")

    phenotype_profile = atlas_report.get("phenotype_profile", {})
    hpo_terms = phenotype_profile.get("hpo_terms", [])
    disease_matches = atlas_report.get("disease_matches", [])
    literature = atlas_report.get("supporting_literature", [])
    clinvar = atlas_report.get("clinvar_results", [])

    candidates_text = "\n".join(
        f"- {c['disease_name']} (match strength: {c.get('match_strength','?')}, OMIM: {c.get('omim','N/A')})\n"
        f"  Supporting: {'; '.join(c.get('supporting_evidence', [])[:2])}\n"
        f"  Causal genes: {', '.join(c.get('causal_genes', [])) or 'see genetic panel'}"
        for c in top_candidates[:3]
    ) or "See ATLAS analysis"

    hpo_text = ", ".join(
        f"{t.get('name', t.get('id', ''))} ({t.get('id', '')})"
        for t in hpo_terms[:8]
        if isinstance(t, dict)
    ) or "See attached phenotype profile"

    panels_text = "\n".join(f"- {p}" for p in genetic_panels) or "- Comprehensive rare disease gene panel\n- Whole exome sequencing if panel negative"

    clinvar_text = "\n".join(
        f"- {r['gene']} ({r['disease']}): {r['total_pathogenic']} pathogenic variants on record in ClinVar"
        for r in clinvar[:3]
        if r.get("total_pathogenic", 0) > 0
    ) or "ClinVar data not available"

    literature_text = "\n".join(
        f"- {a['title'][:80]}... ({a['journal']}, {a['year']}) PMID:{a['pmid']}"
        for a in literature[:2]
    ) or "See ATLAS report for literature references"

    prompt = f"""You are writing a formal clinical genetics referral letter on behalf of a referring physician.
Write in professional medical letter format. Be specific, concise, and clinically precise.

REFERRING PHYSICIAN: {referring_provider}
PATIENT ID: {patient_id or "See chart"}
DIAGNOSTIC DELAY: {f"Approximately {delay_years} years from first documented symptom" if delay_years else "Duration unclear from records"}
ATLAS CONFIDENCE: {confidence}

CLINICAL SUMMARY FROM ATLAS:
{executive_summary}

TOP RARE DISEASE CANDIDATES:
{candidates_text}

HPO PHENOTYPE TERMS IDENTIFIED:
{hpo_text}

PERSISTENT/WORSENING LAB FINDINGS:
{chr(10).join(f"- {f}" for f in red_flags[:3]) or "See attached report"}

SUGGESTED GENETIC WORKUP:
{panels_text}

KNOWN PATHOGENIC VARIANTS IN CANDIDATE GENES (ClinVar):
{clinvar_text}

SUPPORTING LITERATURE:
{literature_text}

Write a complete, professional referral letter with these sections:
1. Opening (date, addressee: "Dear Genetics Specialist,")
2. Reason for referral (1-2 sentences)
3. Clinical presentation and history (key findings, onset, diagnostic delay)
4. Investigations to date (what has been done, what is abnormal)
5. Differential diagnosis under consideration (top candidates with rationale)
6. Requested workup (specific genetic panels, reasoning)
7. Closing (urgency level, contact offer, signature block for {referring_provider})

Write the full letter as plain text, professional medical language, ready to send."""

    try:
        letter_text = await _call_claude(prompt, max_tokens=2000)
    except Exception as exc:
        return {"error": f"Letter generation failed: {exc}"}

    return {
        "referral_letter": letter_text,
        "addressed_to": "Medical Genetics Specialist",
        "from": referring_provider,
        "top_candidate": top_candidates[0]["disease_name"] if top_candidates else "Undiagnosed rare disease",
        "genetic_panels": genetic_panels,
        "character_count": len(letter_text),
    }
