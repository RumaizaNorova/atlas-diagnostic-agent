import httpx
from mcp.server.fastmcp import Context

MONARCH_API = "https://api.monarchinitiative.org/v3/api"


async def match_rare_diseases(
    hpo_terms: list,
    ctx: Context = None,
) -> dict:
    """Query the Monarch Initiative database to find rare diseases matching HPO phenotype terms."""

    hpo_ids = [t["id"] for t in hpo_terms if isinstance(t, dict) and t.get("id", "").startswith("HP:")]

    if not hpo_ids:
        return {"matches": [], "error": "No valid HPO terms provided."}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MONARCH_API}/semsim/search",
            json={
                "termset": hpo_ids[:20],
                "group": "Human Diseases",
                "metric": "ancestor_information_content",
                "limit": 10,
            },
        )
        response.raise_for_status()
        data = response.json()

    matches = []
    for item in data:
        subject = item.get("subject", {})
        xrefs = subject.get("xref", []) or []
        matches.append({
            "disease_id": subject.get("id", ""),
            "disease_name": subject.get("name", "Unknown"),
            "description": subject.get("description") or "",
            "similarity_score": round(item.get("score", 0), 3),
            "matched_phenotypes": (subject.get("has_phenotype_label") or [])[:5],
            "omim_refs": [x for x in xrefs if x.startswith("OMIM:")],
            "orpha_refs": [x for x in xrefs if x.startswith("ORPHA:")],
        })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)

    return {
        "matches": matches,
        "query_hpo_count": len(hpo_ids),
        "hpo_terms_used": hpo_ids,
    }
