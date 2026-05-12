import asyncio
import httpx
from mcp.server.fastmcp import Context

MONARCH_API = "https://api.monarchinitiative.org/v3/api"


async def _fetch_genes_for_disease(client: httpx.AsyncClient, disease_id: str, disease_name: str) -> dict:
    """Query Monarch Initiative for genes associated with a disease."""
    try:
        resp = await client.get(
            f"{MONARCH_API}/association",
            params={
                "subject": disease_id,
                "predicate": "biolink:has_phenotype",
                "object_category": "biolink:Gene",
                "limit": 10,
            },
            timeout=15.0,
        )
        # Try the gene associations endpoint
        gene_resp = await client.get(
            f"{MONARCH_API}/bioentity/disease/{disease_id}/genes",
            params={"limit": 10},
            timeout=15.0,
        )
        if gene_resp.status_code == 200:
            data = gene_resp.json()
            genes = []
            for item in data.get("associations", data.get("items", [])):
                gene = item.get("object", item.get("gene", {}))
                symbol = gene.get("symbol") or gene.get("label") or gene.get("id", "")
                if symbol and not symbol.startswith("MONDO") and not symbol.startswith("HP:"):
                    genes.append({
                        "symbol": symbol,
                        "id": gene.get("id", ""),
                        "name": gene.get("label", gene.get("name", "")),
                    })
            return {"disease_id": disease_id, "disease_name": disease_name, "genes": genes[:8]}
    except Exception:
        pass
    return {"disease_id": disease_id, "disease_name": disease_name, "genes": []}


async def _fetch_genes_ncbi(client: httpx.AsyncClient, disease_name: str) -> list[str]:
    """Fallback: search NCBI Gene database for genes associated with a disease name."""
    try:
        search_resp = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "gene",
                "term": f"{disease_name}[disease] AND Homo sapiens[organism]",
                "retmax": "8",
                "retmode": "json",
            },
            timeout=15.0,
        )
        search_resp.raise_for_status()
        gene_ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not gene_ids:
            return []

        summary_resp = await client.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "gene", "id": ",".join(gene_ids[:8]), "retmode": "json"},
            timeout=15.0,
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})
        genes = []
        for gid in gene_ids[:8]:
            g = result.get(gid, {})
            symbol = g.get("name", "")
            description = g.get("description", "")
            if symbol:
                genes.append(f"{symbol} ({description})" if description else symbol)
        return genes
    except Exception:
        return []


async def get_disease_genes(
    disease_matches: list,
    ctx: Context = None,
) -> dict:
    """Look up genes associated with top rare disease candidates via Monarch Initiative and NCBI.

    Returns the known causal/associated genes for each candidate disease — critical
    context for ordering targeted genetic panels and understanding disease mechanism.
    """

    if not disease_matches:
        return {"disease_genes": [], "error": "No disease matches provided."}

    top_matches = disease_matches[:3]

    async with httpx.AsyncClient() as client:
        results = []
        for match in top_matches:
            disease_id = match.get("disease_id", "")
            disease_name = match.get("disease_name", "")

            gene_data = {"disease_name": disease_name, "genes": [], "gene_symbols": []}

            # Try Monarch first if we have a MONDO ID
            if disease_id.startswith("MONDO:"):
                monarch_result = await _fetch_genes_for_disease(client, disease_id, disease_name)
                if monarch_result.get("genes"):
                    gene_data["genes"] = monarch_result["genes"]
                    gene_data["gene_symbols"] = [g["symbol"] for g in monarch_result["genes"]]

            # Fallback to NCBI if Monarch returned nothing
            if not gene_data["gene_symbols"]:
                ncbi_genes = await _fetch_genes_ncbi(client, disease_name)
                gene_data["gene_symbols"] = ncbi_genes
                gene_data["source"] = "ncbi"
            else:
                gene_data["source"] = "monarch"

            results.append(gene_data)

    return {
        "disease_genes": results,
        "summary": f"Found gene associations for {sum(1 for r in results if r['gene_symbols'])} of {len(results)} top candidates.",
    }
