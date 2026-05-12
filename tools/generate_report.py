import json
import os
from datetime import date
from typing import Annotated

import httpx
from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_utilities import get_patient_id_if_context_exists
from tools.analyze_lab_trends import analyze_lab_trends
from tools.enrich_hpo_terms import enrich_hpo_terms
from tools.extract_phenotypes import _call_claude, extract_phenotype_signals
from tools.get_disease_genes import get_disease_genes
from tools.get_patient_history import get_patient_longitudinal_history
from tools.lookup_clinvar import lookup_clinvar_variants
from tools.match_rare_diseases import match_rare_diseases
from tools.search_literature import search_pubmed_literature


def _compute_diagnostic_delay(onset_dates: list[str]) -> int | None:
    for d in onset_dates:
        try:
            year = int(d[:4])
            if 1900 < year <= date.today().year:
                return date.today().year - year
        except (ValueError, IndexError):
            continue
    return None


async def _marshal_evidence(
    conditions_text: str,
    abnormal_text: str,
    family_text: str,
    lab_trends_summary: str,
    persistent_abnormalities: list,
    phenotype_summary: str,
    top_matches_text: str,
    gene_data: list,
    literature_text: str,
) -> str:
    """First reasoning pass: marshal evidence for and against each candidate before writing the report."""

    gene_text = "\n".join(
        f"- {g['disease_name']}: genes {', '.join(g['gene_symbols'][:5]) or 'unknown'} (via {g.get('source','?')})"
        for g in gene_data
    ) or "Gene data unavailable"

    persistent_text = "\n".join(
        f"- {p['test']}: abnormal in {p['abnormal_readings']}/{p['total_readings']} readings over {p['span_years']} years"
        for p in persistent_abnormalities[:5]
    ) or "None detected"

    prompt = f"""You are a rare disease specialist performing structured diagnostic reasoning.

PATIENT DATA SUMMARY:
Conditions: {conditions_text}
Abnormal findings: {abnormal_text}
Family history: {family_text}
Persistent lab abnormalities (multi-year): {persistent_text}
Lab trend summary: {lab_trends_summary}
Phenotype profile (HPO): {phenotype_summary}

TOP CANDIDATE DISEASES (Monarch similarity scores):
{top_matches_text}

Associated genes per candidate:
{gene_text}

Supporting literature:
{literature_text}

For each of the top 3 candidate diseases, reason through:
1. What findings SUPPORT this diagnosis?
2. What findings ARGUE AGAINST or are inconsistent?
3. What is the single most important test to confirm or rule out?

Return ONLY valid JSON:
{{
  "candidate_reasoning": [
    {{
      "disease": "disease name",
      "supporting": ["specific patient finding that fits", "..."],
      "against": ["finding that doesn't fit or is missing", "..."],
      "key_confirmatory_test": "single most important test"
    }}
  ],
  "most_likely_diagnosis": "disease name or null if unclear",
  "reasoning_confidence": "High | Moderate | Low",
  "critical_missing_workup": ["test or referral that was never done but should have been", "..."]
}}"""

    text = await _call_claude(prompt, max_tokens=1500)
    return text


