# Job Automation System

Automated job hunting system that finds, filters, scores, and notifies you about relevant job opportunities.

## Features

- **Multi-source Job Fetching**: Scrapes jobs from Indeed, LinkedIn, and Google
- **Intelligent Scoring**: Filters jobs based on relevance (score ≥ 40)
- **Deduplication**: Tracks seen jobs to avoid duplicates across runs
- **Email Notifications**: Sends daily reports with high-quality matches
- **Custom Search**: Configurable search terms, locations, and filters

## Architecture

```
JobSpy (fetch jobs)
    ↓
Filter (remove duplicates)
    ↓
Scoring (filter good ones)
    ↓
Email Notification (send report)
```

## Setup

### Prerequisites

- Python 3.10+
- Gmail account with 2FA enabled
- Gmail App Password

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Binz2008-star/job-automation-system-1.git
cd job-automation-system-1
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in `.env`:
```env
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password
EMAIL_TO=your_email@gmail.com
```

### Generate Gmail App Password

1. Enable 2FA on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate a new app password for "Mail"
4. Use the 16-character password in `.env`

## Usage

Run the daily job scraper:
```bash
python -m src.run_daily
```

### Output

- Console: Shows job matches with scores
- Email: Daily report with top 10 high-quality jobs
- Data: `data/seen_jobs.json` tracks seen jobs

## Configuration

Edit `src/job_sources.py` to customize:
- Search terms
- Location
- Number of results
- Job age filter

Edit `src/scoring.py` to adjust scoring criteria.

## Project Structure

```
job-automation-system-1/
├── src/
│   ├── job_sources.py      # Job fetching logic
│   ├── scoring.py          # Job scoring algorithm
│   ├── filter.py           # Deduplication system
│   ├── notifier.py         # Email notifications
│   ├── message_generator.py # Cover message templates
│   └── run_daily.py        # Main pipeline
├── data/
│   └── seen_jobs.json      # Seen jobs database
├── .env                    # Environment variables
└── requirements.txt        # Python dependencies
```

## Current Status

✅ Phase 1: Job Fetching & Scoring
✅ Phase 2: Deduplication & Memory
✅ Phase 3: Email Notifications
⏳ Phase 4: Automation (scheduled runs, Telegram integration)

## License

MIT
