import functools,secrets
from authlib.integrations.flask_client import OAuth
from flask import Blueprint,current_app,flash,g,redirect,session,url_for
from werkzeug.security import generate_password_hash
from . import get_db
oauth=OAuth(); bp=Blueprint("auth",__name__,url_prefix="/auth")
def init_oauth(app):
    oauth.init_app(app); oauth.register(name="google",client_id=app.config["GOOGLE_CLIENT_ID"],client_secret=app.config["GOOGLE_CLIENT_SECRET"],server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",client_kwargs={"scope":"openid email profile"})
@bp.route("/login")
def login():
    if not current_app.config["GOOGLE_CLIENT_ID"] or not current_app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Google sign-in is not configured."); return redirect(url_for("cl.index"))
    return oauth.google.authorize_redirect(url_for("auth.callback",_external=True))
@bp.route("/callback")
def callback():
    try: token=oauth.google.authorize_access_token(); info=token.get("userinfo") or oauth.google.userinfo(token=token)
    except Exception: current_app.logger.exception("Google OAuth callback failed"); flash("Google sign-in failed. Please try again."); return redirect(url_for("auth.login"))
    sub,email=info.get("sub"),info.get("email")
    if not sub or not email or not info.get("email_verified",False): flash("Google did not provide a verified email address."); return redirect(url_for("auth.login"))
    db=get_db(); identity=db.execute("SELECT user_id FROM user_identity WHERE provider=? AND subject=?",("google",sub)).fetchone()
    if identity: uid=identity["user_id"]
    else:
        user=db.execute("SELECT id FROM user WHERE username=?",(email,)).fetchone()
        uid=user["id"] if user else db.execute("INSERT INTO user(username,password) VALUES(?,?)",(email,generate_password_hash(secrets.token_urlsafe(32)))).lastrowid
        db.execute("INSERT INTO user_identity(user_id,provider,subject,email) VALUES(?,?,?,?)",(uid,"google",sub,email)); db.commit()
    session.clear(); session["user_id"]=uid; return redirect(url_for("cl.index"))
@bp.route("/logout")
def logout(): session.clear(); return redirect(url_for("cl.index"))
@bp.before_app_request
def load_user():
    uid=session.get("user_id"); g.user=None if uid is None else get_db().execute("SELECT * FROM user WHERE id=?",(uid,)).fetchone()
def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped
