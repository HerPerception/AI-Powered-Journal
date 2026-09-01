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
    api_key = os.environ.get("GROQ_API_KEY")
    model = "qwen/qwen3.6-27b"
    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = f"Read this entry {user_entry}, predict the mood in one word, give a mood score on the scale of 1-10, and a two-sentence reflection. Return in JSON format, for example {{'mood_label': 'stressed', 'mood_score': 4, 'reflection': '...'}}"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
        }
    )
    data = response.json()
    print(data)
    first_choice = data["choices"][0]
    model_text = first_choice["message"]["content"]
    index = model_text.find("</think>")
    model_text = model_text[index+len("</think>"):]
    model_text = model_text.replace("```json", "")
    model_text = model_text.replace("```", "")
    formatted_text = json.loads(model_text)

    mood_label = formatted_text["mood_label"]
    mood_score = formatted_text["mood_score"]
    reflection = formatted_text["reflection"]

    print(f"Based on the journal entry, the mood is predicted to be: {mood_label}, with mood score: {mood_score}, and reflection: {reflection}"
)
    return f"Based on the journal entry, the mood is predicted to be: {mood_label}, with mood score: {mood_score}, and reflection: {reflection}"

if __name__ == "__main__":
    app.run(debug=True)