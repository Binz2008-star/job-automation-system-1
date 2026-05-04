from python_jobspy import scrape_jobs
import logging
import time

logger = logging.getLogger(__name__)

_QUERIES = [
    "ESG Manager",
    "HSE Manager",
    "Environmental Compliance Manager",
    "Sustainability Manager",
    "Operations Manager Environmental",
]

def get_jobs():
    seen = set()
    all_jobs = []
    for query in _QUERIES:
        try:
            df = scrape_jobs(
                site_name=["indeed"],
                search_term=query,
                location="United Arab Emirates",
                results_wanted=20,
                hours_old=48,
                country_indeed="united arab emirates",
            )
            for _, row in df.iterrows():
                link = str(row.get("job_url") or "")
                if link and link not in seen:
                    seen.add(link)
                    all_jobs.append({
                        "title": str(row.get("title", "") or ""),
                        "company": str(row.get("company", "") or ""),
                        "location": str(row.get("location", "") or ""),
                        "link": link,
                        "description": str(row.get("description", "") or ""),
                        "source": "indeed",
                    })
            time.sleep(3)
        except Exception:
            logger.warning(f"scrape_failed query={query}", exc_info=True)
    logger.info(f"jobs_fetched total={len(all_jobs)}")
    return all_jobs
