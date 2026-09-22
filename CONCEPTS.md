# Concepts — Quick Reference

Brief definitions of everything used in this project, tied to the file and line where
it appears. **For the long version — evidence, traps, reasoning — see `LEARNING_LOG.md`.**

Line numbers match `app.py` / `templates/index.html` as of 2026-09-22.

---

## A. Request lifecycle (Flask)

**Route / decorator**
`@app.route("/", methods=["POST"])` binds a URL + HTTP method to a function. Flask calls that
function when a matching request arrives. `app.py:26, 38`

**The lifecycle**
Browser → request → route → function runs → returns a value → Flask turns it into an HTTP
response → browser renders it. Nothing in a view function talks to the browser directly.

**`request.form["entry_text"]`**
Reads a submitted form field by the `name` attribute it was given. **Raises
`BadRequestKeyError` if the field is absent entirely** — which is *not* the same as empty.
`app.py:40`

**Two layers of validation**
`required` on the `<textarea>` is client-side — the browser blocks empty submits. It is
bypassable (curl, devtools). `len(user_entry) == 0` is server-side and is the real check.
Both are useful; only the server one is a guarantee. `app.py:41`, `index.html:18`

**`400 Bad Request`**
The status meaning "your input was wrong" — the user *can* fix this one, unlike a `502`.
`app.py:42`

**`if __name__ == "__main__":`**
Runs only when the file is executed **directly**. `flask run` **imports** the file instead,
so `__name__` is `"app"` and this block is **skipped**. Code that must always run cannot
live here. `app.py:103`

**`app.run(debug=True)`**
Starts Flask's development server. `debug=True` adds auto-reload on save and an interactive
traceback page. Development only — never production.

---

## B. Database (SQLite & SQL)

**`sqlite3.connect("journal.db")`**
Opens the database at that path, creating a **0-byte file** if it doesn't exist. That file is
a path, not yet a database — it holds nothing until a `CREATE TABLE` runs.

**`CREATE TABLE IF NOT EXISTS`**
Creates the table only if absent → safe to run on every request. **This** is what turns the
0-byte file into a real database. `app.py:13-22`

**Connection vs Cursor**
**Connection** = the pipe to the file (`.execute()`, `.commit()`, `.close()`).
**Cursor** = runs queries and holds rows (`.fetchall()`, `.fetchone()`, `.lastrowid`).
A Connection has **no** `fetchall()`. `connect_db()` returns a *Connection*.

**`?` placeholders**
Parameterized queries. The values travel separately from the SQL text, so a value can never
be interpreted as SQL. This is what prevents SQL injection. `app.py:47-48`

**`commit()`**
Makes a write durable and visible to **other connections**. Without it, a second connection
to the same file sees nothing. `app.py:51, 97`

**`cursor.lastrowid`**
The id of the row just inserted — how you know which row to `UPDATE`. **Readable only until
the connection closes.** Capture it before `conn.close()`. `app.py:50`

**`INSERT INTO ... VALUES`**
Adds a **new** row. `app.py:47-48`

**`UPDATE ... SET ... WHERE id = ?`**
Changes an **existing** row. Columns not named keep their old values.
**⚠️ Omit `WHERE` and every row in the table is overwritten — silently, no undo.**
`app.py:93-95`

**`SELECT * FROM entries`**
Reads all rows. Columns come back in **schema order** — which is what makes the template's
positional indices work. `app.py:32`

**`None` → `NULL`**
Python's `None` is stored as SQL `NULL`. Same value, two names. `app.py:48`

**Three-valued logic**
SQL comparisons return **TRUE, FALSE, or UNKNOWN**. Anything compared to `NULL` is
**UNKNOWN** — not FALSE. `WHERE` keeps only TRUE rows, so **`NULL` rows silently vanish**
from comparisons (no error, no warning).

**`IS NULL` vs `= NULL`**
`x = NULL` always evaluates to UNKNOWN, so it matches nothing, ever. Only `IS NULL` /
`IS NOT NULL` work.

**`NULL` ≠ `''`**
`NULL` = "unknown — never computed." `''` = "known, and the answer was blank."
Conflating them makes un-analyzed rows **indistinguishable** from genuinely-blank results,
so `WHERE mood_label IS NULL` — the retry queue — could not exist. `app.py:48`

**`INTEGER PRIMARY KEY AUTOINCREMENT`**
The `id` column: a unique, never-reused row identifier. `app.py:15`

**`fetchall()` / `fetchone()`**
All rows as a list of tuples / the next row as one tuple. `app.py:33`

---

## C. Talking to the model (HTTP + LLM)

**`requests.post(url, headers=, json=, timeout=)`**
Sends an HTTP POST with a JSON body. `app.py:58-69`

**`Authorization: Bearer <key>`**
How the API key is presented to Groq. `app.py:60`

**`os.environ.get("GROQ_API_KEY")`**
Reads the key from the environment. Returns `None` if unset — which produces
`Bearer None` and a `401` identical to a wrong key. `app.py:53`

**`.env` + `python-dotenv`**
`.env` holds the key; Flask calls `load_dotenv()` at startup **if python-dotenv is
installed**, so the key reaches `os.environ`. Verified in `flask/app.py:623-624`.

**`timeout=10`**
Gives up after 10 seconds and **raises**. Without it, a hung connection waits forever and
the user's browser spins. `app.py:68`

**Status codes**
`200` OK · `400` your input was wrong · `401` your key is bad · `429` rate limited ·
`500` *I* am broken · `502` *the thing behind me* is broken.

