from mcp.server.fastmcp import FastMCP

from tools.analyze_lab_trends import analyze_lab_trends
from tools.compute_urgency_score import compute_urgency_score
from tools.enrich_hpo_terms import enrich_hpo_terms
from tools.extract_phenotypes import extract_phenotype_signals
from tools.generate_patient_summary import generate_patient_summary
from tools.generate_referral_letter import generate_referral_letter
from tools.generate_report import run_atlas_analysis
from tools.get_disease_genes import get_disease_genes
from tools.get_patient_history import get_patient_longitudinal_history
from tools.lookup_clinvar import lookup_clinvar_variants
from tools.match_rare_diseases import match_rare_diseases
from tools.search_literature import search_pubmed_literature
from tools.write_fhir_report import write_atlas_report_to_fhir

mcp = FastMCP("ATLAS Diagnostic Agent", stateless_http=True, host="0.0.0.0")

# Declare Prompt Opinion FHIR context extension so the platform passes patient
# FHIR credentials to every tool call automatically.
_original_get_capabilities = mcp._mcp_server.get_capabilities


def _patched_get_capabilities(notification_options, experimental_capabilities):
    caps = _original_get_capabilities(notification_options, experimental_capabilities)
    caps.model_extra["extensions"] = {
        "ai.promptopinion/fhir-context": {
            "scopes": [
                {"name": "patient/Patient.rs", "required": True},
                {"name": "patient/Condition.rs", "required": True},
                {"name": "patient/Observation.rs", "required": True},
                {"name": "patient/MedicationRequest.rs"},
                {"name": "patient/Procedure.rs"},
                {"name": "patient/DiagnosticReport.rs"},
                {"name": "patient/FamilyMemberHistory.rs"},
                {"name": "patient/AllergyIntolerance.rs"},
            ]
        }
    }
    return caps


mcp._mcp_server.get_capabilities = _patched_get_capabilities

mcp.tool(
    name="GetPatientLongitudinalHistory",
    description=(
        "Reads the patient's complete FHIR medical history across all visits: "
        "conditions, lab results, medications, and procedures over time."
    ),
)(get_patient_longitudinal_history)

mcp.tool(
    name="ExtractPhenotypeSignals",
    description=(
        "Converts raw clinical findings from a patient history dict into structured "
        "Human Phenotype Ontology (HPO) terms for rare disease matching."
    ),
)(extract_phenotype_signals)

mcp.tool(
    name="MatchRareDiseases",
    description=(
        "Queries the Monarch Initiative rare disease database using HPO phenotype terms "
        "and returns ranked candidate diseases with similarity scores."
    ),
)(match_rare_diseases)

mcp.tool(
    name="AnalyzeLabTrends",
    description=(
        "Detects progressive and persistent lab abnormalities over time in a patient's "
        "FHIR observation history. Groups by test, sorts by date, and identifies worsening "
        "trends and multi-year persistent abnormalities that single readings miss."
    ),
)(analyze_lab_trends)

mcp.tool(
    name="EnrichHPOTerms",
    description=(
        "Enriches extracted HPO phenotype terms with official definitions, synonyms, "
        "and clinical context from the Human Phenotype Ontology at hpo.jax.org."
    ),
)(enrich_hpo_terms)

mcp.tool(
    name="GetDiseaseGenes",
    description=(
        "Looks up causal and associated genes for top rare disease candidates via "
        "Monarch Initiative and NCBI. Returns gene symbols to guide targeted genetic panel ordering."
    ),
)(get_disease_genes)

mcp.tool(
    name="LookupClinVarVariants",
    description=(
        "Queries the NCBI ClinVar database for known pathogenic and likely-pathogenic "
        "variants in genes associated with top rare disease candidates. Returns variant "
        "IDs, clinical significance, and ClinVar URLs to guide genetic panel ordering."
    ),
)(lookup_clinvar_variants)

mcp.tool(
    name="GenerateReferralLetter",
    description=(
        "Generates a complete, ready-to-send clinical genetics referral letter based on "
        "the ATLAS diagnostic report. Includes patient presentation, key findings, top "
        "candidate diagnoses, requested genetic workup, and ClinVar variant context. "
        "Run RunATLASAnalysis first, then pass the result to this tool."
    ),
)(generate_referral_letter)

mcp.tool(
    name="SearchPubMedLiterature",
    description=(
        "Search PubMed for recent clinical case reports and studies on a rare disease candidate. "
        "Returns titles, authors, journal, and PubMed links for supporting evidence."
    ),
)(search_pubmed_literature)

mcp.tool(
    name="ComputeUrgencyScore",
    description=(
        "Computes a 1-5 urgency/triage score for rare disease workup based on diagnostic delay, "
        "disease severity of top candidates, multi-year lab trends, and missed red flags. "
        "Returns urgency level (Routine/Soon/Elevated/Urgent/Emergent) with rationale "
        "to help clinicians prioritise rare disease referrals. Run RunATLASAnalysis first."
    ),
)(compute_urgency_score)

mcp.tool(
    name="GeneratePatientSummary",
    description=(
        "Generates a plain-language summary of ATLAS findings written for the patient, not the clinician. "
        "No medical jargon, no HPO codes — clear, compassionate language explaining what was found, "
        "what it might mean, and what happens next. Run RunATLASAnalysis first."
    ),
)(generate_patient_summary)

mcp.tool(
    name="WriteATLASReportToFHIR",
    description=(
        "Writes the ATLAS diagnostic report back to the patient's EHR as a structured "
        "FHIR R4 DiagnosticReport resource. Closes the loop: ATLAS reads from FHIR, "
        "reasons over the data, and writes findings back so every clinician sees them. "
        "Encodes HPO terms, candidate diagnoses (with OMIM codes), confidence level, "
        "and diagnostic delay as structured FHIR extensions. "
        "Run RunATLASAnalysis first, then pass the result to this tool."
    ),
)(write_atlas_report_to_fhir)

mcp.tool(
    name="RunATLASAnalysis",
    description=(
        "ATLAS full rare disease diagnostic analysis. Reads the patient's complete "
        "longitudinal FHIR history (conditions, labs, medications, procedures, family history, "
        "diagnostic reports, allergies), extracts HPO phenotype signals, cross-references against "
        "the Monarch Initiative rare disease database, fetches supporting PubMed literature, "
        "and returns a structured report with candidate diagnoses, missed red flags, and "
        "immediate next steps. Use this as the primary entry point for a full diagnostic workup."
    ),
)(run_atlas_analysis)
