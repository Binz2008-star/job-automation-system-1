from src.telegram_bot import format_telegram_jobs


def test_telegram_formatter_escapes_html():
    jobs = [(
        {
            "title": "<script>alert(1)</script>",
            "company": "ACME <b>bold</b>",
            "location": "Dubai & UAE",
            "link": "https://example.com/job",
        },
        88,
    )]

    output = format_telegram_jobs(jobs)

    assert "<script>" not in output
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in output
    assert "&lt;b&gt;bold&lt;/b&gt;" in output


def test_telegram_formatter_rejects_javascript_links():
    jobs = [(
        {
            "title": "Security Engineer",
            "company": "ACME",
            "location": "Dubai",
            "link": "javascript:alert(1)",
        },
        91,
    )]

    output = format_telegram_jobs(jobs)

    assert 'href="#"' in output
