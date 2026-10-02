from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from urllib.parse import urlparse
from datetime import datetime
from . import get_db
from .auth import login_required
from .categories import CRAIGSLIST_CATEGORIES, CRAIGSLIST_CATEGORY_GROUPS
from .scraper import get_craigslist_listings, store_listing

bp = Blueprint("cl", __name__)

@bp.route("/")
def index():
    return _feed("all", "Craigslist Listings")

@bp.route("/pets")
def pets():
    return _feed("pet", "Craigslist Pets")

def _feed(category, title):
    db = get_db()
    where = "category = ?" if category != "all" else "1 = 1"
    params = (category,) if category != "all" else ()
    listings = db.execute(
        f"""SELECT * FROM craigslist_postings
            WHERE {where}
              AND (datetime(scraped_at) >= datetime('now', '-1 day')
                   OR status = 'pending')
              AND status != 'complete'
            ORDER BY COALESCE(posted_at, scraped_at) DESC, id DESC""",
        params,
    ).fetchall()
    return render_template("index.html", listings=listings, feed_title=title)

@bp.route("/api/latest-id")
def latest_id():
    row = get_db().execute(
        """SELECT id FROM craigslist_postings
           WHERE status != 'complete'
             AND (datetime(scraped_at) >= datetime('now', '-1 day')
                  OR status = 'pending')
           ORDER BY COALESCE(posted_at, scraped_at) DESC, id DESC LIMIT 1"""
    ).fetchone()
    return jsonify({"latest_id": row["id"] if row else 0})

@bp.route("/jobs", methods=("GET", "POST"))
@login_required
def jobs():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            db.execute("DELETE FROM craigslist_jobs WHERE id = ?", (request.form["job_id"],))
        else:
            try:
                values = _job_values(request.form)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("cl.jobs"))
            job_id = request.form.get("job_id")
            if job_id:
                db.execute(
                    """UPDATE craigslist_jobs SET name=?, term=?, category=?, radius=?,
                       run_times=?, location_name=?, location_url=?, is_default_location=?,
                       enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (*values, job_id),
                )
            else:
                job_key = request.form.get("job_key") or values[0].lower().replace(" ", "-")
                db.execute(
                    """INSERT INTO craigslist_jobs
                       (job_key,name,term,category,radius,run_times,location_name,location_url,
                        is_default_location,enabled)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (job_key, *values),
                )
        db.commit()
        flash("Craigslist search jobs updated.", "success")
        return redirect(url_for("cl.jobs"))

    jobs = db.execute(
        """SELECT * FROM craigslist_jobs
           ORDER BY enabled DESC, name COLLATE NOCASE"""
    ).fetchall()
    return render_template(
        "jobs.html", jobs=jobs, category_groups=CRAIGSLIST_CATEGORY_GROUPS
    )

def _job_values(form):
    name = form.get("name", "").strip()
    term = form.get("term", "").strip()
    category = form.get("category", "sss").strip()
    if category not in CRAIGSLIST_CATEGORIES:
        raise ValueError("Invalid Craigslist category.")
    try:
        radius = int(form.get("radius", "100"))
    except ValueError:
        radius = 100
    radius = max(5, min(radius, 500))
    run_times = form.get("run_times", "06:00").strip()
    for run_time in run_times.split(","):
        try:
            datetime.strptime(run_time.strip(), "%H:%M")
        except ValueError:
            raise ValueError("Run times must use HH:MM format.")
    location_name = form.get("location_name", "East Texas").strip()
    location_url = form.get(
        "location_url", "https://easttexas.craigslist.org/search/sss"
    ).strip()
    parsed = urlparse(location_url)
    if parsed.scheme != "https" or not parsed.netloc or "craigslist.org" not in parsed.netloc:
        raise ValueError("Location URL must be an HTTPS Craigslist URL.")
    is_default = 1 if form.get("is_default_location") else 0
    enabled = 1 if form.get("enabled") else 0
    if not name or not term:
        raise ValueError("Name and search term are required.")
    return (name, term, category, radius, run_times, location_name, location_url, is_default, enabled)

@bp.route("/jobs/<int:job_id>/run", methods=("POST",))
@login_required
def run_job(job_id):
    job = get_db().execute("SELECT * FROM craigslist_jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        return ("Job not found", 404)
    listings = get_craigslist_listings(
        query=job["term"], category=job["category"],
        search_url=job["location_url"], area_label=job["location_name"],
        radius=job["radius"], max_results=None,
    )
    db = get_db()
    inserted = sum(store_listing(item, db) for item in listings)
    db.execute(
        "UPDATE craigslist_jobs SET last_run_at=CURRENT_TIMESTAMP WHERE id=?",
        (job_id,),
    )
    db.commit()
    flash(f"Imported {inserted} new Craigslist listings.", "success")
    return redirect(url_for("cl.jobs"))
