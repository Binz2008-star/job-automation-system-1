from src.applications import get_applied_jobs

apps = get_applied_jobs()
print(f'Total applications: {len(apps)}')
for i, app in enumerate(apps, 1):
    print(f'{i}. {app.get("title", "Unknown")} - {app.get("company", "Unknown")}')
    print(f'   Status: {app.get("status", "unknown")}')
    print(f'   Link: {app.get("link", "No link")}')
    print()
