"""Accounts, sessions and CSRF.

Four decisions worth reading before the code:

1. **Session fixation.** On a successful login the session is *cleared* before
   the user id is stored. Without that, an attacker who can plant a session
   cookie in your browser before you log in keeps the same session id after you
   log in -- and therefore keeps your logged-in session. Clearing first means
   the id you hold before auth is worthless after it.

2. **One message for both failures.** A wrong password and an unknown email
   produce the same reply. Distinguishing them tells an attacker which addresses
   have accounts, which is a free account-enumeration oracle.

3. **Same response time is not attempted.** `check_password_hash` only runs when
   the user exists, so an unknown email returns measurably faster. Fixing that
   properly means hashing a dummy password on the miss path. Noted, not done --
   it is a timing side channel, and it is on the list.

4. **Logout is POST, not GET.** A GET logout can be triggered by any image tag
   on any page. Requiring POST + CSRF means a third-party site cannot log your
   users out.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from functools import wraps

import click
from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import connect_db

bp = Blueprint("auth", __name__)

SESSION_USER_KEY = "user_id"
CSRF_SESSION_KEY = "csrf_token"

MIN_PASSWORD_LENGTH = 8


# --------------------------------------------------------------------------
# Session helpers
# --------------------------------------------------------------------------


def current_user():
    """The logged-in user as a Row, or None.

    Goes to the database on every call rather than trusting a copy in the
    session. A session cookie is client-held and signed, not encrypted -- it is
    a claim about who you are, not proof, and it should not carry anything you
    would be unhappy to see forged.
    """
    user_id = session.get(SESSION_USER_KEY)
    if user_id is None:
        return None

    conn = connect_db(current_app.config["DATABASE"])
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------


def csrf_token() -> str:
    """A per-session token, created on first use. Exposed to templates."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def csrf_protect():
    """Reject state-changing requests without a matching token.

    Registered as `before_request`, so it is a property of the app rather than
    something each new route has to remember. A rule that depends on remembering
    is a rule that will be forgotten -- see the missing-WHERE lesson in
    LEARNING_LOG 14, same failure shape.
    """
    if not current_app.config.get("CSRF_ENABLED", True):
        return None
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return None

    sent = request.form.get("csrf_token")
    expected = session.get(CSRF_SESSION_KEY)

    # compare_digest, not ==: string comparison short-circuits on the first
    # differing byte, which leaks the token one byte at a time to anyone who can
    # measure the response. Constant-time comparison does not.
    if not expected or not sent or not secrets.compare_digest(sent, expected):
        return "Bad request.", 400

    return None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if not current_app.config.get("ALLOW_PUBLIC_SIGNUP"):
        # Closed by default. Opening the door to strangers is a deliberate
        # config change, not something you get by forgetting to turn it off.
        return "Signups are closed.", 403

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.")
            return redirect(url_for("auth.signup"))
        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            return redirect(url_for("auth.signup"))

        conn = connect_db(current_app.config["DATABASE"])
        try:
            conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, generate_password_hash(password), str(datetime.now())),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # The UNIQUE constraint on users.email is the real guard. Checking
            # "does this email exist?" first and then inserting is a race: two
            # simultaneous signups both pass the check and both insert. Let the
            # database enforce it and handle the failure.
            flash("That email is already registered.")
            return redirect(url_for("auth.signup"))
        finally:
            conn.close()

        return redirect(url_for("auth.login"))

    return render_template("signup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = connect_db(current_app.config["DATABASE"])
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email or password is incorrect.")
            return redirect(url_for("auth.login"))

        # Clear BEFORE storing: destroys the pre-login session id, so a session
        # planted before authentication does not survive it.
        session.clear()
        session[SESSION_USER_KEY] = user["id"]
        return redirect(url_for("journal.index"))

    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
# Operator commands
# --------------------------------------------------------------------------


@bp.cli.command("create-user")
@click.argument("email")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_user(email: str, password: str) -> None:
    """Create an account from the command line. The invite path.

    Run as:  flask create-user someone@example.com
    """
    email = email.strip().lower()
    conn = connect_db(current_app.config["DATABASE"])
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), str(datetime.now())),
        )
        conn.commit()
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]

        # The three entries written before accounts existed have no owner. The
        # operator creating the first account claims them; nobody else does.
        #
        # Deliberately NOT done in the public signup route: unreferenced rows
        # must never be adopted by whoever happens to register next.
        orphans = conn.execute(
            "SELECT COUNT(*) AS n FROM entries WHERE user_id IS NULL"
        ).fetchone()["n"]
        if orphans and conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1:
            conn.execute("UPDATE entries SET user_id = ? WHERE user_id IS NULL", (user_id,))
            conn.commit()
            click.echo(f"Claimed {orphans} ownerless entr(y/ies) for {email}.")
    except sqlite3.IntegrityError:
        raise click.ClickException(f"{email} is already registered.")
    finally:
        conn.close()

    click.echo(f"Created {email}.")
