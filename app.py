from flask import Flask, render_template, request
import json
import requests
import os

app = Flask(__name__)

@app.route("/")
def banana():
    # return "Hello from banana"
    return render_template("index.html")

@app.route("/entries", methods=["POST"])
def save_entry():
    user_entry = request.form["entry_text"]
    api_key = os.environ.get("GOOGLE_API_KEY")
    model = "gemini-3.7-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = f"Read this entry {user_entry}, predict the mood in one word, give a mood score on the scale of 1-10, and a two-sentence reflection. Return in JSON format, for example {{'mood_label': 'stressed', 'mood_score': 4, 'reflection': '...'}}"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            }
    )
    data = response.json()
    print(data)
    first_candidate = data["candidates"][0]
    model_text = first_candidate["content"]["parts"][0]["text"]
    model_text = model_text.replace("```json", "")
    model_text = model_text.replace("```", "")
    formatted_text = json.loads(model_text)

    return formatted_text["mood_label"]

if __name__ == "__main__":
    app.run(debug=True)