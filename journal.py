"""Journal routes: read entries, save an entry.

Every route here is behind `@login_required`, and every query that touches
entries carries `WHERE user_id = ?`. Those two sentences are the whole privacy
model for this module, and the second one is the one that fails silently: a
missing login check gives you a redirect, a missing WHERE gives you someone
else's diary with no error at all.
"""
from datetime import datetime

from flask import Blueprint, current_app, render_template, request

from analysis import AnalysisError, analyze_entry
from auth import current_user, login_required
from db import connect_db

bp = Blueprint("journal", __name__)


@bp.route("/")
@login_required
def index():
    user = current_user()

    conn = connect_db(current_app.config["DATABASE"])
    # ORDER BY id DESC rather than timestamp: id is the insertion order and
    # never ties. Two entries written in the same microsecond share a timestamp,
    # and `ORDER BY timestamp` would then return them in an arbitrary order that
    # can differ between page loads.
    entries = conn.execute(
        "SELECT * FROM entries WHERE user_id = ? ORDER BY id DESC", (user["id"],)
    ).fetchall()
    conn.close()

    return render_template("index.html", entries=entries, user=user)


@bp.route("/entries", methods=["POST"])
@login_required
def save_entry():
    user = current_user()

    # `.get()` instead of `["entry_text"]`: an absent field is a bad request, not a
    # crash. `.strip()` closes the gap where "   " slipped past the old length check.
    user_entry = (request.form.get("entry_text") or "").strip()
    if not user_entry:
        return "No entry. Verify that an entry was made.", 400

    timestamp = str(datetime.now())
    # Save first: the writing is on disk before the network is touched.
    conn = connect_db(current_app.config["DATABASE"])
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (timestamp, user_entry, None, None, None, user["id"]))

    entry_id = cursor.lastrowid      # readable only until conn.close()
    conn.commit()
    conn.close()

    try:
        analysis = analyze_entry(user_entry, current_app.config["GROQ_API_KEY"])
    except AnalysisError as e:
        # One except clause, because analysis.py funnels every failure into one
        # type. This is now the only place a Groq-shaped failure can reach the
        # user -- a malformed model response can no longer become a 500.
        #
        # The row stays analysis_status='pending', so the retry worker will pick
        # it up. Returning 502 tells the truth about what happened: the entry
        # saved, the analysis did not.
        current_app.logger.warning("Mood analysis failed for entry %s: %s", entry_id, e)
        return "Entry saved. Mood analysis unavailable right now.", 502

    conn = connect_db(current_app.config["DATABASE"])
    cursor = conn.cursor()
    # `AND user_id = ?` is redundant today -- entry_id came from our own INSERT
    # one function above, so it is provably this user's row. It is here anyway,
    # because "provably" is a property of the current code, not of the statement.
    # If entry_id ever arrives from a form field or a URL, this line is already
    # correct and the version without it is already a breach.
    cursor.execute(
        "UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ?, "
        "analysis_status = 'ok' WHERE id = ? AND user_id = ?",
        (analysis.mood_label, analysis.mood_score, analysis.reflection,
         entry_id, user["id"]))

    conn.commit()
    conn.close()
    return (
        f"Based on the journal entry, the mood is predicted to be: {analysis.mood_label}, "
        f"with mood score: {analysis.mood_score}, and reflection: {analysis.reflection}"
    )
