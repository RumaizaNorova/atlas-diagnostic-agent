from mcp.server.fastmcp import FastMCP

from tools.extract_phenotypes import extract_phenotype_signals
from tools.generate_report import run_atlas_analysis
from tools.get_patient_history import get_patient_longitudinal_history
from tools.match_rare_diseases import match_rare_diseases
from tools.search_literature import search_pubmed_literature

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
    name="SearchPubMedLiterature",
    description=(
        "Search PubMed for recent clinical case reports and studies on a rare disease candidate. "
        "Returns titles, authors, journal, and PubMed links for supporting evidence."
    ),
)(search_pubmed_literature)

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