async def run_atlas_analysis(
    patientId: Annotated[
        str | None,
        Field(description="Patient ID — optional if FHIR context is provided by the platform"),
    ] = None,
    ctx: Context = None,
) -> dict:
    """Run ATLAS full rare disease diagnostic analysis.

    Reads the patient's complete longitudinal FHIR history across 8 resource types,
    extracts and enriches HPO phenotype signals, matches against the Monarch Initiative
    rare disease database, analyzes multi-year lab trends, looks up disease-associated genes,
    fetches PubMed literature, performs structured two-pass AI reasoning, and returns
    a comprehensive diagnostic report with candidate diagnoses, missed red flags,
    gene panels to order, and immediate next steps.
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

    # Run enrichment steps in parallel
    try:
        import asyncio
        lab_trends_task = analyze_lab_trends(patient_history=history)
        hpo_enrichment_task = enrich_hpo_terms(hpo_terms=phenotypes.get("hpo_terms", []))
        gene_lookup_task = get_disease_genes(disease_matches=disease_matches.get("matches", []))
        literature_task = search_pubmed_literature(
            disease_name=disease_matches.get("matches", [{}])[0].get("disease_name", "") if disease_matches.get("matches") else "",
            hpo_terms=phenotypes.get("hpo_terms", []),
        )

        lab_trends, hpo_enriched, gene_data_result, literature = await asyncio.gather(
            lab_trends_task, hpo_enrichment_task, gene_lookup_task, literature_task,
            return_exceptions=True,
        )

        if isinstance(lab_trends, Exception):
            lab_trends = {"trends": [], "persistent_abnormalities": [], "summary": str(lab_trends)}
        if isinstance(hpo_enriched, Exception):
            hpo_enriched = {"enriched_terms": phenotypes.get("hpo_terms", [])}
        if isinstance(gene_data_result, Exception):
            gene_data_result = {"disease_genes": []}
        if isinstance(literature, Exception):
            literature = {"articles": []}

        # ClinVar lookup depends on gene results — run after gather
        clinvar_result = await lookup_clinvar_variants(
            disease_genes=gene_data_result.get("disease_genes", [])
        )
        if isinstance(clinvar_result, Exception):
            clinvar_result = {"clinvar_results": [], "total_pathogenic_variants_found": 0}

    except Exception as exc:
        lab_trends = {"trends": [], "persistent_abnormalities": [], "summary": ""}
        hpo_enriched = {"enriched_terms": phenotypes.get("hpo_terms", [])}
        gene_data_result = {"disease_genes": []}
        literature = {"articles": []}
        clinvar_result = {"clinvar_results": [], "total_pathogenic_variants_found": 0}

    conditions = history.get("conditions", [])
    abnormal_obs = [o for o in history.get("observations", []) if o.get("abnormal")]
    onset_dates = sorted([c.get("onset", "") for c in conditions if c.get("onset")])
    family_history = history.get("family_history", [])
    diagnostic_reports = history.get("diagnostic_reports", [])
    allergies = history.get("allergies", [])
    top_matches = disease_matches.get("matches", [])
    gene_data = gene_data_result.get("disease_genes", [])
    clinvar_data = clinvar_result.get("clinvar_results", [])
    persistent_abnormalities = lab_trends.get("persistent_abnormalities", [])

    diagnostic_delay_years = _compute_diagnostic_delay(onset_dates)
    earliest_onset = onset_dates[0] if onset_dates else "unknown"

    conditions_text = "\n".join(
        f"- {c['display']} (onset: {c.get('onset', 'unknown')})" for c in conditions
    ) or "None documented"

    abnormal_text = "\n".join(
        f"- {o['name']}: {o['value']} (flag: {o['interpretation']}, date: {o['date']})"
        for o in abnormal_obs
    )[:2000] or "None documented"

    family_text = "\n".join(
        f"- {f['relationship']}: {', '.join(f['conditions']) or 'unspecified'}"
        + (" (deceased)" if f.get("deceased") else "")
        for f in family_history
    ) or "None documented"

    top_matches_text = "\n".join(
        f"- {m['disease_name']} | score: {m['similarity_score']} | {', '.join(m['omim_refs']) or 'no OMIM'}"
        for m in top_matches[:5]
    ) or "No strong matches found"

    literature_text = "\n".join(
        f"- {a['title']} ({a['journal']}, {a['year']}) PMID:{a['pmid']}"
        for a in literature.get("articles", [])[:3]
    ) or "No recent literature retrieved"

    phenotype_summary = phenotypes.get("clinical_summary", "")

    clinvar_text = "\n".join(
        f"- {r['gene']} ({r['disease']}): {r['total_pathogenic']} pathogenic variants in ClinVar"
        for r in clinvar_data[:5]
        if r.get("total_pathogenic", 0) > 0
    ) or "No ClinVar variants found for candidate genes"

    # Pass 1: structured reasoning
    reasoning_json = {}
    try:
        reasoning_text = await _marshal_evidence(
            conditions_text=conditions_text,
            abnormal_text=abnormal_text,
            family_text=family_text,
            lab_trends_summary=lab_trends.get("summary", ""),
            persistent_abnormalities=persistent_abnormalities,
            phenotype_summary=phenotype_summary,
            top_matches_text=top_matches_text,
            gene_data=gene_data,
            literature_text=literature_text,
        )
        if reasoning_text.startswith("```"):
            parts = reasoning_text.split("```")
            reasoning_text = parts[1] if len(parts) > 1 else reasoning_text
            if reasoning_text.startswith("json"):
                reasoning_text = reasoning_text[4:].strip()
        reasoning_json = json.loads(reasoning_text)
    except Exception:
        reasoning_json = {}

    # Build gene text for final report
    gene_summary_text = "\n".join(
        f"- {g['disease_name']}: {', '.join(g['gene_symbols'][:5]) or 'no genes found'}"
        for g in gene_data
    ) or "Gene associations not retrieved"

    worsening = lab_trends.get("worsening_abnormal_trends", [])
    worsening_text = "\n".join(
        f"- {t['test']}: {t['first_value']} ({t['first_date']}) → {t['latest_value']} ({t['latest_date']}), trend: {t.get('trend','unknown')}"
        for t in worsening[:5]
    ) or "None detected"

    most_likely = reasoning_json.get("most_likely_diagnosis", "")
    reasoning_confidence = reasoning_json.get("reasoning_confidence", "")

    # Pass 2: final report synthesis
    prompt = f"""You are ATLAS, an AI diagnostic agent specialising in rare disease identification.
