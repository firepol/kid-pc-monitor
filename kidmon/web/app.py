"""The single Flask app served on each kid PC.

Two audiences share one port:

* The kid gets the open, read-only status page at ``/`` and ``/api/status``.
* The parent logs in at ``/admin`` (session cookie, password hashed with
  werkzeug) and drives the control endpoints under ``/api/admin/*``.

The app is a thin HTTP layer over a :class:`~kidmon.control.TimeControl`
instance — it parses requests and calls control methods; all enforcement logic
lives in ``control``.

Security note: traffic is plain HTTP by default. On a home LAN that is usually
fine, but anyone who can reach the port can read the kid status. The admin side
is password-protected. Put it behind HTTPS (e.g. a reverse proxy) if you expose
it beyond your LAN.
"""
import functools
import logging
import os

from flask import (
    Flask, jsonify, redirect, render_template_string, request, session, url_for,
)
from werkzeug.security import check_password_hash

from .templates import KID_PAGE, LOGIN_PAGE, ADMIN_PAGE

logger = logging.getLogger("kidmon.web")


def _secret_key(storage):
    """Stable per-install Flask secret so sessions survive a restart."""
    key = storage.get_state("web_secret")
    if not key:
        key = os.urandom(24).hex()
        storage.set_state("web_secret", key)
    return key


def create_app(control, config, storage):
    app = Flask(__name__)
    app.secret_key = _secret_key(storage)

    def require_admin(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin"):
                return jsonify(ok=False, message="Not authorised"), 401
            return view(*args, **kwargs)
        return wrapped

    # --- open (kid) routes ---------------------------------------------------

    @app.get("/")
    def kid_page():
        return render_template_string(KID_PAGE)

    @app.get("/api/status")
    def api_status():
        return jsonify(control.status())

    # --- chat (open page; role decided server-side from the session) ---------

    # The display name is cosmetic and read from a cookie, but it is only
    # trusted when the request carries a valid admin session — so a kid can't
    # post as a parent (they have no signed session), only relabel nothing.
    PARENT_NAME_COOKIE = "kidmon_parent_name"

    @app.get("/api/chat")
    def api_chat_get():
        if not control.chat_enabled:
            return jsonify(enabled=False, messages=[])
        is_parent = bool(session.get("admin"))
        parent_name = (request.cookies.get(PARENT_NAME_COOKIE, "Parent")
                       if is_parent else None)
        return jsonify(enabled=True, is_parent=is_parent,
                       kid_name=control.kid_name, parent_name=parent_name,
                       messages=storage.get_messages(50))

    @app.post("/api/chat")
    def api_chat_post():
        if not control.chat_enabled:
            return jsonify(ok=False, message="Chat disabled"), 403
        body = ((request.json or {}).get("body") or "").strip()
        if not body:
            return jsonify(ok=False, message="Empty message"), 400
        is_parent = bool(session.get("admin"))
        parent_name = request.cookies.get(PARENT_NAME_COOKIE, "Parent")
        msg = control.post_chat(body, is_parent, parent_name)
        return jsonify(ok=True, message=msg)

    # --- auth ----------------------------------------------------------------

    @app.route("/admin", methods=["GET"])
    def admin():
        if not session.get("admin"):
            return redirect(url_for("login"))
        return render_template_string(ADMIN_PAGE, s=control.status())

    @app.route("/login", methods=["GET", "POST"])
    def login():
        _, password_hash = config.get_admin_credentials()
        configured = bool(password_hash)
        # Remember a previously-chosen chat name so it pre-fills the form.
        saved_name = request.cookies.get(PARENT_NAME_COOKIE, "")
        if request.method == "POST":
            pw = request.form.get("password", "")
            if not configured:
                return render_template_string(
                    LOGIN_PAGE, configured=False, parent_name=saved_name,
                    error="No admin password configured.")
            # One shared password for all parents — no username. Each parent
            # picks a display name (for chat) at login; it's not a credential.
            if check_password_hash(password_hash, pw):
                session["admin"] = True
                resp = redirect(url_for("admin"))
                name = request.form.get("name", "").strip()[:40]
                if name:
                    resp.set_cookie(PARENT_NAME_COOKIE, name,
                                    max_age=60 * 60 * 24 * 365, samesite="Lax")
                return resp
            return render_template_string(
                LOGIN_PAGE, configured=True, parent_name=saved_name,
                error="Wrong password.")
        return render_template_string(LOGIN_PAGE, configured=configured,
                                      parent_name=saved_name, error=None)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("kid_page"))

    # --- admin actions -------------------------------------------------------

    @app.post("/api/admin/lock")
    @require_admin
    def admin_lock():
        control.lock_pc()
        return jsonify(ok=True, message="Computer locked")

    @app.post("/api/admin/set_limit")
    @require_admin
    def admin_set_limit():
        try:
            minutes = int(request.json["minutes"])
        except (KeyError, TypeError, ValueError):
            return jsonify(ok=False, message="Invalid minutes"), 400
        if minutes < 0:
            # A negative limit would make get_time_remaining clamp to 0 and lock
            # the PC instantly ("Time's up") with no time actually used.
            return jsonify(ok=False, message="Minutes must be 0 or more"), 400
        control.set_usage_limit(minutes)
        return jsonify(ok=True, message=f"Limit set to {minutes} minutes")

    @app.post("/api/admin/extend")
    @require_admin
    def admin_extend():
        try:
            minutes = int(request.json["minutes"])
        except (KeyError, TypeError, ValueError):
            return jsonify(ok=False, message="Invalid minutes"), 400
        if control.extend_time(minutes):
            return jsonify(ok=True, message=f"Extended by {minutes} minutes")
        return jsonify(ok=False, message="No limit set to extend"), 400

    @app.post("/api/admin/add_lock_time")
    @require_admin
    def admin_add_lock_time():
        try:
            hour, minute = map(int, request.json["time"].split(":"))
        except (KeyError, TypeError, ValueError):
            return jsonify(ok=False, message="Invalid time (use HH:MM)"), 400
        control.add_scheduled_lock(hour, minute)
        control.save_state()
        return jsonify(ok=True, message=f"Lock added at {hour:02d}:{minute:02d}")

    @app.post("/api/admin/clear")
    @require_admin
    def admin_clear():
        what = (request.json or {}).get("what")
        if what == "usage":
            control.clear_usage_limit()
        elif what == "locks":
            control.clear_lock_times()
        elif what == "all":
            control.clear_all()
        else:
            return jsonify(ok=False, message="Unknown clear target"), 400
        return jsonify(ok=True, message=f"Cleared {what}")

    @app.post("/api/admin/message")
    @require_admin
    def admin_message():
        body = (request.json or {}).get("message", "").strip()
        if not body:
            return jsonify(ok=False, message="Empty message"), 400
        # Route through the chat store (not just an OS popup): the message is
        # persisted and shows in the kid's chat thread even if notify-send /
        # the OS notifier is missing, so it isn't silently dropped.
        parent_name = request.cookies.get(PARENT_NAME_COOKIE, "Parent")
        control.post_chat(body, is_parent=True, parent_name=parent_name)
        return jsonify(ok=True, message="Message sent")

    @app.get("/api/admin/history")
    @require_admin
    def admin_history():
        return jsonify(rows=storage.get_history(limit=30))

    @app.get("/api/admin/activity")
    @require_admin
    def admin_activity():
        return jsonify(rows=storage.get_activity_summary())

    return app
