from datetime import datetime
import subprocess
import sys
from pathlib import Path
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from . import get_db
from .jobs import execute_job
from .scraper import craigslist_locations

bp = Blueprint("cl", __name__)

BLOG_STATUSES = ("pending", "completed")


@bp.route("/api/locations")
def api_locations():
    try:
        return jsonify(craigslist_locations())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 503


def normalize_blog_status(status):
    value = (status or "pending").strip().lower()
    return value if value in BLOG_STATUSES else "pending"


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def blog_allowed_emails():
    raw = (current_app.config.get("BLOG_ALLOWED_EMAILS") or "").strip()
    return {value.strip().lower() for value in raw.split(",") if value.strip()}


def is_blog_admin(user):
    if not user:
        return False
    email = (user.get("email") or "").strip().lower()
    return bool(email) and email in blog_allowed_emails()


@bp.route("/")
def index():
    listings = get_db().execute(
        """SELECT * FROM craigslist_postings
           WHERE status NOT IN ('hidden', 'unpublished')
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
                db.execute(
                    """UPDATE craigslist_jobs
                       SET last_run_at=CURRENT_TIMESTAMP,
                           last_status='running',
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (job["id"],),
                )
                db.commit()
                project_root = Path(current_app.root_path).parent
                subprocess.Popen(
                    [sys.executable, str(project_root / "scheduler.py"), "--job-id", str(job["id"])],
                    cwd=str(project_root),
                    start_new_session=True,
                )
                flash("Search started. Results will appear as the job completes.", "success")
            return redirect(url_for("cl.control"))
        try:
            name = request.form["name"].strip()
            location = request.form["location"].strip()
            term = request.form["term"].strip()
            category = request.form.get("category", "sss").strip()
            radius = max(0, min(int(request.form.get("radius", "0")), 500))
            run_times = request.form.get("run_times", "").strip()
            enabled = bool(request.form.get("enabled"))
            post_to_blog = bool(request.form.get("post_to_blog"))
            if not name or not location or not term:
                raise ValueError("Name, location, and search term are required.")
            for value in run_times.split(","):
                if value.strip():
                    datetime.strptime(value.strip(), "%H:%M")
            job_id = request.form.get("job_id")
            if job_id:
                db.execute(
                          """UPDATE craigslist_jobs SET name=?, location=?, term=?, category=?,
                              radius=?, run_times=?, enabled=?, post_to_blog=?,
                              updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                          (name, location, term, category, radius, run_times, enabled, post_to_blog, job_id),
                )
            else:
                job_key = f"{name.lower().replace(' ', '-')}-{datetime.now().timestamp()}"
                db.execute(
                    """INSERT INTO craigslist_jobs
                              (job_key,name,location,term,category,radius,run_times,enabled,post_to_blog)
                              VALUES (?,?,?,?,?,?,?,?,?)""",
                          (job_key, name, location, term, category, radius, run_times, enabled, post_to_blog),
                )
            db.commit()
            flash("Search saved.", "success")
        except (KeyError, ValueError) as exc:
            flash(str(exc) or "Invalid search settings.", "error")
        return redirect(url_for("cl.control"))
    jobs = db.execute("SELECT * FROM craigslist_jobs ORDER BY enabled DESC, name").fetchall()
    return render_template("control.html", jobs=jobs)

@bp.route("/listing/<int:listing_id>/hide", methods=("POST",))
def hide_listing(listing_id):
    db = get_db()
    db.execute("UPDATE craigslist_postings SET status='hidden' WHERE id=?", (listing_id,))
    db.commit()
    return redirect(url_for("cl.index"))


@bp.route("/listing/<int:listing_id>/status", methods=("POST",))
def craigslist_listing_status(listing_id):
    current_user = get_current_user()
    if not current_user:
        flash("Please sign in with Google to update listings.", "error")
        return redirect(url_for("cl.google_login"))
    if not is_blog_admin(current_user):
        flash("Only the configured blog admin can update listings.", "error")
        return redirect(url_for("cl.blog"))

    status = request.form.get("action", "").strip().lower()
    if status not in BLOG_STATUSES:
        flash("Choose pending or completed for the listing status.", "error")
        return redirect(url_for("cl.blog"))

    db = get_db()
    cursor = db.execute(
        "UPDATE craigslist_postings SET status = ? WHERE id = ? AND status != 'hidden'",
        (status, listing_id),
    )
    db.commit()
    if cursor.rowcount:
        flash(f"Listing marked as {status}.", "success")
    else:
        flash("Listing not found or hidden.", "error")
    return redirect(url_for("cl.blog"))


@bp.route("/auth/login")
def google_login():
    oauth = current_app.extensions.get("oauth")
    if not oauth or "google" not in oauth._clients:
        flash("Google OAuth is not configured.", "error")
        return redirect(url_for("cl.blog"))
    redirect_uri = url_for("cl.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.route("/auth/callback")
def google_callback():
    oauth = current_app.extensions.get("oauth")
    if not oauth or "google" not in oauth._clients:
        flash("Google OAuth is not configured.", "error")
        return redirect(url_for("cl.blog"))
    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.userinfo()
        if not token or not user_info:
            raise ValueError("Google login failed.")
    except Exception as exc:
        flash(f"Google sign-in failed: {exc}", "error")
        return redirect(url_for("cl.blog"))

    db = get_db()
    google_sub = user_info.get("sub") or user_info.get("email")
    email = (user_info.get("email") or "").strip()
    name = (user_info.get("name") or user_info.get("email") or "Google User").strip()
    picture = (user_info.get("picture") or "").strip()

    if not google_sub or not email:
        flash("Google account did not return the required profile data.", "error")
        return redirect(url_for("cl.blog"))

    db.execute(
        """
        INSERT INTO users (google_sub, email, name, picture, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(google_sub) DO UPDATE SET
            email=EXCLUDED.email,
            name=EXCLUDED.name,
            picture=EXCLUDED.picture,
            updated_at=CURRENT_TIMESTAMP
        """,
        (google_sub, email, name, picture),
    )
    user = db.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
    db.commit()
    session["user_id"] = user["id"]
    session["user_name"] = name
    session["user_email"] = email
    flash("Signed in with Google.", "success")
    return redirect(url_for("cl.blog"))


@bp.route("/auth/logout")
def google_logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("cl.blog"))


@bp.route("/blog")
def blog():
    current_user = get_current_user()
    is_admin = is_blog_admin(current_user)
    db = get_db()
    posts = db.execute(
        """
        SELECT bp.*, u.name AS author_name, u.email AS author_email
        FROM blog_posts bp
        LEFT JOIN users u ON u.id = bp.user_id
        ORDER BY CASE bp.status WHEN 'pending' THEN 0 ELSE 1 END, bp.updated_at DESC
        """
    ).fetchall()
    listings = db.execute(
        """SELECT * FROM craigslist_postings
           WHERE status NOT IN ('hidden', 'unpublished')
           ORDER BY COALESCE(posted_at, scraped_at) DESC, id DESC
           LIMIT 200"""
    ).fetchall()
    latest_listing_id = db.execute(
        "SELECT COALESCE(MAX(id), 0) AS latest_id FROM craigslist_postings "
        "WHERE status NOT IN ('hidden', 'unpublished')"
    ).fetchone()["latest_id"]
    return render_template(
        "blog.html",
        posts=posts,
        listings=listings,
        latest_listing_id=latest_listing_id,
        current_user=current_user,
        is_admin=is_admin,
    )


@bp.route("/blog/admin")
def blog_admin():
    current_user = get_current_user()
    if not current_user:
        flash("Please sign in with Google to access the admin dashboard.", "error")
        return redirect(url_for("cl.google_login"))
    if not is_blog_admin(current_user):
        flash("Only the configured blog admin can view the dashboard.", "error")
        return redirect(url_for("cl.blog"))

    db = get_db()
    status_filter = request.args.get("status", "all").strip().lower()
    if status_filter not in {"all", "pending", "completed"}:
        status_filter = "all"

    sort_order = request.args.get("sort", "updated_desc").strip().lower()
    if sort_order not in {"updated_desc", "updated_asc", "created_desc", "created_asc"}:
        sort_order = "updated_desc"

    search_term = (request.args.get("search", "") or "").strip()
    my_posts_only = request.args.get("mine", "0").strip().lower() in {"1", "true", "yes", "on"}
    pending_only = request.args.get("pending", "0").strip().lower() in {"1", "true", "yes", "on"}

    query = """
        SELECT bp.*, u.name AS author_name, u.email AS author_email
        FROM blog_posts bp
        LEFT JOIN users u ON u.id = bp.user_id
    """
    params = []
    clauses = []
    if status_filter != "all":
        clauses.append("bp.status = ?")
        params.append(status_filter)
    elif pending_only:
        clauses.append("bp.status = ?")
        params.append("pending")
    if search_term:
        clauses.append("(LOWER(bp.title) LIKE ? OR LOWER(bp.body) LIKE ?)")
        like_term = f"%{search_term.lower()}%"
        params.extend([like_term, like_term])
    if my_posts_only:
        clauses.append("bp.user_id = ?")
        params.append(current_user["id"])
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    sort_clause = {
        "updated_desc": " ORDER BY CASE bp.status WHEN 'pending' THEN 0 ELSE 1 END, bp.updated_at DESC",
        "updated_asc": " ORDER BY CASE bp.status WHEN 'pending' THEN 0 ELSE 1 END, bp.updated_at ASC",
        "created_desc": " ORDER BY CASE bp.status WHEN 'pending' THEN 0 ELSE 1 END, bp.created_at DESC",
        "created_asc": " ORDER BY CASE bp.status WHEN 'pending' THEN 0 ELSE 1 END, bp.created_at ASC",
    }[sort_order]
    query += sort_clause

    posts = db.execute(query, params).fetchall()
    summary = db.execute(
        "SELECT status, COUNT(*) AS count FROM blog_posts GROUP BY status"
    ).fetchall()
    counts = {"pending": 0, "completed": 0, "total": 0}
    for row in summary:
        counts["total"] += row["count"]
        if row["status"] in counts:
            counts[row["status"]] = row["count"]

    return render_template(
        "blog_admin.html",
        posts=posts,
        current_user=current_user,
        status_filter=status_filter,
        sort_order=sort_order,
        search_term=search_term,
        mine=my_posts_only,
        pending_only=pending_only,
        counts=counts,
    )


@bp.route("/blog/new", methods=("GET", "POST"))
def blog_new():
    current_user = get_current_user()
    is_admin = is_blog_admin(current_user)
    if not current_user:
        flash("Please sign in with Google to create a blog post.", "error")
        return redirect(url_for("cl.google_login"))
    if not is_admin:
        flash("Only the configured blog admin can create posts.", "error")
        return redirect(url_for("cl.blog"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        status = normalize_blog_status(request.form.get("status"))

        if not title or not body:
            flash("Title and body are required.", "error")
            return render_template("blog_new.html", current_user=current_user, is_admin=is_admin)

        get_db().execute(
            "INSERT INTO blog_posts (user_id, title, body, status) VALUES (?, ?, ?, ?)",
            (current_user["id"], title, body, status),
        )
        get_db().commit()
        flash("Blog post created.", "success")
        return redirect(url_for("cl.blog"))

    return render_template("blog_new.html", current_user=current_user, is_admin=is_admin)


@bp.route("/blog/<int:post_id>/status", methods=("POST",))
def blog_status(post_id):
    current_user = get_current_user()
    is_admin = is_blog_admin(current_user)
    if not current_user:
        flash("Please sign in with Google to update blog posts.", "error")
        return redirect(url_for("cl.google_login"))

    db = get_db()
    post = db.execute(
        "SELECT * FROM blog_posts WHERE id = ?",
        (post_id,),
    ).fetchone()

    if post is None:
        flash("Blog post not found.", "error")
        return redirect(url_for("cl.blog"))

    can_manage = is_admin or post["user_id"] == current_user["id"]
    if not can_manage:
        flash("Blog post not found or you cannot modify it.", "error")
        return redirect(url_for("cl.blog"))

    action = request.form.get("action", "pending")
    if action == "delete":
        db.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
        db.commit()
        flash("Blog post deleted.", "success")
        return redirect(url_for("cl.blog"))

    status = normalize_blog_status(action)
    db.execute(
        "UPDATE blog_posts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, post_id),
    )
    db.commit()
    flash(f"Blog post marked as {status}.", "success")
    return redirect(url_for("cl.blog"))


@bp.route("/api/latest-id")
def latest_id():
    row = get_db().execute(
        "SELECT id FROM craigslist_postings "
        "WHERE status NOT IN ('hidden', 'unpublished') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {"latest_id": row["id"] if row else 0}
