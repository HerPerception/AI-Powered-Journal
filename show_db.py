"""Show what's actually in journal.db. Throwaway dev tool.

Run with:  venv/bin/python show_db.py
"""
import sqlite3

conn = sqlite3.connect("journal.db")
cursor = conn.cursor()

count = cursor.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
print(f"--- {count} row(s) in entries ---\n")

cursor.execute("SELECT * FROM entries")
for row in cursor.fetchall():
    print(row)
    print()

conn.close()
