from contextlib import asynccontextmanager
import os
import time

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mcp_instance import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="ATLAS — Rare Disease Diagnostic Agent",
    description=(
        "End-to-end rare disease diagnostic analysis. "
        "Reads FHIR patient history, extracts HPO phenotypes, cross-references 6 biomedical databases, "
        "performs two-pass AI reasoning, and returns a structured diagnostic report."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health():
    return JSONResponse({"status": "ok", "service": "ATLAS Rare Disease Diagnostic Agent", "version": "1.0.0"})


# ---------------------------------------------------------------------------
# Demo endpoint — full ATLAS pipeline on a synthetic patient, no auth needed
# ---------------------------------------------------------------------------

@app.get(
    "/demo",
    tags=["Demo"],
    summary="Run full ATLAS analysis on synthetic rare disease patient",
    description=(
        "Runs the complete ATLAS pipeline on a pre-loaded synthetic patient: "
        "31-year-old female with a 9-year diagnostic odyssey (hEDS + POTS misdiagnosed as fibromyalgia). "
        "No authentication or FHIR context required. "
        "Demonstrates all 8 data sources, HPO extraction, Monarch matching, lab trend analysis, "
        "ClinVar lookup, PubMed literature, two-pass AI reasoning, and urgency scoring."
    ),
)
async def run_demo():
    from demo_patient import DEMO_PATIENT_HISTORY
    from tools.generate_report import _run_atlas_pipeline
    from tools.compute_urgency_score import compute_urgency_score

    start = time.time()
    result = await _run_atlas_pipeline(DEMO_PATIENT_HISTORY)
    if "error" in result:
        return JSONResponse(result, status_code=500)

    urgency = await compute_urgency_score(atlas_result=result)
    result["urgency"] = urgency
    result["demo_meta"] = {
        "patient": "Synthetic — 31-year-old female, 9-year diagnostic odyssey",
        "clinical_case": "hEDS + POTS, misdiagnosed as fibromyalgia/anxiety/IBS",
        "pipeline_seconds": round(time.time() - start, 1),
        "note": "All data is synthetic. No real patient information.",
    }
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Free-text symptom analysis — no FHIR required
# ---------------------------------------------------------------------------

class SymptomRequest(BaseModel):
    symptoms: str
    age: int | None = None
    sex: str | None = None
    duration_years: float | None = None
    family_history: list[str] | None = None


@app.post(
    "/api/analyze",
    tags=["Analysis"],
    summary="Analyze free-text symptoms for rare disease candidates",
    description=(
        "Accepts a plain-text symptom description and optional demographic context. "
        "Extracts HPO phenotype terms via Claude, matches against the Monarch Initiative rare disease database, "
        "enriches with gene associations and ClinVar variants, and returns ranked candidates. "
        "No FHIR or EHR access required — designed for direct clinical or patient use."
    ),
)
async def analyze_symptoms(body: SymptomRequest):
    from tools.extract_phenotypes import extract_phenotype_signals
    from tools.match_rare_diseases import match_rare_diseases
    from tools.get_disease_genes import get_disease_genes
    from tools.lookup_clinvar import lookup_clinvar_variants
    from tools.enrich_hpo_terms import enrich_hpo_terms
    import asyncio

    if not body.symptoms or len(body.symptoms.strip()) < 10:
        return JSONResponse({"error": "Please provide a symptom description (minimum 10 characters)."}, status_code=400)

    context_notes = []
    if body.age:
        context_notes.append(f"Age: {body.age}")
    if body.sex:
        context_notes.append(f"Sex: {body.sex}")
    if body.duration_years:
        context_notes.append(f"Duration: {body.duration_years} years")
    if body.family_history:
        context_notes.append(f"Family history: {', '.join(body.family_history)}")

    history = {
        "patient_id": "api-symptom-query",
        "conditions": [
            {
                "display": body.symptoms,
                "onset": "",
                "status": "active",
                "code": "",
            }
        ],
        "observations": [],
        "medications": [],
        "procedures": [],
        "family_history": [
            {"relationship": "Family member", "conditions": [cond], "deceased": False}
            for cond in (body.family_history or [])
        ],
        "diagnostic_reports": [],
        "allergies": [],
        "_context_notes": context_notes,
    }

    start = time.time()

    try:
        phenotypes = await extract_phenotype_signals(patient_history=history)
        hpo_terms = phenotypes.get("hpo_terms", [])

        disease_matches, hpo_enriched = await asyncio.gather(
            match_rare_diseases(hpo_terms=hpo_terms),
            enrich_hpo_terms(hpo_terms=hpo_terms),
            return_exceptions=True,
        )
        if isinstance(disease_matches, Exception):
            disease_matches = {"matches": []}
        if isinstance(hpo_enriched, Exception):
            hpo_enriched = {"enriched_terms": hpo_terms}

        top_matches = disease_matches.get("matches", [])[:5]
        gene_data_result = await get_disease_genes(disease_matches=top_matches)
        clinvar_result = await lookup_clinvar_variants(
            disease_genes=gene_data_result.get("disease_genes", [])
        )

    except Exception as exc:
        return JSONResponse({"error": f"Analysis failed: {type(exc).__name__}: {exc}"}, status_code=500)

    return JSONResponse({
        "query": {
            "symptoms": body.symptoms,
            "age": body.age,
            "sex": body.sex,
            "duration_years": body.duration_years,
            "family_history": body.family_history,
        },
        "phenotype_extraction": {
            "hpo_terms": hpo_enriched.get("enriched_terms", hpo_terms),
            "clinical_summary": phenotypes.get("clinical_summary", ""),
            "hpo_term_count": len(hpo_terms),
        },
        "top_candidates": top_matches,
        "disease_genes": gene_data_result.get("disease_genes", []),
        "clinvar_summary": {
            "genes_searched": len(gene_data_result.get("disease_genes", [])),
            "total_pathogenic_variants": clinvar_result.get("total_pathogenic_variants_found", 0),
            "results": clinvar_result.get("clinvar_results", [])[:5],
        },
        "analysis_seconds": round(time.time() - start, 1),
        "note": (
            "This analysis is for research and decision-support purposes only. "
            "Clinical diagnosis requires a qualified physician."
        ),
    })


# ---------------------------------------------------------------------------
# Disease search — query Monarch Initiative directly
# ---------------------------------------------------------------------------

@app.get(
    "/api/diseases",
    tags=["Reference"],
    summary="Search rare disease database",
    description="Search the Monarch Initiative rare disease database by name or HPO term. Returns OMIM codes, phenotype descriptions, and associated genes.",
)
async def search_diseases(
    q: str = Query(..., description="Disease name or keyword (e.g. 'ehlers-danlos', 'POTS', 'marfan')"),
    limit: int = Query(10, ge=1, le=50, description="Number of results to return"),
):
    if not q or len(q.strip()) < 2:
        return JSONResponse({"error": "Query must be at least 2 characters."}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.monarchinitiative.org/v3/search",
                params={"q": q, "category": "biolink:Disease", "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return JSONResponse({"error": f"Monarch search failed: {exc}"}, status_code=502)

    items = data.get("items", [])
    results = []
    for item in items:
        results.append({
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "category": item.get("category", ""),
            "omim": next(
                (x for x in item.get("xref", []) if x.startswith("OMIM:")),
                None,
            ),
            "mondo": item.get("id") if str(item.get("id", "")).startswith("MONDO:") else None,
            "synonyms": item.get("synonym", [])[:3],
        })

    return JSONResponse({
        "query": q,
        "total": data.get("total", len(results)),
        "results": results,
    })


# ---------------------------------------------------------------------------
# HPO term lookup
# ---------------------------------------------------------------------------

@app.get(
    "/api/phenotype/{hpo_id}",
    tags=["Reference"],
    summary="Look up an HPO phenotype term",
    description="Fetch official definition, synonyms, and clinical context for an HPO term (e.g. HP:0001382).",
)
async def get_phenotype(hpo_id: str):
    hpo_id = hpo_id.replace("_", ":").upper()
    if not hpo_id.startswith("HP:"):
        return JSONResponse({"error": "HPO ID must start with HP: (e.g. HP:0001382)"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://hpo.jax.org/api/hpo/term/{hpo_id}",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return JSONResponse({"error": f"HPO lookup failed: {exc}"}, status_code=502)

    term = data.get("details", data)
    return JSONResponse({
        "id": hpo_id,
        "name": term.get("name", ""),
        "definition": term.get("definition", ""),
        "synonyms": term.get("synonyms", []),
        "comment": term.get("comment", ""),
        "is_a": term.get("isA", []),
    })


app.mount("/", mcp.streamable_http_app())

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
