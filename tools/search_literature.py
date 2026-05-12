import httpx
from mcp.server.fastmcp import Context

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def search_pubmed_literature(
    disease_name: str,
    hpo_terms: list,
    ctx: Context = None,
) -> dict:
    """Search PubMed for recent clinical literature on a rare disease candidate.

    Queries the NIH PubMed database (free, no API key required) for case reports
    and clinical studies relevant to the top candidate disease, returning titles,
    authors, journal, and publication year to support the diagnostic report.
    """

    if not disease_name:
        return {"articles": [], "error": "No disease name provided."}

    # Build a focused query: disease name + rare disease context
    hpo_names = [t["name"] for t in hpo_terms[:3] if isinstance(t, dict) and t.get("name")]
    query_parts = [f'"{disease_name}"', "rare disease"]
    if hpo_names:
        query_parts.append(f'("{hpo_names[0]}")')
    query = " AND ".join(query_parts) + " AND (case report[pt] OR clinical study[pt])"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Step 1: search for PMIDs
            search_resp = await client.get(
                PUBMED_SEARCH,
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmax": "5",
                    "sort": "relevance",
                    "retmode": "json",
                    "datetype": "pdat",
                    "mindate": "2019",
                    "maxdate": "2026",
                },
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            pmids = search_data.get("esearchresult", {}).get("idlist", [])

            if not pmids:
                # Fallback: broader search without HPO terms
                search_resp2 = await client.get(
                    PUBMED_SEARCH,
                    params={
                        "db": "pubmed",
                        "term": f'"{disease_name}" AND rare disease',
                        "retmax": "5",
                        "sort": "relevance",
                        "retmode": "json",
                        "datetype": "pdat",
                        "mindate": "2019",
                        "maxdate": "2026",
                    },
                )
                search_resp2.raise_for_status()
                pmids = search_resp2.json().get("esearchresult", {}).get("idlist", [])

            if not pmids:
                return {"articles": [], "query": query, "note": "No recent literature found."}

            # Step 2: fetch summaries for those PMIDs
            summary_resp = await client.get(
                PUBMED_SUMMARY,
                params={
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "json",
                },
            )
            summary_resp.raise_for_status()
            summary_data = summary_resp.json()

            articles = []
            result = summary_data.get("result", {})
            for pmid in pmids:
                article = result.get(pmid, {})
                if not article:
                    continue
                authors = [a.get("name", "") for a in article.get("authors", [])[:3]]
                articles.append({
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "authors": authors,
                    "journal": article.get("fulljournalname", article.get("source", "")),
                    "year": article.get("pubdate", "")[:4],
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                })

            return {
                "articles": articles,
                "total_found": len(articles),
                "disease_queried": disease_name,
            }

    except Exception as exc:
        return {"articles": [], "error": f"PubMed search failed: {exc}"}