You have completed a full multi-source diagnostic workup. Now synthesise the final report.

PATIENT OVERVIEW
Earliest onset: {earliest_onset}
Time undiagnosed: {f"{diagnostic_delay_years} years" if diagnostic_delay_years else "unknown"}

Conditions: {conditions_text}
Abnormal findings: {abnormal_text}
Family history: {family_text}

MULTI-YEAR LAB TRENDS (worsening):
{worsening_text}

Persistent abnormalities (>50% readings abnormal over 1+ years):
{chr(10).join(f"- {p['test']}: {p['abnormal_readings']}/{p['total_readings']} readings over {p['span_years']}y" for p in persistent_abnormalities[:5]) or "None"}

PHENOTYPE PROFILE (HPO): {phenotype_summary}

TOP DISEASE MATCHES (Monarch Initiative):
{top_matches_text}

ASSOCIATED GENES PER CANDIDATE:
{gene_summary_text}

KNOWN PATHOGENIC CLINVAR VARIANTS IN CANDIDATE GENES:
{clinvar_text}

SUPPORTING LITERATURE:
{literature_text}

STRUCTURED REASONING (pass 1):
Most likely: {most_likely or "unclear"}
Confidence: {reasoning_confidence or "unknown"}
{json.dumps(reasoning_json.get("candidate_reasoning", []), indent=2) if reasoning_json.get("candidate_reasoning") else ""}

Generate the final ATLAS diagnostic report. Return ONLY valid JSON:
{{
  "executive_summary": "3-4 sentences covering the diagnostic picture, why rare disease workup is warranted, and the leading candidate",
  "estimated_diagnostic_delay_years": {diagnostic_delay_years if diagnostic_delay_years is not None else "null"},
  "top_candidates": [
    {{
      "disease_name": "...",
      "omim": "OMIM:XXXXXX or null",
      "match_strength": "Strong | Moderate | Weak",
      "supporting_evidence": ["specific finding from this patient", "..."],
      "against_evidence": ["finding that doesn't fit", "..."],
      "causal_genes": ["GENE1", "GENE2"],
      "recommended_confirmatory_tests": ["most important test", "..."]
    }}
  ],
  "red_flags_missed": ["specific finding + why it should have triggered rare disease workup", "..."],
  "persistent_lab_abnormalities": ["test name + duration of abnormality", "..."],
  "immediate_next_steps": ["concrete clinical action with rationale", "..."],
  "genetic_panels_to_order": ["specific panel name", "..."],
  "atlas_confidence": "High | Moderate | Low",
  "atlas_confidence_rationale": "one sentence"
}}

Top candidates: up to 3. Red flags: 3-5. Next steps: 4-5. Genetic panels: 1-3."""

    try:
        text = await _call_claude(prompt, max_tokens=2500)
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
            "hpo_terms": hpo_enriched.get("enriched_terms", phenotypes.get("hpo_terms", [])),
            "clinical_summary": phenotype_summary,
        },
        "disease_matches": top_matches[:5],
        "disease_genes": gene_data,
        "clinvar_variants": clinvar_data,
        "lab_analysis": {
            "persistent_abnormalities": persistent_abnormalities,
            "worsening_trends": worsening,
            "summary": lab_trends.get("summary", ""),
        },
        "supporting_literature": literature.get("articles", [])[:3],
        "reasoning_pass_1": reasoning_json,
        "data_points_analyzed": {
            "conditions": len(conditions),
            "total_observations": len(history.get("observations", [])),
            "abnormal_observations": len(abnormal_obs),
            "medications": len(history.get("medications", [])),
            "procedures": len(history.get("procedures", [])),
            "family_history_entries": len(family_history),
            "diagnostic_reports": len(diagnostic_reports),
            "allergies": len(allergies),
            "hpo_terms_extracted": len(phenotypes.get("hpo_terms", [])),
            "lab_series_analyzed": len(lab_trends.get("trends", [])),
            "persistent_abnormalities": len(persistent_abnormalities),
            "pubmed_articles": len(literature.get("articles", [])),
            "clinvar_variants_found": clinvar_result.get("total_pathogenic_variants_found", 0),
        },
    }
