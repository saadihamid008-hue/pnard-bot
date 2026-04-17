"""World Bank scraper — uses the public Projects API, verified live April 2026.

The API is JSON, stable, and free (no key required). We fetch active Pakistan
projects sorted by board approval date (most recent first). New project entries
are the signal — they typically precede subcontracting opportunities by weeks
to months.
"""
import hashlib

import requests

API_URL = "https://search.worldbank.org/api/v2/projects"
PARAMS = {
    "format": "json",
    "countrycode_exact": "PK",
    "srt": "boardapprovaldate",   # sort
    "order": "desc",
    "rows": 50,
    "fl": ("id,project_name,boardapprovaldate,status,countryshortname,"
           "sector1,theme1,url,project_abstract,lendinginstr"),
}

TIMEOUT = 25
UA = "PNARD-Bot/1.0 (opportunity monitoring; contact via pnard.com)"


def scrape_worldbank() -> list[dict]:
    try:
        r = requests.get(API_URL, params=PARAMS, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[WB] fetch failed: {e}")
        return []

    try:
        data = r.json()
    except ValueError as e:
        print(f"[WB] JSON parse failed: {e}")
        return []

    projects = data.get("projects") or {}
    if not isinstance(projects, dict):
        return []

    out: list[dict] = []
    for proj_id, proj in projects.items():
        if not isinstance(proj, dict):
            continue
        name = (proj.get("project_name") or "").strip()
        if not name:
            continue
        status = (proj.get("status") or "").strip()
        # Skip closed/dropped — we want live pipeline
        if status.lower() in {"closed", "dropped"}:
            continue
        url = (proj.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{proj_id}").strip()
        sector = ""
        s1 = proj.get("sector1")
        if isinstance(s1, dict):
            sector = (s1.get("Name") or "").strip()
        theme = ""
        t1 = proj.get("theme1")
        if isinstance(t1, dict):
            theme = (t1.get("Name") or "").strip()
        abstract = (proj.get("project_abstract") or {})
        abstract_text = ""
        if isinstance(abstract, dict):
            abstract_text = (abstract.get("cdata!") or "").strip()

        summary_bits = [b for b in [status, sector, theme, abstract_text] if b]
        summary = " · ".join(summary_bits[:3])
        if abstract_text and abstract_text not in summary:
            summary = (summary + " — " + abstract_text) if summary else abstract_text

        lid = "wb:" + hashlib.sha1(proj_id.encode("utf-8")).hexdigest()[:16]
        out.append({
            "id": lid,
            "source": "World Bank",
            "title": f"{proj_id}: {name}",
            "summary": summary,
            "url": url,
            "date": (proj.get("boardapprovaldate") or "")[:10],
        })
    return out
