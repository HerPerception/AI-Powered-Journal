"""Throwaway experiment: what does sqlite3 do with a missing file / missing table?

Run it, read the output, then delete it. It is not part of the app.
"""
import os
import sqlite3

print("1. journal.db exists BEFORE connect? ", os.path.exists("journal.db"))

conn = sqlite3.connect("journal.db")

print("2. journal.db exists AFTER connect?  ", os.path.exists("journal.db"),
      "(size:", os.path.getsize("journal.db"), "bytes)")

print("3. tables inside this database:      ",
      conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
print()

cur = conn.cursor()

# CASE 1 -- the table exists, but we never inserted anything.
cur.execute("CREATE TABLE IF NOT EXISTS demo (id INTEGER)")
print("4. CASE 1 (table exists, 0 rows) ->", cur.execute("SELECT * FROM demo").fetchall())

# CASE 2 -- the table was never created at all.
try:
    cur.execute("SELECT * FROM entries")
    print("5. CASE 2 (table missing)        -> returned", cur.fetchall())
except Exception as e:
    print("5. CASE 2 (table missing)        -> RAISED", type(e).__name__ + ":", e)

conn.close()
