"""Journal routes: read entries, save an entry.

Extracted from app.py so the factory can register it. It becomes a blueprint
now rather than later because auth is arriving next and will be a second
blueprint -- having one route group already shaped as an app would mean
reshaping it in the same commit that adds login, which is how a commit that
changes two things becomes a commit nobody can review.
"""
from datetime import datetime

from flask import Blueprint, current_app, render_template, request

from analysis import AnalysisError, analyze_entry
from db import connect_db

bp = Blueprint("journal", __name__)


@bp.route("/")
def index():
    conn = connect_db(current_app.config["DATABASE"])
    entries = conn.execute("SELECT * FROM entries").fetchall()
    conn.close()

    return render_template("index.html", entries=entries)


@bp.route("/entries", methods=["POST"])
def save_entry():
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
        "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)",
        (timestamp, user_entry, None, None, None))

    entry_id = cursor.lastrowid      # readable only until conn.close()
    conn.commit()
    conn.close()

    try:
        analysis = analyze_entry(user_entry, current_app.config["GROQ_API_KEY"])
    except AnalysisError as e:
        # One except clause, because analysis.py funnels every failure into one
        # type. This is now the only place a Groq-shaped failure can reach the
        # user -- a malformed model response can no longer become a 500.
        current_app.logger.warning("Mood analysis failed for entry %s: %s", entry_id, e)
        return "Entry saved. Mood analysis unavailable right now.", 502

    conn = connect_db(current_app.config["DATABASE"])
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ? WHERE id = ?",
        (analysis.mood_label, analysis.mood_score, analysis.reflection, entry_id))

    conn.commit()
    conn.close()
    return (
        f"Based on the journal entry, the mood is predicted to be: {analysis.mood_label}, "
        f"with mood score: {analysis.mood_score}, and reflection: {analysis.reflection}"
    )
