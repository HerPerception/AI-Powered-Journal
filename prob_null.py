import sqlite3

conn = sqlite3.connect(":memory:")
c = conn.cursor()
c.execute("CREATE TABLE t (label TEXT)")

c.execute("INSERT INTO t VALUES (?)", ("",))     # the API answered: blank
c.execute("INSERT INTO t VALUES (?)", (None,))   # the API never answered
c.execute("INSERT INTO t VALUES (?)", ("calm",)) # the API answered: calm
conn.commit()

print("A) WHERE label = ''       ->", c.execute("SELECT count(*) FROM t WHERE label = ''").fetchone()[0])
print("B) WHERE label IS NULL    ->", c.execute("SELECT count(*) FROM t WHERE label IS NULL").fetchone()[0])
print("C) WHERE label != 'calm'  ->", c.execute("SELECT count(*) FROM t WHERE label != 'calm'").fetchone()[0])