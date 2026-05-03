def score_job(job):
    score = 0
    title = (job.get("title") or "").lower()

    keywords = [
        "executive",
        "assistant",
        "operations",
        "manager",
        "chief",
        "staff",
        "compliance",
        "director"
    ]

    for kw in keywords:
        if kw in title:
            score += 15

    return score