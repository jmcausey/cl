from datetime import datetime
from .scraper import run_scraper, base_location_search_url

def execute_job(job):
    search_url = base_location_search_url(
        job["location"], category=job["category"], query=job["term"], radius=job["radius"]
    )
    return run_scraper(
        query=job["term"], max_results=None, search_url=search_url,
        category=job["category"], radius=job["radius"]
    )

def run_due_jobs(db, now=None, force=False):
    now = now or datetime.now()
    runs = 0
    jobs = db.execute("SELECT * FROM craigslist_jobs WHERE enabled IS TRUE ORDER BY id").fetchall()
    for job in jobs:
        times = [x.strip() for x in (job["run_times"] or "").split(",") if x.strip()]
        if force:
            times = [now.strftime("%H:%M")]
        for value in times:
            try:
                t = datetime.strptime(value, "%H:%M").time()
            except ValueError:
                continue
            scheduled = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if not force and scheduled > now:
                continue
            last = job["last_run_at"]
            if last:
                try:
                    last_dt = last if isinstance(last, datetime) else datetime.fromisoformat(last)
                    if last_dt >= scheduled:
                        continue
                except ValueError:
                    pass
            try:
                inserted = execute_job(dict(job))
                status = "completed"
                print(f"Search '{job['name']}' completed: {inserted} new listings.")
            except Exception as exc:
                status = "failed"
                print(f"Search '{job['name']}' failed: {exc}")
            db.execute(
                """UPDATE craigslist_jobs
                   SET last_run_at=?, last_status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (scheduled.isoformat(sep=" "), status, job["id"]),
            )
            db.commit()
            runs += 1
    return runs
