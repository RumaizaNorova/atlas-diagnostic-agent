import asyncio
import httpx
from mcp.server.fastmcp import Context

HPO_API = "https://hpo.jax.org/api/hpo/term"


async def _fetch_term(client: httpx.AsyncClient, hp_id: str) -> dict | None:
    try:
        resp = await client.get(f"{HPO_API}/{hp_id}", timeout=10.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        term = data.get("details", data)
        return {
            "id": hp_id,
            "name": term.get("name", ""),
            "definition": term.get("definition", ""),
            "synonyms": [s.get("label", "") for s in term.get("synonyms", [])][:3],
            "comment": term.get("comment", ""),
        }
    except Exception:
        return None


async def enrich_hpo_terms(
    hpo_terms: list,
    ctx: Context = None,
) -> dict:
    """Enrich extracted HPO terms with official definitions, synonyms, and clinical context from the Human Phenotype Ontology.

    Queries hpo.jax.org (the authoritative HPO source) to add definitions
    and synonyms that strengthen the phenotype profile for rare disease matching.
    """

    valid_terms = [t for t in hpo_terms if isinstance(t, dict) and t.get("id", "").startswith("HP:")]
    if not valid_terms:
        return {"enriched_terms": [], "error": "No valid HPO terms to enrich."}

    async with httpx.AsyncClient() as client:
        tasks = [_fetch_term(client, t["id"]) for t in valid_terms[:15]]
        results = await asyncio.gather(*tasks)

    enriched = []
    for original, fetched in zip(valid_terms[:15], results):
        merged = {**original}
        if fetched:
            merged["official_name"] = fetched["name"]
            merged["definition"] = fetched["definition"]
            merged["synonyms"] = fetched["synonyms"]
        enriched.append(merged)

    return {
        "enriched_terms": enriched,
        "total_enriched": len([e for e in enriched if e.get("definition")]),
    }
