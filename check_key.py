"""Throwaway: WHERE is the API key coming from? Never prints the key itself.

Run with:  venv/bin/python check_key.py
"""
import os

before = os.environ.get("GROQ_API_KEY")
print("1. in the shell env BEFORE loading .env :", "PRESENT" if before else "MISSING")

from dotenv import load_dotenv
load_dotenv()

after = os.environ.get("GROQ_API_KEY")
print("2. after load_dotenv()                  :", "PRESENT" if after else "MISSING")

print("3. length of the key                    :", len(after) if after else 0)
print("4. does it start with 'gsk_'?           :", after.startswith("gsk_") if after else "n/a")
print()
print("VERDICT:")
if before:
    print("  -> The SHELL is providing the key. .env may or may not be doing anything.")
elif after:
    print("  -> .env is providing the key. The shell has nothing.")
else:
    print("  -> NOTHING is providing the key. This is why Groq says 'Invalid API Key'.")
