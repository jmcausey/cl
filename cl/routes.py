from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from . import get_db
from .jobs import execute_job

bp = Blueprint("cl", __name__)

@bp.route("/")
def index():
    listings = get_db().execute(
        """SELECT * FROM craigslist_postings
           WHERE status != 'hidden'
           ORDER BY COALESCE(posted_at, scraped_at) DESC, id DESC
           LIMIT 200"""
    ).fetchall()
    return render_template("index.html", listings=listings)

@bp.route("/control", methods=("GET", "POST"))
def control():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            db.execute("DELETE FROM craigslist_jobs WHERE id=?", (request.form["job_id"],))
            db.commit()
            flash("Search removed.", "success")
            return redirect(url_for("cl.control"))
        if action == "run":
            job = db.execute("SELECT * FROM craigslist_jobs WHERE id=?", (request.form["job_id"],)).fetchone()
            if job is None:
                flash("Search not found.", "error")
            else:
                try:
                    inserted = execute_job(dict(job))
                    db.execute(
                        """UPDATE craigslist_jobs
                           SET last_run_at=CURRENT_TIMESTAMP,
                               last_status='completed',
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (job["id"],),
                    )
                    db.commit()
                    flash(f"Search completed: {inserted} new listings published.", "success")
                except Exception as exc:
                    db.execute(
                        """UPDATE craigslist_jobs
                           SET last_run_at=CURRENT_TIMESTAMP,
                               last_status='failed',
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (job["id"],),
                    )
                    db.commit()
                    flash(f"Search failed: {exc}", "error")
            return redirect(url_for("cl.control"))
        try:
            name = request.form["name"].strip()
            location = request.form["location"].strip()
            term = request.form["term"].strip()
            category = request.form.get("category", "sss").strip()
            radius = max(0, min(int(request.form.get("radius", "0")), 500))
            run_times = request.form.get("run_times", "").strip()
            enabled = 1 if request.form.get("enabled") else 0
            if not name or not location or not term:
                raise ValueError("Name, location, and search term are required.")
            for value in run_times.split(","):
                if value.strip():
                    datetime.strptime(value.strip(), "%H:%M")
            job_id = request.form.get("job_id")
            if job_id:
                db.execute(
                    """UPDATE craigslist_jobs SET name=?, location=?, term=?, category=?,
                       radius=?, run_times=?, enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (name, location, term, category, radius, run_times, enabled, job_id),
                )
            else:
                job_key = f"{name.lower().replace(' ', '-')}-{datetime.now().timestamp()}"
                db.execute(
                    """INSERT INTO craigslist_jobs
                       (job_key,name,location,term,category,radius,run_times,enabled)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (job_key, name, location, term, category, radius, run_times, enabled),
                )
            db.commit()
            flash("Search saved.", "success")
        except (KeyError, ValueError) as exc:
            flash(str(exc) or "Invalid search settings.", "error")
        return redirect(url_for("cl.control"))
    jobs = db.execute("SELECT * FROM craigslist_jobs ORDER BY enabled DESC, name COLLATE NOCASE").fetchall()
    return render_template("control.html", jobs=jobs)

@bp.route("/listing/<int:listing_id>/hide", methods=("POST",))
def hide_listing(listing_id):
    db = get_db()
    db.execute("UPDATE craigslist_postings SET status='hidden' WHERE id=?", (listing_id,))
    db.commit()
    return redirect(url_for("cl.index"))

@bp.route("/api/latest-id")
def latest_id():
    row = get_db().execute("SELECT id FROM craigslist_postings ORDER BY id DESC LIMIT 1").fetchone()
    return {"latest_id": row["id"] if row else 0}
