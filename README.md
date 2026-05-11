# ATLAS — AI Diagnostic Agent for Rare Disease

> *The average rare disease patient sees 7 doctors over 4 years before receiving a correct diagnosis. The clues were always in the chart. No one connected them.*

ATLAS is an MCP server that reads a patient's complete longitudinal FHIR history, extracts phenotype signals, and cross-references them against the Monarch Initiative rare disease database — surfacing what years of fragmented care missed.

---

## The Problem

300 million people worldwide live with a rare disease. Most spend years — sometimes decades — being told their symptoms are stress, anxiety, or simply unexplained. The tragedy is that the diagnostic evidence is almost always present in the medical record. What's missing is a system that reads the entire story at once.

**ATLAS does exactly that.**

---

## How It Works

ATLAS is built as an MCP server that integrates natively with the Prompt Opinion platform via FHIR context propagation (SHARP extension spec).

```
Patient selected in Prompt Opinion
        │
        ▼
GetPatientLongitudinalHistory   ← reads Condition, Observation,
        │                          MedicationRequest, Procedure from FHIR
        ▼
ExtractPhenotypeSignals         ← maps clinical findings to HPO terms
        │                          using Gemini 2.0 Flash
        ▼
MatchRareDiseases               ← queries Monarch Initiative semsim API
        │                          with patient's HPO phenotype profile
        ▼
RunATLASAnalysis                ← synthesises structured diagnostic report:
                                   candidate diagnoses · missed red flags
                                   confirmatory tests · immediate next steps
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `RunATLASAnalysis` | **Primary tool.** Full end-to-end rare disease workup for a patient. |
| `GetPatientLongitudinalHistory` | Reads complete FHIR history across all resource types. |
| `ExtractPhenotypeSignals` | Converts clinical findings to HPO phenotype terms. |
| `MatchRareDiseases` | Queries Monarch Initiative by HPO profile, returns ranked candidates. |

---

## Sample Output

```json
{
  "atlas_report": {
    "executive_summary": "Patient presents with a 6-year history of fatigue, joint pain, recurrent rash, and persistently elevated ANA. The combination of multisystem involvement with positive autoimmune markers warrants urgent rare disease evaluation.",
    "estimated_diagnostic_delay_years": 6,
    "top_candidates": [
      {
        "disease_name": "Systemic Lupus Erythematosus",
        "omim": "OMIM:152700",
        "match_strength": "Strong",
        "supporting_evidence": [
          "ANA positive (2019, 2021, 2023) — documented three times, never actioned",
          "Recurrent malar rash noted in dermatology visit (2020)",
          "Arthralgia across multiple joints with no structural finding"
        ],
        "recommended_confirmatory_tests": ["Anti-dsDNA antibody", "Complement C3/C4", "Complete metabolic panel"]
      }
    ],
    "red_flags_missed": [
      "Three separate ANA-positive results across 4 years — each addressed in isolation",
      "Fatigue + joint pain + rash triad present from 2018, never evaluated together"
    ],
    "immediate_next_steps": [
      "Urgent rheumatology referral",
      "Anti-dsDNA, anti-Smith, anti-Ro/La antibody panel",
      "Urinalysis with microscopy to assess renal involvement",
      "Complement levels (C3, C4, CH50)"
    ],
    "atlas_confidence": "High",
    "atlas_confidence_rationale": "Strong phenotype-disease match supported by repeated objective lab findings in the record."
  }
}
```

---

## Running Locally

```bash
git clone https://github.com/RumaizaNorova/atlas-diagnostic-agent
cd atlas-diagnostic-agent

pip install -r requirements.txt

cp .env.example .env
# Add your GEMINI_API_KEY to .env

python main.py
# Server runs on http://localhost:8000/mcp
```

Expose via ngrok for testing with Prompt Opinion:
```bash
ngrok http 8000
# Copy the ngrok URL → paste into Prompt Opinion as MCP server URL + /mcp
```

---

## Deployment

Deployed on Railway. Set `GEMINI_API_KEY` as an environment variable in the Railway dashboard.

---

## Standards Compliance

- **MCP** — Streamable HTTP transport, `mcp` Python SDK
- **FHIR R4** — Reads Patient, Condition, Observation, MedicationRequest, Procedure
- **SHARP** — Declares `ai.promptopinion/fhir-context` extension in MCP capabilities
- **HPO** — Human Phenotype Ontology terms via Monarch Initiative API
- **MONDO** — Disease ontology returned by Monarch semsim search

---

## External APIs

- [Monarch Initiative](https://monarchinitiative.org/) — open, no key required
- [Google Gemini 2.0 Flash](https://ai.google.dev/) — phenotype extraction + report synthesis