**`response.status_code`**
The **only** reliable success signal. `app.py:75`

**`response.json()`**
Parses the body. **Succeeds even on an error response**, because error bodies are valid
JSON (`{"error": {...}}`). **Never use it to detect failure.** `app.py:79`

**`data["choices"][0]`**
The trap: on failure the body has only an `error` key, so this raises `KeyError: 'choices'` —
an error that points at the wrong place entirely. `app.py:81`

**`except requests.exceptions.RequestException`**
`RequestException` is the **parent** of every error `requests` raises (`ConnectionError`,
`Timeout`, `HTTPError`, …), so one clause catches HTTP errors, network failures, and
timeouts together. `app.py:70-72`

**`return "...", 502`**
Returning two values sets both the body and the status code. A bare string defaults to
**200 OK** — the status you get by not choosing. `app.py:72, 77`

**Two scopes of failure**
`401` is a **global config fault** — only the operator can fix it; retrying is pointless.
`429`/`503`/network are **transient** — retrying helps. Match the response to the scope.
`app.py:75-77`

**Fast vs slow model output**
`openai/gpt-oss-20b` returns clean JSON in `content` and its thinking in a separate
`reasoning` field. Older models embedded thinking in `content` inside `</think>` tags —
which is what the `.replace()` calls below were patching. `app.py:84-85`

**`.replace("```json", "")` — band-aids**
Each line patches **one specific historical failure mode** and nothing else. They're dead
code for the current model. `app.py:84-85`

**`json.loads()`**
Parses the model's text into a Python dict. **The output is never guaranteed to match the
shape you asked for** — the model is probabilistic. `app.py:86`

---

## D. Template (Jinja + HTML)

**`{{ }}` / `{% %}`**
`{{ }}` outputs an expression. `{% %}` runs a statement (`for`, `if`). `index.html:8-15`

**`render_template("index.html", entries=entries)`**
Renders a Jinja template with the given variables. `app.py:36`

**Jinja runs on the server, first**
The browser never receives your template — only the finished HTML. Anything that must
happen before the browser sees the page happens in Jinja. `app.py:36`

**HTML comments don't hide Jinja**
`<!-- -->` is a message to the **browser**. Jinja renders first and ignores it, so
`{% %}` tags **inside** an HTML comment still execute. To comment out Jinja use `{# #}`.

**`or ""`**
`None or ""` → `""`. Converts a `NULL` mood into nothing, instead of Jinja printing the
literal word `None`. **Storage says "unknown"; display shows nothing.** `index.html:10-12`

**Positional indices are fragile**
`each_entry[2]` means "the 3rd column of `SELECT *`". Add or reorder a column and every
index shifts — **silently**, with no error. `sqlite3.Row` would let you use column names.
`index.html:10-12`

**`<textarea name="entry_text">`**
The `name` attribute is the dict key that arrives in `request.form`.

**`required`**
Client-side validation. Convenience, not security. `index.html:18`

---

## E. Python mechanics

**`import` RUNS the file**
Top-to-bottom, at the import line, side effects included. It does not "look up" a file.

**Indentation is ownership**
A line pushed right belongs to the line above it. An extra space is an `IndentationError`
before any code runs.

**Exceptions travel upward**
An uncaught exception exits your function, exits the route, and Flask turns it into a
`500`. `try`/`except` is a net that catches it earlier.

**f-strings**
`f"Bearer {api_key}"` interpolates a value into a string. `app.py:60`

**`str(datetime.now())`**
A timestamp as text. Set at line 43, so it records **submission** time, not analysis time.
`app.py:43`

---

## F. Environment & git

**A venv is a folder + `pyvenv.cfg`**
The marker file is the only thing that makes Python treat the folder as a venv. Without it,
`venv/bin/python` (a symlink to the system Python) silently uses the **system** packages —
producing `ModuleNotFoundError` for a package you can see on disk.

**Activation ≠ configuration**
`(venv)` in your shell prompt only means your **shell** knows the path. It says nothing
about which packages your **interpreter** uses.

**`requirements.txt` vs the venv**
`requirements.txt` is durable, tiny, and committable. The venv is disposable,
machine-specific, and must never be committed.

**`.gitignore` doesn't untrack**
It only stops **new** files. Already-tracked files keep being tracked until
`git rm -r --cached <path>` — which removes them from the index and **keeps them on disk**.

**`journal.db` is gitignored**
It's local data, recreated automatically by `connect_db()`. `.gitignore:1`

**The app's real dependencies**
`Flask` and `requests` (plus their transitive deps). `requirements.txt` is currently a full
`pip freeze` including an entire Jupyter stack — it should be trimmed.

---

## G. Design decisions (the "why", in one line each)

**Save first, analyze second**
`INSERT` with `NULL` mood → call the API → `UPDATE` the same row. Everything between the
first `commit()` and the `UPDATE` can fail — network, key, timeout, killed process. Saving
first means **the writing is on disk before the network is ever touched.** `app.py:41-97`

**`NULL` is the retry queue**
Rows whose analysis failed stay `NULL` and are findable with
`SELECT * FROM entries WHERE mood_label IS NULL`. Fix the cause, sweep, everything catches up.

**Log the detail, show a summary**
`print()` the `401`/`503` for yourself; show the user one plain sentence. An error they
can't act on shouldn't be shown to them in detail. `app.py:71, 76`

---

*Last updated 2026-09-22.*
*Not yet covered (doesn't exist yet): the startup API key check, and the `NULL`-row sweep.*
