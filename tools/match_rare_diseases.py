import asyncio
import httpx
from mcp.server.fastmcp import Context

MONARCH_API = "https://api.monarchinitiative.org/v3/api"

_INHERITANCE_MODE_LABELS = {
    "HP:0000006": "Autosomal dominant",
    "HP:0000007": "Autosomal recessive",
    "HP:0001417": "X-linked",
    "HP:0001419": "X-linked recessive",
    "HP:0001423": "X-linked dominant",
    "HP:0001450": "Y-linked",
    "HP:0001428": "Somatic mutation",
    "HP:0001427": "Mitochondrial",
    "HP:0003743": "Genetic anticipation",
    "HP:0003745": "Sporadic",
}


async def _fetch_disease_details(client: httpx.AsyncClient, disease_id: str) -> dict:
    """Fetch inheritance mode and prevalence for a disease from Monarch entity endpoint."""
    if not disease_id.startswith("MONDO:"):
        return {}
    try:
        resp = await client.get(
            f"{MONARCH_API}/entity/{disease_id}",
            timeout=8.0,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        details: dict = {}

        # Inheritance modes from HPO hierarchy associations
        inheritance_hpo = data.get("inheritance", [])
        if inheritance_hpo:
            details["inheritance_modes"] = [
                _INHERITANCE_MODE_LABELS.get(h.get("id", ""), h.get("label", ""))
                for h in inheritance_hpo
                if h.get("id") or h.get("label")
            ]

        # Prevalence class if provided
        prevalence = data.get("prevalence")
        if prevalence:
            details["prevalence"] = prevalence

        return details
    except Exception:
        return {}


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
            "inheritance_modes": [],
            "prevalence": None,
        })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)

    # Enrich top 5 matches with inheritance + prevalence in parallel
    async with httpx.AsyncClient(timeout=10.0) as client:
        detail_tasks = [
            _fetch_disease_details(client, m["disease_id"])
            for m in matches[:5]
        ]
        details_list = await asyncio.gather(*detail_tasks, return_exceptions=True)

    for match, details in zip(matches[:5], details_list):
        if isinstance(details, dict):
            if details.get("inheritance_modes"):
                match["inheritance_modes"] = details["inheritance_modes"]
            if details.get("prevalence"):
                match["prevalence"] = details["prevalence"]

    return {
        "matches": matches,
        "query_hpo_count": len(hpo_ids),
        "hpo_terms_used": hpo_ids,
    }
