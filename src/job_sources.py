import requests

def get_jobs():
    url = "https://jsearch.p.rapidapi.com/search"
    querystring = {
        "query": "executive assistant OR operations manager UAE",
        "page": "1",
        "num_pages": "1"
    }

    headers = {
        "X-RapidAPI-Key": "YOUR_API_KEY",
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=querystring)
    data = response.json()

    jobs = []
    for job in data.get("data", []):
        jobs.append({
            "title": job.get("job_title"),
            "company": job.get("employer_name"),
            "location": job.get("job_city"),
            "link": job.get("job_apply_link")
        })

    return jobs