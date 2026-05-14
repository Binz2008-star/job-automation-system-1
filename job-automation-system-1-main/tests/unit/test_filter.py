import json

import src.filter as job_filter


def test_filter_prefers_link_for_dedupe(monkeypatch, tmp_path):
    seen_file = tmp_path / "seen_jobs.json"
    monkeypatch.setattr(job_filter, "SEEN_JOBS_FILE", str(seen_file))
    monkeypatch.setattr(job_filter, "is_db_available", lambda: False)

    jobs = [
        {"title": "Executive Assistant", "company": "A", "location": "Dubai", "link": "https://example.com/1"},
        {"title": "Executive Assistant", "company": "A", "location": "Dubai", "link": "https://example.com/1"},
    ]

    new_jobs = job_filter.filter_new_jobs(jobs)

    assert len(new_jobs) == 1
    assert json.loads(seen_file.read_text()) == ["https://example.com/1"]


def test_filter_falls_back_to_composite_id_when_link_missing(monkeypatch, tmp_path):
    seen_file = tmp_path / "seen_jobs.json"
    monkeypatch.setattr(job_filter, "SEEN_JOBS_FILE", str(seen_file))
    monkeypatch.setattr(job_filter, "is_db_available", lambda: False)

    jobs = [
        {"title": "Chief of Staff", "company": "B", "location": "Abu Dhabi", "link": ""},
        {"title": "Chief of Staff", "company": "B", "location": "Abu Dhabi"},
    ]

    new_jobs = job_filter.filter_new_jobs(jobs)

    assert len(new_jobs) == 1
    assert json.loads(seen_file.read_text()) == ["Chief of Staff_B_Abu Dhabi"]


def test_load_seen_jobs_handles_corrupt_json(monkeypatch, tmp_path):
    seen_file = tmp_path / "seen_jobs.json"
    seen_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(job_filter, "SEEN_JOBS_FILE", str(seen_file))
    monkeypatch.setattr(job_filter, "is_db_available", lambda: False)

    assert job_filter.load_seen_jobs() == set()
