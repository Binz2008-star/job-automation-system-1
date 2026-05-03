from jobspy import scrape_jobs


def get_jobs():
    jobs_df = scrape_jobs(
        site_name=["indeed", "linkedin", "google"],
        search_term="Executive Assistant OR Operations Manager OR Chief of Staff",
        location="UAE",
        results_wanted=30,
        hours_old=24,
        country_indeed="united arab emirates"
    )

    jobs = []

    for _, row in jobs_df.iterrows():
        jobs.append({
            "title": row.get("title"),
            "company": row.get("company"),
            "location": row.get("location"),
            "link": row.get("job_url"),
            "description": row.get("description")
        })

    return jobs
