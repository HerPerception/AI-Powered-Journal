# Learning Log — AI-Powered-Journal

**Cumulative. Never overwritten, only appended to.**
Covers the **2026-09-20** and **2026-09-21** sessions.

> **How this differs from `SESSION_NOTES.md`:**
> `SESSION_NOTES.md` = *where I am* (current state, next task). Rewritten each session.
> `LEARNING_LOG.md` = *what I know* (concepts + the evidence that proved them). Permanent.

Each entry has the same four parts:

- **What it means** — the mental model, in plain words
- **How I proved it** — the experiment or observation, not a claim I was told
- **The trap** — the specific way this bites
- **Where it lives** — where it shows up in my code

---

## Contents

**Python**
1. [`import` RUNS the file](#1-import-runs-the-file)
2. [`__name__ == "__main__"` — the guard](#2-__name__--__main__--the-guard)
3. [Indentation is ownership](#3-indentation-is-ownership)
4. [Exceptions travel upward; `try`/`except` is a net](#4-exceptions-travel-upward-tryexcept-is-a-net)
5. [A venv is a folder *plus* a marker file](#5-a-venv-is-a-folder-plus-a-marker-file)
6. [The venv is disposable; `requirements.txt` is durable](#6-the-venv-is-disposable-requirementstxt-is-durable)

**HTTP & APIs**
7. [Status codes are the only reliable success signal](#7-status-codes-are-the-only-reliable-success-signal)
8. [Three ways a network call fails](#8-three-ways-a-network-call-fails)
9. [An error the user can't act on shouldn't be shown to them](#9-an-error-the-user-cant-act-on-shouldnt-be-shown-to-them)
10. [500 vs 502 — be accurate about *who* is broken](#10-500-vs-502--be-accurate-about-who-is-broken)

**SQLite & SQL**
11. [`connect()` does not create a table — only `CREATE TABLE` does](#11-connect-does-not-create-a-table--only-create-table-does)
12. [Connection vs Cursor](#12-connection-vs-cursor)
13. [`NULL` is not `''` — SQL has three truth values](#13-null-is-not--sql-has-three-truth-values)
14. [`UPDATE` anatomy — and the missing-`WHERE` disaster](#14-update-anatomy--and-the-missing-where-disaster)
15. [`cursor.lastrowid` — and when it dies](#15-cursorlastrowid--and-when-it-dies)

**Flask & Jinja**
16. [The request lifecycle](#16-the-request-lifecycle)
17. [HTML comments are for the browser, not Jinja](#17-html-comments-are-for-the-browser-not-jinja)
18. [Jinja renders `None` as the literal word "None"](#18-jinja-renders-none-as-the-literal-word-none)
19. [`flask run` imports your file — it does not run it](#19-flask-run-imports-your-file--it-does-not-run-it)

**LLMs**
20. [The model is not a function](#20-the-model-is-not-a-function)
21. [The output shape changes when you change models](#21-the-output-shape-changes-when-you-change-models)

**Engineering practice**
22. [Match the scope of the response to the scope of the failure](#22-match-the-scope-of-the-response-to-the-scope-of-the-failure)
23. [A confident claim is not evidence](#23-a-confident-claim-is-not-evidence)
24. [Design decisions are only proven by failure](#24-design-decisions-are-only-proven-by-failure)

---

# Python

## 1. `import` RUNS the file

**What it means.** `import somemodule` does not "look up" a file. Python **executes it
top-to-bottom**, right there at the import line, then returns. Every side effect in that
file happens: prints fire, variables get created, servers start.

**How I proved it** (`demo_name.py` / `demo_import.py`):

```
$ python3 demo_name.py
demo_name.py  -> my __name__ is: __main__

$ python3 demo_import.py
demo_name.py  -> my __name__ is: demo_name     ← printed BY the import
demo_import.py -> my __name__ is: __main__
```

**The trap.** Importing a file to "just look at its functions" runs its startup code —
including anything that opens connections or starts servers.

**Where it lives.** This is why `app.py` has an `if __name__ == "__main__":` guard. It also
explains §19.

---

## 2. `__name__ == "__main__"` — the guard

**What it means.** Every module has a `__name__`.

- File run **directly** → `__name__` is `"__main__"`
- File **imported** → `__name__` is the module name (the filename minus `.py`)

So `if __name__ == "__main__":` means *"only do this if I was started on purpose, not pulled
in as a helper."*

**How I proved it.** The two-line experiment in §1.

**The trap.** Without the guard, importing a file fires its side effects — including
`app.run()` starting a server you never asked for.

**Where it lives.** `app.py` line 93. And for the *third* time this pattern is the open
question for the startup key check (see §19).

---

## 3. Indentation is ownership

**What it means.** A line pushed right **belongs to the line above it**. Indentation isn't
decoration in Python — it's the structure. Python requires consistent indentation inside a
block, and an extra space is a hard `IndentationError` before any of your code runs.

**How I proved it.** `app.py` line 41 originally had five spaces instead of four → the file
refused to run at all.

**The trap.** This is exactly how the `connect_db()` bug hid: the call was indented *inside*
the `if`, so it belonged to a branch that never fired.

**Where it lives.** Everywhere. But specifically: check indentation first whenever code
"does nothing" instead of erroring.

---

## 4. Exceptions travel upward; `try`/`except` is a net

**What it means.** An exception is a **value that travels up the call stack**. When
`requests.post()` raises, that value moves up — through `requests`, through your line, out
of your function, into Flask. Whatever it passes through, it flies past. Flask is where it
finally stops, and Flask's answer is `500 Internal Server Error`.

`try`/`except` is a net you hang under a region of code:

```python
try:
    ...this might raise...
except SomeError as e:
    ...and if it does, control lands HERE instead...
```

- `try:` — "run this; if it raises, don't let it escape"
- `except X as e:` — "if an `X` (or any **subclass** of `X`) comes out, catch it here and
  bind it to the name `e`"

Catching a **parent** class catches all its children. That's why
`except requests.exceptions.RequestException` handles `ConnectionError`, `Timeout`,
`HTTPError`, and `TooManyRedirects` in one clause.

**How I proved it.** Before the fix, a `401` from Groq escaped `save_entry` and produced
`KeyError: 'choices'` → `500`. After the fix, the same `401` was caught, logged, and turned
into a clean `502` with a readable message.

**The trap.** A `500` is often not a decision anyone made — it's just what happens when an
exception runs off the end of a view.

**Where it lives.** `app.py` lines 67–76.

---

## 5. A venv is a folder *plus* a marker file

**What it means.** A virtual environment is **not** just "a directory with packages in it."
It's a directory **plus `pyvenv.cfg`**, which sits at the top of `venv/` beside `bin/` and
`lib/`.

When Python starts, it looks for that marker file:

- **Found** → *"I'm a venv. My packages live in `./lib/python3.12/site-packages`."*
- **Not found** → *"I'm just the system Python."* → `/usr/lib/python3/dist-packages` →
  **your packages are invisible**

`venv/bin/python` is only a **symlink to the system Python**. The marker is the *only* thing
that makes it behave like a venv.

**How I proved it.**

```
$ flask run
ModuleNotFoundError: No module named 'flask'      ← but flask WAS on disk

$ venv/bin/python -c "import sys; print(sys.prefix)"
/usr                                              ← not the venv!
```

**The trap — two of them:**

1. **A venv is machine-specific, which is why it must never be committed.** Mine was tracked
   in git while `pyvenv.cfg` was not. Restoring the repo brought back 1,469 venv files and
   not the one file that makes it work. A partially-restored venv doesn't fail loudly — it
   silently falls back to system Python.
2. **`(venv)` in your shell prompt only means your *shell* knows where the venv is.** It
   says nothing about what your *interpreter* does. Activation just prepends `venv/bin` to
   your `PATH`. It is a convenience for *finding* the executable, not configuration.

**Where it lives.** Environment setup. Fix:

```bash
git rm -r --cached venv              # untrack, keeps files on disk
python3 -m venv --clear venv          # regenerates pyvenv.cfg
venv/bin/pip install -r requirements.txt
```

---

## 6. The venv is disposable; `requirements.txt` is durable

**What it means.** Destroying a venv loses nothing, because the **list** of what it needs
lives in a file that git tracks.

**How I proved it.** `python3 -m venv --clear venv` wiped ~100 installed packages in one
command and cost me nothing — `pip install -r requirements.txt` restored everything.

**The trap.** Committing the venv instead of `requirements.txt` gives you the *worst* of
both: a repo that's huge, machine-specific, and silently broken on restore.

**Where it lives.** `.gitignore` line 2 (`venv`). Note: **gitignore never untracks files
that are already tracked** — it only stops *new* ones. You have to `git rm --cached` them.

---

# HTTP & APIs

## 7. Status codes are the only reliable success signal

**What it means.** `response.status_code` tells you unambiguously whether the call worked.
Nothing else does.

**How I proved it** (`probe_api.py`, deliberately wrong key):

```
1. status_code: 401
2. raw body   : {"error":{"message":"Invalid API Key","type":"invalid_request_error",...}}
3. r.json() SUCCEEDED -> dict with keys: ['error']
4. body['choices'] -> RAISED KeyError: 'choices'
```

**The trap — this one is severe.** The error body is **perfectly valid JSON**. So
`r.json()` **succeeds on a failed call**, the garbage flows downstream, and it blows up later
at `data["choices"]` as a `KeyError` — an error that points at **the wrong place entirely**.

`r.json()` will never catch a failed API call. Only `status_code` will.

**Where it lives.** `app.py` line 67, *before* `response.json()` on line 69.

---

## 8. Three ways a network call fails

| # | Failure | Where it surfaces | Handle with |
|---|---|---|---|
| a | Server **replies with an error** (`401`/`429`/`503`) | `response.status_code != 200` | an `if` |
| b | Server **never replies** (DNS fails, connection refused) | `requests.post` **raises** | `except RequestException` |
| c | Connection opens, then **hangs forever** | nothing — it just waits | `timeout=` |

**How I proved it.** I fixed (a) first and thought I was done. Then: "what happens if Groq
never replies?" — with no `try`/`except`, `requests.post` raises and the `if` is never
reached. **The bug was only half-fixed**, and the half I hadn't fixed was exactly the case I
couldn't easily reproduce by hand.

**The trap.** You fix the failure you can reproduce. The failure you *can't* reproduce is
still there. (c) is worse than a `500`: with no timeout, the request never returns, the
browser spins forever, and the user gives up and re-submits.

**Where it lives.** `app.py` lines 55–76.

---

## 9. An error the user can't act on shouldn't be shown to them

**What it means.** Classify failures by **who can fix them**:

| Status | Meaning | Who can fix it |
|---|---|---|
| `401` / `403` | your API key is bad | **you** — never the user |
| `429` | rate limited | nobody; wait |
| `500` / `503` | upstream is down | nobody |

In every row the *user cannot act*. So they don't need `invalid_api_key` — they need a
sentence they understand.

**The principle.** **Log the detail for yourself; show the user a summary.**
`print(f"Groq returned {response.status_code}: {response.text}")` goes to your terminal;
`"Entry saved. Mood analysis unavailable right now."` goes to their screen.

**How I proved it.** Deliberately set a bad key. Browser showed the plain sentence; terminal
showed `Groq returned 401: {"error":{"message":"Invalid API Key",...}}`. Both audiences got
what they needed.

**Where it lives.** `app.py` lines 74 and 78.

---

## 10. `500` vs `502` — be accurate about *who* is broken

**What it means.**

- `500` says **"I am broken."**
- `502 Bad Gateway` says **"the server behind me is broken."**

The entry save worked perfectly. The thing behind you — Groq — misbehaved. So `502` is the
accurate status.

**How I proved it.** Server log after the fix:
`"POST /entries HTTP/1.1" 502 -`

**The trap.** `return "some string"` gives the browser **`200 OK`** — the default for
"you chose not to choose." If you want a status, you have to state it:
`return "...", 502`.

**Where it lives.** `app.py` lines 68 and 72.

---

# SQLite & SQL

## 11. `connect()` does not create a table — only `CREATE TABLE` does

**What it means.** `sqlite3.connect("journal.db")` creates a **0-byte file**. It is a *path*,
not a database. Only `CREATE TABLE` (plus `commit()`) makes it a real database.

**How I proved it** (`probe_sqlite.py`):

```
1. journal.db exists BEFORE connect?  False
2. journal.db exists AFTER connect?   True (size: 0 bytes)   ← 0 BYTES
3. tables inside this database:       []
4. CASE 1 (table exists, 0 rows) -> []
5. CASE 2 (table missing)        -> RAISED OperationalError: no such table: entries
```

**The trap.** Lines 4 and 5 print **identically** (`[]`) but mean opposite things — "no such
table" vs "table with zero rows." Python cannot tell you which you're in. That's why CASE 2
had to be wrapped in `try`/`except` to reveal itself.

**Where it lives.** `connect_db()` in `app.py`, which runs `CREATE TABLE IF NOT EXISTS` so
the schema exists no matter how the app was launched.

---

## 12. Connection vs Cursor

**What it means.**

| | Connection | Cursor |
|---|---|---|
| what it is | the pipe to the file | runs queries, holds rows |
| has `execute()` | ✅ | ✅ |
| has `fetchall()` / `fetchone()` | ❌ | ✅ |
| has `lastrowid` (after INSERT) | ❌ | ✅ |

Naming a **Connection** `cursor` produced:

```
AttributeError: 'sqlite3.Connection' object has no attribute 'fetchall'
```

**Mental model: a Connection can run a statement but cannot hand you back rows.**

**Where it lives.** `connect_db()` returns a *Connection*; every caller does
`cursor = conn.cursor()`.

---

## 13. `NULL` is not `''` — SQL has three truth values

**What it means.** This is the concept of the 2026-09-21 session.

- `''` = *"the API answered, and its answer was blank"* — a **known** value
- `NULL` = *"the API never answered"* — **unknown**

Everywhere else in programming a yes/no question has two answers. **SQL has three: TRUE,
FALSE, and UNKNOWN.** Comparing *anything* to `NULL` gives UNKNOWN — not FALSE.

And `WHERE` keeps a row only when the condition is **TRUE**. So `NULL` rows are silently
dropped from comparisons.

**How I proved it** (`probe_null.py`) — three rows in:

```python
c.execute("INSERT INTO t VALUES (?)", ("",))     # API answered: blank
c.execute("INSERT INTO t VALUES (?)", (None,))   # API never answered
c.execute("INSERT INTO t VALUES (?)", ("calm",)) # API answered: calm
```

```
A) WHERE label = ''       -> 1
B) WHERE label IS NULL    -> 1
C) WHERE label != 'calm'  -> 1      ← NOT 2!
```

**C is the lesson.** Three rows, one is `'calm'`, so intuitively two are "not calm." SQL
returned **1**. The `NULL` row evaluated to **UNKNOWN**, and `WHERE` discarded it — no error,
no warning. It just vanished.

**The trap.** Hence `= NULL` **never** works (`NULL = NULL` is UNKNOWN, not TRUE). You must
use `IS NULL` / `IS NOT NULL`.

**Why it mattered for the design.** Storing `''` for un-analyzed entries would make them
**indistinguishable** from entries the model genuinely returned blank for — and this query
**could not exist**:

```sql
SELECT * FROM entries WHERE mood_label IS NULL
```

That query is the **retry queue**. `None` in Python → `NULL` in SQLite. Same value, two names.

**Where it lives.** `app.py` line 46 — `(timestamp, user_entry, None, None, None)`.

---

## 14. `UPDATE` anatomy — and the missing-`WHERE` disaster

**What it means.**

```sql
UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ? WHERE id = ?
└──1───┘ └──2───┘                                              └──3───┘
```

1. **`UPDATE <table>`** — which table (same job `INSERT INTO` does)
2. **`SET col = value, col = value`** — which columns get new values.
   **Columns you don't mention keep their old values** — so `timestamp` and `text` are left
   exactly as written. *Your writing is never rewritten.*
3. **`WHERE <which rows>`** — the filter

**⚠️ THE TRAP.** **Omit `WHERE` and `UPDATE` changes EVERY ROW IN THE TABLE** — silently,
no confirmation, no undo. This is the single most dangerous thing in SQL. **Write the
`WHERE` before you write the `SET`.**

**How I proved it.** Replaced the duplicate `INSERT` with this `UPDATE`; one submission went
from producing **2 rows** to **1 row**, correctly filled.

**Where it lives.** `app.py` lines 83–85.

---

## 15. `cursor.lastrowid` — and when it dies

**What it means.** After `cursor.execute(...)` runs an `INSERT`, **`cursor.lastrowid`** holds
the id of the row just inserted. That's how you know *which* row to `UPDATE`.

**The trap — this is the whole reason it's a separate entry.**

> **`lastrowid` is only readable until the connection closes.** `conn.close()` destroys the
> cursor and takes `lastrowid` with it.

So it must be captured **immediately after the INSERT and BEFORE `conn.close()`**:

```python
cursor.execute("INSERT INTO entries ... VALUES (?, ?, ?, ?, ?)",
               (timestamp, user_entry, None, None, None))

entry_id = cursor.lastrowid      # ← HERE. Before commit/close.

conn.commit()
conn.close()
```

**Where it lives.** `app.py` line 48.

**Bonus observation:** the `UPDATE` at line 83 runs on a *second* connection opened at line
81, and it can see the row inserted by the first one. That works **because of `commit()`** —
commit is what makes a write durable and visible to other connections.

---

# Flask & Jinja

## 16. The request lifecycle

**What it means.** The path a form submission takes:

```
Browser
  │  POST /entries  (form data: entry_text=...)
  ▼
Flask router ──► matches @app.route("/entries", methods=["POST"])
  │
  ▼
save_entry()
  ├─ request.form["entry_text"]        read the form field
  ├─ INSERT ... (None, None, None)     the entry is now SAFE ON DISK
  ├─ requests.post(...)  ──► Groq      the part that can fail
  ├─ UPDATE ... WHERE id = ?           same row, now complete
  └─ return
  │
  ▼
Browser gets the response
```

**Where it lives.** `app.py`. And the **save-first ordering** is a design decision that came
out of this: see §24.

---

## 17. HTML comments are for the browser, not Jinja

**What it means.** `<!-- -->` is a message to the **browser**. But your template is never
sent to the browser as-is — **Jinja2 renders it on the server first**, and Jinja has no idea
what an HTML comment is. To Jinja, `<!-- {% for ... %} -->` is just text with a tag inside
it, and **tags get executed**.

Jinja's own comment syntax is:

```jinja
{# this is invisible to Jinja #}
```

**How I proved it.** The homepage 500'd with:

```
File "templates/index.html", line 18
    <circle cx="{{ loop.index0 * 40 }}" cy="{{ 200 - (each_entry[4] * 20)}}" r="5" />
TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
```

Line 18 was **inside a commented-out `<svg>` block** that had supposedly been "removed"
months earlier. It had never been removed — only wrapped in `<!-- -->`, which Jinja ignored.

**The trap.** `<!-- -->` comments out code for the *browser*. It does **not** comment out
Jinja. Deleting the block is the cleanest fix; `{# #}` is the correct syntax if you must
keep it.

**Where it lives.** `templates/index.html`.

---

## 18. Jinja renders `None` as the literal word "None"

**What it means.** `None` does not render as empty. It renders as the four characters
`None`.

**How I proved it** (`probe_none.py`):

```
None   -> 'mood_label: [None]'     ← the WORD "None" shown to the user
''     -> 'mood_label: []'
'calm' -> 'mood_label: [calm]'
```

**The trap.** Under the save-first design, entries whose mood hasn't arrived render as
`None` on the homepage. **Storage layer says "unknown"; the display layer must show nothing.**

Fix:

```jinja
{{ each_entry[3] or "" }}
```

`None or ""` → `""`.

**Where it lives.** `templates/index.html` lines 10–12.

**The general principle:** storage and display are **different layers**. `None` is correct in
the database; `or ""` is correct in the template. Don't let one layer's vocabulary leak into
the other.

---

## 19. `flask run` **imports** your file — it does not run it

**What it means.** `flask run` imports `app.py` as a module, so `__name__` is `"app"`, **not**
`"__main__"`.

**How I proved it.** The first big bug:

```python
if __name__ == "__main__":
    connect_db()          # ← INSIDE the if → skipped when the if is False
    app.run(debug=True)
```

Observed live:

```
File "app.py", line 32, in banana
    cursor.execute("SELECT * FROM entries")
sqlite3.OperationalError: no such table: entries
"GET / HTTP/1.1" 500
```

**The trap.** Any code that must run *regardless of how the app was launched* cannot live in
the `__main__` block. Putting it there gives you a safety net with a hole exactly where you
use it most.

**The fix, and the pattern to reuse:** move the work into the code path that always runs —
routes call `connect_db()` themselves.

**Where it lives.** This pattern has now appeared **three times**:

| # | Thing that must always run | Outcome |
|---|---|---|
| 1 | `connect_db()` | ✅ fixed by calling it in every route |
| 2 | `.env` loading | ✅ turned out fine — `app.run()` does load it (verified in source) |
| 3 | startup API key check | ⬜ **open question** |

---

# LLMs

## 20. The model is not a function

**What it means.** There is no `f(text) → label` mapping. The same input can produce
different outputs. **Never treat an LLM call as deterministic.**

**How I proved it.** The **exact same entry text** was submitted twice:

| | mood_label | mood_score |
|---|---|---|
| first submission | `'content'` | 8 |
| second submission | `'motivated'` | 8 |

Same input, different label, two minutes apart. Both readings are defensible.

**The trap.** Don't build logic that assumes a stable label for given text. Don't treat a
disagreement between runs as a bug. Don't let a probabilistic output into a deterministic
code path without validating it first.

**Where it lives.** `app.py` line 78 — `formatted_text["mood_label"]`. If the model returns
JSON without that key, you get a `KeyError`. **The output is never guaranteed to match the
shape you asked for.**

---

## 21. The output shape changes when you change models

**What it means.** Same prompt, same code — different model, different response shape.

- An **older** model put its thinking *inside* `content`, wrapped in `</think>` tags → you had
  to strip them before `json.loads()` would work.
- **`openai/gpt-oss-20b`** puts thinking in a **separate field**:

```python
'message': {
    'content':   '{"mood_label":"excited","mood_score":8,...}',   # clean JSON
    'reasoning': 'We need to parse the entry: "Hello world!!!..."' # the thinking
}
```

**The trap — band-aids.** Look at `app.py` lines 74–75:

```python
model_text = model_text.replace("```json", "")
model_text = model_text.replace("```", "")
```

Each line patches **one specific historical failure mode** and nothing else. They're dead
code for the current model. Every band-aid like this is a bet that the model won't fail a
*different* way tomorrow.

**Where it lives.** `app.py` lines 74–75.

---

# Engineering practice

## 22. Match the scope of the response to the scope of the failure

**What it means.** Failures have **scope**, and the response must match it.

| Failure | Scope | Who can fix it | Correct response |
|---|---|---|---|
| `429` / `503` | one request | nobody — time | retry *that entry* later |
| network blip | one request | nobody — time | retry *that entry* later |
| **`401` bad key** | **the whole app** | **the operator** | **fix config, then sweep** |

**The trap.** Retrying a per-entry loop against a dead key is a **category error** — it
treats a *global* fault as if it were *local*. It would fire 500 pointless API calls and
still fix nothing, because **retrying is not an action that can change a key.**

**The answer to "what if the key is bad":** it's an operator problem, not an entry problem.
Two halves:

1. **Visibility** — the operator must *find out*. A `print()` in a terminal you aren't
   watching is not visibility.
2. **A recoverable backlog** — nothing may be lost while it's broken.

**And the payoff:** the `NULL` rows **already are that backlog**. Fix the key → sweep →
everything catches up. **This only works because of two earlier decisions: save before the
API call, and store `None` instead of `''`.** Had either been different, the backlog would be
unrecoverable and no sweep could exist.

**Not yet built:** the startup key check, and the sweep.

---

## 23. A confident claim is not evidence

**What it means.** This is the most transferable lesson of the 2026-09-21 session, and it
came from the mentor being wrong.

Mid-session, the mentor asserted confidently that `app.run()` does **not** load `.env`, and
that `python app.py` would therefore fail to authenticate. **That was wrong.** From the
installed source:

```
flask/app.py:546   def run(self, host=None, port=None, debug=None, load_dotenv: bool = True, ...)
flask/app.py:623       if get_load_dotenv(load_dotenv):
flask/app.py:624           cli.load_dotenv()
```

`app.run()` loads `.env`, and defaults to on.

**The lesson — not "the mentor was wrong," but:**

- **A confident-sounding claim is not evidence** — including from someone who sounds like an
  authority.
- **When someone contradicts something you directly observed, trust your observation** and
  ask them for their evidence.
- The remedy is mechanical: **show me the line of code, or run the experiment.**

**The finer point.** The mentor's *recon* claim ("nothing loads `.env`") was correct and
observed. The *follow-up* claim ("and `app.run()` wouldn't either") was invented and merely
plausible-sounding. **Those are different things and must be labelled differently.**

---

## 24. Design decisions are only proven by failure

**What it means.** The save-first design was a *reasoned* choice on 2026-09-20. It became a
*proven* one on 2026-09-21, when both branches were exercised against a live server.

**The design:** `INSERT` (mood = `None`) → call API → `UPDATE` the same row.

**Why not one `INSERT` at the end, with everything known?** Because everything between the
first `commit()` (line 49) and the `UPDATE` (line 85) can fail — network, DNS, timeout, bad
key, rate limit, malformed JSON, **the process being killed**. Any of those and the writing
is gone forever.

**How I proved it.**

| | row 1 (success) | row 2 (deliberate 401) |
|---|---|---|
| entry text | saved ✅ | saved ✅ |
| `mood_label` | `'stressed'` | **`None`** |
| `mood_score` | `4` | **`None`** |
| reflection | filled | **`None`** |

Both branches, one table. **The row survives every failure.**

**Cost:** one extra local SQLite write per request.
**Benefit:** no user ever loses an entry.

**The trap.** `save-on-failure` (the rejected alternative) has a backwards guarantee: *"the
entry is saved, unless something actually went wrong"* — and its save code does not run if
the process is killed, the machine reboots, the connection drops, or an unanticipated
exception escapes.

**Where it lives.** `app.py` lines 41–50 (insert), 55–76 (the fragile part), 81–87 (update).

---

*Last updated: 2026-09-21.*
*Next concepts to append: the startup key check, and the `NULL`-row sweep.*
