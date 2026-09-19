"""Throwaway: what does Groq actually send back when the request is bad?

Run it, read the output, then delete it. It is not part of the app.
"""
import requests

url = "https://api.groq.com/openai/v1/chat/completions"

r = requests.post(
    url,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer deliberately-wrong-key",
    },
    json={
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 10,
    },
)

print("1. status_code:", r.status_code)
print("2. raw body   :", r.text[:300])
print()

try:
    body = r.json()
    print("3. r.json() SUCCEEDED ->", type(body).__name__, "with keys:", list(body.keys()))
except Exception as e:
    print("3. r.json() RAISED    ->", type(e).__name__ + ":", e)

print()
print("4. what does body['choices'] do?")
try:
    print("   ->", body["choices"])
except Exception as e:
    print("   -> RAISED", type(e).__name__ + ":", e)
