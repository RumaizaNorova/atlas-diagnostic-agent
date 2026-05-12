import asyncio
import httpx
from mcp.server.fastmcp import Context

NCBI_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


async def _fetch_variants_for_gene(client: httpx.AsyncClient, gene_symbol: str, disease_name: str) -> dict:
    """Query ClinVar for pathogenic variants in a specific gene associated with a disease."""
    try:
        # Search ClinVar for pathogenic/likely pathogenic variants in this gene
        search_resp = await client.get(
            NCBI_SEARCH,
            params={
                "db": "clinvar",
                "term": f"{gene_symbol}[gene] AND ({disease_name}[disease] OR clinsig_pathogenic[filter] OR clinsig_likely_pathogenic[filter])",
                "retmax": "10",
                "retmode": "json",
            },
            timeout=15.0,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

        if not ids:
            # Fallback: just pathogenic variants for this gene
            search_resp2 = await client.get(
                NCBI_SEARCH,
                params={
                    "db": "clinvar",
                    "term": f"{gene_symbol}[gene] AND (pathogenic[clinsig] OR likely pathogenic[clinsig])",
                    "retmax": "5",
                    "retmode": "json",
                },
                timeout=15.0,
            )
            search_resp2.raise_for_status()
            ids = search_resp2.json().get("esearchresult", {}).get("idlist", [])

        if not ids:
            return {"gene": gene_symbol, "pathogenic_variants": [], "total_pathogenic": 0}

        # Fetch summaries
        summary_resp = await client.get(
            NCBI_SUMMARY,
            params={"db": "clinvar", "id": ",".join(ids[:5]), "retmode": "json"},
            timeout=15.0,
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

        variants = []
        for vid in ids[:5]:
            v = result.get(str(vid), {})
            if not v:
                continue
            title = v.get("title", "")
            germline = v.get("germline_classification", {})
            clinical_sig = germline.get("description", v.get("clinical_significance", {}).get("description", "unknown"))
            variants.append({
                "variant_id": vid,
                "title": title,
                "clinical_significance": clinical_sig,
                "last_evaluated": germline.get("last_evaluated", ""),
                "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{vid}/",
            })

        return {
            "gene": gene_symbol,
            "pathogenic_variants": variants,
            "total_pathogenic": len(ids),
        }

    except Exception as exc:
        return {"gene": gene_symbol, "pathogenic_variants": [], "error": str(exc)}


async def lookup_clinvar_variants(
    disease_genes: list,
    ctx: Context = None,
) -> dict:
    """Look up known pathogenic ClinVar variants for genes associated with top rare disease candidates.

    Queries the NCBI ClinVar database (the authoritative source for clinically significant
    genetic variants) to find pathogenic and likely pathogenic variants in the causal genes
    identified for each candidate disease. This tells clinicians exactly which genetic
    panel to order and what variants to look for.
    """

    if not disease_genes:
        return {"clinvar_results": [], "error": "No disease genes provided."}

    async with httpx.AsyncClient() as client:
        tasks = []
        labels = []

        for disease_entry in disease_genes[:3]:
            disease_name = disease_entry.get("disease_name", "")
            gene_symbols = disease_entry.get("gene_symbols", [])[:3]
            for gene in gene_symbols:
                if gene and len(gene) < 20:  # skip malformed entries
                    tasks.append(_fetch_variants_for_gene(client, gene, disease_name))
                    labels.append((disease_name, gene))

        if not tasks:
            return {"clinvar_results": [], "note": "No valid gene symbols to query."}

        results = await asyncio.gather(*tasks, return_exceptions=True)

    clinvar_results = []
    for (disease_name, gene), result in zip(labels, results):
        if isinstance(result, Exception):
            continue
        result["disease"] = disease_name
        if result.get("total_pathogenic", 0) > 0 or result.get("pathogenic_variants"):
            clinvar_results.append(result)

    # Sort by number of pathogenic variants found
    clinvar_results.sort(key=lambda x: x.get("total_pathogenic", 0), reverse=True)

    total_variants = sum(r.get("total_pathogenic", 0) for r in clinvar_results)

    return {
        "clinvar_results": clinvar_results,
        "total_pathogenic_variants_found": total_variants,
        "genes_queried": len(tasks),
        "summary": (
            f"Found {total_variants} pathogenic/likely-pathogenic ClinVar variants "
            f"across {len(clinvar_results)} genes for top candidate diseases."
        ),
    }
