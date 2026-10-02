from datetime import datetime
from urllib.parse import urlencode,urlparse
from .scraper import run_scraper
AREA_SEARCH_URL="https://www.craigslist.org/search/area/easttexas"
def execute_job(job):
    category=job["category"]; query=job["term"].strip(); location_url=job.get("location_url") or AREA_SEARCH_URL
    parsed=urlparse(location_url); params={"search_distance":job["radius"]}
    if parsed.path.startswith("/search/area/"): params["cat"]=category
    if not (category=="pet" and query.lower()=="pets"): params["query"]=query
    if parsed.path.startswith("/search/area/"): url=f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(params)}"
    else: url=f"{parsed.scheme}://{parsed.netloc}/search/{category}?{urlencode(params)}"
    return run_scraper(query=query,max_results=None,search_url=url,category=category,area_label=job.get("location_name","East Texas"),radius=job["radius"])
def run_due_jobs(db,now=None,force=False,runner=execute_job):
    now=now or datetime.now(); runs=0
    for job in db.execute("SELECT * FROM craigslist_jobs WHERE enabled=1 ORDER BY id").fetchall():
        times=[x.strip() for x in job["run_times"].split(",") if x.strip()]
        if force: times=[now.strftime("%H:%M")]
        for value in times:
            try: t=datetime.strptime(value,"%H:%M").time()
            except ValueError: continue
            scheduled=now.replace(hour=t.hour,minute=t.minute,second=0,microsecond=0)
            if not force and scheduled>now: continue
            last=job["last_run_at"]
            if last:
                try:
                    if datetime.fromisoformat(last)>=scheduled: continue
                except ValueError: pass
            db.execute("UPDATE craigslist_jobs SET last_run_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(scheduled.isoformat(sep=" "),job["id"]))
            history=db.execute("INSERT INTO search_query(term,radius,status,created) VALUES(?,?,?,?)",(job["term"],job["radius"],"running",scheduled.isoformat(sep=" ")))
            db.commit()
            try:
                runner(dict(job)); status="completed"
            except Exception as exc:
                status="failed"; print(f"Craigslist job '{job['name']}' failed: {exc}")
            db.execute("UPDATE search_query SET status=? WHERE id=?",(status,history.lastrowid)); db.commit(); runs+=1
    return runs
