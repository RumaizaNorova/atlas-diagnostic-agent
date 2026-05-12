# ATLAS — Rare Disease Diagnostic Agent

> *The average rare disease patient sees 7 doctors over 4 years before receiving a correct diagnosis. The clues were always in the chart. No one connected them.*

ATLAS is a production-ready MCP server that performs end-to-end rare disease diagnostic analysis. It reads a patient's complete longitudinal FHIR history across 8 resource types, extracts HPO phenotype signals, cross-references 6 biomedical databases, performs two-pass AI reasoning, and returns a structured diagnostic report — then writes findings back to the EHR as a FHIR DiagnosticReport.

**Live server:** `https://atlas-diagnostic-agent.onrender.com`

---

## The Problem

300 million people worldwide live with a rare disease. Most spend years — sometimes decades — being told their symptoms are stress, anxiety, or simply unexplained. The tragedy is that the diagnostic evidence is almost always present in the medical record. What's missing is a system that reads the entire story at once.

**ATLAS does exactly that.**

---

## Architecture

```
FHIR EHR (Epic)
      │
      ▼
GetPatientLongitudinalHistory   ← 8 FHIR resource types
      │
      ├── ExtractPhenotypeSignals  ← Claude AI → HPO terms
      │         └── EnrichHPOTerms  ← hpo.jax.org official ontology
      │
      ├── MatchRareDiseases  ← Monarch Initiative phenotype similarity
      │         └── GetDiseaseGenes  ← Monarch + NCBI gene associations
      │                   └── LookupClinVarVariants  ← NCBI ClinVar pathogenic variants
      │
      ├── AnalyzeLabTrends  ← worsening/persistent patterns (pure computation)
      │
      └── SearchPubMedLiterature  ← NIH PubMed case reports
                │
                ▼
         RunATLASAnalysis  ← two-pass AI reasoning → structured report
                │
                ├── ComputeUrgencyScore      ← triage 1-5 score
                ├── GenerateReferralLetter   ← ready-to-send clinical letter
                ├── GeneratePatientSummary   ← plain language for patient
                └── WriteATLASReportToFHIR  ← FHIR R4 DiagnosticReport write-back
```

---

## MCP Tools (13 total)

| Tool | Description | APIs |
|------|-------------|------|
| `GetPatientLongitudinalHistory` | Reads Condition, Observation, MedicationRequest, Procedure, FamilyMemberHistory, DiagnosticReport, AllergyIntolerance, Patient | FHIR R4 |
| `ExtractPhenotypeSignals` | Maps clinical findings to HPO phenotype terms | Anthropic Claude |
| `EnrichHPOTerms` | Official definitions and synonyms from HPO ontology | hpo.jax.org |
| `MatchRareDiseases` | Phenotype similarity scoring against rare disease database | Monarch Initiative |
| `GetDiseaseGenes` | Causal gene lookup for candidate diseases | Monarch Initiative, NCBI Gene |
| `LookupClinVarVariants` | Known pathogenic variants in candidate genes | NCBI ClinVar |
| `AnalyzeLabTrends` | Detects worsening/persistent multi-year lab abnormalities | — (pure computation) |
| `SearchPubMedLiterature` | Recent case reports for top candidate disease | NIH PubMed |
| `RunATLASAnalysis` | Full pipeline with two-pass AI reasoning | All of the above |
| `ComputeUrgencyScore` | Triage score 1-5 (Routine → Emergent) with rationale | — (pure computation) |
| `GenerateReferralLetter` | Ready-to-send clinical genetics referral letter | Anthropic Claude |
| `GeneratePatientSummary` | Plain-language patient-facing summary | Anthropic Claude |
| `WriteATLASReportToFHIR` | Writes findings back to EHR as FHIR R4 DiagnosticReport | FHIR R4 |

---

## Sample Output

```json
{
  "atlas_report": {
    "executive_summary": "Patient presents with a 7-year history of fatigue, joint hypermobility, and recurrent subluxations. The combination of multisystem connective tissue involvement warrants urgent rare disease evaluation.",
    "estimated_diagnostic_delay_years": 7,
    "top_candidates": [
      {
        "disease_name": "Ehlers-Danlos Syndrome, Hypermobile Type",
        "omim": "OMIM:130020",
        "match_strength": "Strong",
        "supporting_evidence": ["Joint hypermobility documented across 4 visits", "Chronic pain unresolved by standard treatment"],
        "against_evidence": ["No skin hyperextensibility noted"],
        "causal_genes": ["COL5A1", "COL5A2"],
        "recommended_confirmatory_tests": ["Beighton score assessment", "Genetics referral", "Echocardiogram"]
      }
    ],
    "red_flags_missed": ["Recurrent subluxations across 3 years never evaluated for connective tissue disorder"],
    "genetic_panels_to_order": ["Connective tissue disorder panel (COL5A1, COL5A2, COL3A1, FBN1)"],
    "atlas_confidence": "High"
  },
  "data_points_analyzed": {
    "conditions": 12, "total_observations": 187, "abnormal_observations": 23,
    "hpo_terms_extracted": 14, "lab_series_analyzed": 31,
    "persistent_abnormalities": 4, "clinvar_variants_found": 47, "pubmed_articles": 3
  }
}
```

---

## Setup

```bash
git clone https://github.com/RumaizaNorova/atlas-diagnostic-agent
cd atlas-diagnostic-agent
pip install -r requirements.txt
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env
uvicorn main:app --reload
# Server runs on http://localhost:8000
```

Health check: `GET /health`

---

## Deployment

Deployed on Render. Set `ANTHROPIC_API_KEY` as an environment variable in the Render dashboard.

---

## Standards

- **MCP** — Streamable HTTP transport, FastMCP Python SDK, stateless
- **FHIR R4** — Reads and writes 8+ resource types via Epic
- **SHARP** — Declares `ai.promptopinion/fhir-context` extension in MCP capabilities
- **HPO** — Human Phenotype Ontology terms, validated against hpo.jax.org
- **MONDO** — Disease ontology via Monarch Initiative
- **LOINC** — DiagnosticReport coded with LOINC 81247-9

---

## External APIs (7 total, all free)

- [Monarch Initiative](https://monarchinitiative.org/) — phenotype similarity, gene associations
- [NCBI ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/) — pathogenic variant database
- [NCBI PubMed](https://pubmed.ncbi.nlm.nih.gov/) — clinical literature
- [NCBI Gene](https://www.ncbi.nlm.nih.gov/gene/) — gene-disease associations
- [HPO Ontology API](https://hpo.jax.org/) — term definitions and synonyms
- [Anthropic Claude](https://anthropic.com/) — phenotype extraction and report synthesis
- [Epic FHIR R4](https://fhir.epic.com/) — patient health records

Built for the **Agents Assemble — The Healthcare AI Endgame** hackathon on Prompt Opinion.
