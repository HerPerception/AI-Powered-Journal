import os
from datetime import datetime

from flask import Flask, render_template, request

from analysis import AnalysisError, analyze_entry
from db import connect_db

app = Flask(__name__)


@app.route("/")
def banana():
    conn = connect_db()   # ensure schema before serving anything, this should run even if I use 'flask run'
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entries")
    entries = cursor.fetchall()
    conn.close()

    return render_template("index.html", entries=entries)


@app.route("/entries", methods=["POST"])
def save_entry():
    # `.get()` instead of `["entry_text"]`: an absent field is a bad request, not a
    # crash. `.strip()` closes the gap where "   " slipped past the old length check.
    user_entry = (request.form.get("entry_text") or "").strip()
    if not user_entry:
        return "No entry. Verify that an entry was made.", 400

    timestamp = str(datetime.now())
    conn = connect_db()   # save first: the writing is on disk before the network is touched
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)",
        (timestamp, user_entry, None, None, None))

    entry_id = cursor.lastrowid      # readable only until conn.close()
    conn.commit()
    conn.close()

    try:
        analysis = analyze_entry(user_entry, os.environ.get("GROQ_API_KEY"))
    except AnalysisError as e:
        # One except clause, because analysis.py funnels every failure into one
        # type. This is now the only place a Groq-shaped failure can reach the
        # user -- a malformed model response can no longer become a 500.
        print(f"Mood analysis failed for entry {entry_id}: {e}")
        return "Entry saved. Mood analysis unavailable right now.", 502

    conn = connect_db()
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


if __name__ == "__main__":
    connect_db()   # ensure schema before serving anything
    app.run(debug=True)
