from flask import Flask, render_template, request
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
    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={...}
    )
    return user_entry

if __name__ == "__main__":
    app.run(debug=True)