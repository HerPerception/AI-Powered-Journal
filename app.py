from datetime import datetime
from flask import Flask, render_template, request
import json
import requests
import os
import sqlite3

app = Flask(__name__)

def connect_db():
    conn = sqlite3.connect("journal.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            text TEXT,
            mood_label TEXT,
            mood_score INTEGER,
            reflection TEXT
        )
        """)
    conn.commit()
    return conn

@app.route("/")
def banana():
    # return "Hello from banana"

    conn = connect_db()   # ensure schema before serving anything, this should run even if I use 'flask run'
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM entries")
    entries = cursor.fetchall()
    conn.close()

    return render_template("index.html", entries=entries)

@app.route("/entries", methods=["POST"])
def save_entry():
    user_entry = request.form["entry_text"]
    if len(user_entry) == 0:
        return "No entry. Verify that an entry was made.", 400
    timestamp = str(datetime.now())
    conn = connect_db()   # ensure entry is saved so a failed API call does not cause a loss of the user entry.
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)", 
        (timestamp, user_entry, None, None, None))
    
    entry_id = cursor.lastrowid      # ← add this
    conn.commit()
    conn.close()
    api_key = os.environ.get("GROQ_API_KEY")
    model = "openai/gpt-oss-20b"
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = f"Read this entry {user_entry}, predict the mood in one word, give a mood score on the scale of 1-10, 10 represents very positive feelings, 1 represents very negative feelings, regardless of the specific mood word, and a two-sentence reflection. Return in correct JSON format, for example {{\"mood_label\": \"stressed\", \"mood_score\": 4, \"reflection\": \"...\"}}"
    try:
       response = requests.post(
            url,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={
                  "model": model,
                  "messages": [
                      {"role": "user", "content": prompt}
                  ],
                  "max_tokens": 1000
              },
              timeout=10
          )
    except requests.exceptions.RequestException as e:
          print(f"Groq request failed: {e}")
          return "Entry saved. Mood analysis unavailable right now.", 502


    if response.status_code != 200:
        print(f"Groq returned {response.status_code}: {response.text}")
        return "Entry saved. Mood analysis unavailable right now.", 502

    data = response.json()
    print(data)
    first_choice = data["choices"][0]
    model_text = first_choice["message"]["content"]
   
    formatted_text = json.loads(model_text)

    mood_label = formatted_text["mood_label"]
    mood_score = formatted_text["mood_score"]
    reflection = formatted_text["reflection"]
    conn = connect_db()   # ensure schema before serving anything, this should run even if I use 'flask run'.
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ? WHERE id = ?",
        (mood_label, mood_score, reflection, entry_id))

    conn.commit()
    conn.close()
    print(f"Based on the journal entry, the mood is predicted to be: {mood_label}, with mood score: {mood_score}, and reflection: {reflection}")
    return f"Based on the journal entry, the mood is predicted to be: {mood_label}, with mood score: {mood_score}, and reflection: {reflection}"

if __name__ == "__main__":
    connect_db()   # ensure schema before serving anything
    app.run(debug=True)
