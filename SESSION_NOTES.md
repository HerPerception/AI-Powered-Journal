# Session Notes — AI-Powered-Journal

**Last worked: 2026-09-21 (ran past midnight into the 22nd).** Read this whole file before touching anything.

> **The app works.** Both the success path and the failure path are correct and were
> observed working. Nothing is broken. Yesterday's notes were written while `app.py`
> was mid-refactor and are now mostly obsolete — this file replaces them.

---

## ✅ 0. State of the world right now

| Thing | Status |
|---|---|
| `app.py` | **works.** Both branches verified against a live server. |
| `journal.db` | exists, has 2 rows (one analyzed, one `NULL` from the deliberate 401 test) |
| `.env` | exists, holds the real (new) Groq key, **gitignored, never committed** |
| `venv/` | repaired — see §2. `python-dotenv` installed. |
| `venv/` in git | **still tracked in the index** — `git rm -r --cached venv` may not have been committed yet. **Check this first.** |

**Verify before doing anything else:**

```bash
git status              # is venv/ still showing as staged deletions?
venv/bin/python -c "import sys; print(sys.prefix)"   # must print .../AI-Powered-Journal/venv
```

---

## 🔐 1. Security — RESOLVED, and better than feared

- The exposed Groq key was **revoked** and replaced. ✅
- `.env` **is** in `.gitignore` (line 3) and `git check-ignore -v .env` confirms it. ✅
- **The key was never committed.** Verified by scanning every commit in the repo for
  key-shaped strings (`gsk_`, `sk-`) — zero hits. The "Securing API Key" commit
  (`08e140c`) removed exactly one line, `print(api_key)`; no literal key was ever in git.
  **No history rewrite needed.**
- Still open (cosmetic): `venv/` (1,469 files) and `__pycache__/*.pyc` are tracked.

---

## 🐛 2. The broken venv — and what it taught

`flask run` failed with `ModuleNotFoundError: No module named 'flask'` **even though
Flask was installed** at `venv/lib/python3.12/site-packages/flask/`.

**Cause:** `venv/pyvenv.cfg` was missing.

- A venv is a folder **plus a marker file** (`pyvenv.cfg`).
- Python looks for that marker beside its executable. Found → "I'm a venv, my packages
  are in `./lib/python3.12/site-packages`." Not found → "I'm the system Python" →
  `/usr/lib/python3/dist-packages` → no Flask.
- `venv/bin/python` is just a symlink to the system Python. **The marker is the only
  thing that makes it a venv.**
- Proof: `venv/bin/python -c "import sys; print(sys.prefix)"` printed **`/usr`**.

**Why it happened:** `venv/` is tracked in git, but `pyvenv.cfg` was *not* — `git status`
was clean, so an untracked deletion can't be shown there. Every tracked venv file was
restored; the one file that made it work was not.

**The lesson:** *a venv is disposable; `requirements.txt` is the durable artifact.*

**The fix that worked:**

```bash
git rm -r --cached venv              # untrack (keeps files on disk)
python3 -m venv --clear venv         # regenerates pyvenv.cfg
venv/bin/pip install -r requirements.txt
```

**Also learned:** `(venv)` in your shell prompt only means your **shell** knows where the
venv is. It says nothing about what your **interpreter** does. Activation is a `PATH`
convenience, not configuration.

---

## 🧱 3. SQL `NULL` — the concept of the day

`''` and `NULL` are **not** interchangeable for "no mood yet."

- `''` = *"the API answered, and the answer was blank."* (a known value)
- `NULL` = *"the API never answered."* (unknown)

**SQL has three truth values: TRUE, FALSE, UNKNOWN.** Comparing anything to `NULL` yields
UNKNOWN, and `WHERE` keeps only TRUE rows — so `NULL` rows **silently vanish** from
comparisons. Proven with `probe_null.py`:

| query | count | why |
|---|---|---|
| `WHERE label = ''` | 1 | matches only the blank row |
| `WHERE label IS NULL` | 1 | matches only the unknown row |
| `WHERE label != 'calm'` | **1** (not 2!) | the `NULL` row evaluates to UNKNOWN and is **dropped** |

That's why `= NULL` never works — always `IS NULL` / `IS NOT NULL`.

**Why this mattered for the design:** storing `''` for un-analyzed entries would make them
indistinguishable from genuinely-blank results, and

```sql
SELECT * FROM entries WHERE mood_label IS NULL
```

**could not exist.** That query is the retry queue. `None` in Python → `NULL` in SQLite.

---

## 🔨 4. What got built

### a) Error B — the three pre-API values

The `INSERT` runs before the API is called, so three names had no value yet. Fixed by
passing `None` inline:

```python
cursor.execute(
    "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)",
    (timestamp, user_entry, None, None, None))
```

### b) Error C — the double write became an `UPDATE`

The second `INSERT` produced a **duplicate row per submission** (observed: rows 2/3 and
4/5 shared the same timestamp — one submission, two rows). Fixed:

```python
entry_id = cursor.lastrowid      # immediately after the first execute, BEFORE conn.close()
...
cursor.execute(
    "UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ? WHERE id = ?",
    (mood_label, mood_score, reflection, entry_id))
```

**`cursor.lastrowid` is only readable until the connection closes.** Capture it before
line 50's `conn.close()`, or it's gone.

**`UPDATE` anatomy:** `UPDATE <table> SET <col>=?,... WHERE <which rows>`.
**⚠️ Omit the `WHERE` and you update EVERY row — silently, no undo.**

### c) The template — two separate bugs

The homepage 500'd with `TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'`
at `index.html` line 18 — inside the SVG block that had been **commented out** with
`<!-- -->` months ago.

> **HTML comments (`<!-- -->`) are for the *browser*. Jinja2 never sees them.** Jinja
> renders the template on the server *first*, so `{% %}` and `{{ }}` inside an HTML comment
> **still execute.** Jinja's own comment syntax is `{# ... #}`.

Fixed by deleting the block entirely, and adding `or ""` to the three display fields so a
`NULL` renders as nothing rather than the literal word `None`:

```jinja
{{ each_entry[3] or "" }}
```

**Storage layer says "unknown" (`None`); display layer shows nothing (`or ""`). Different
layers, different tools.**

### d) Status-code handling + network errors

```python
    try:
        response = requests.post(
            url,
            headers={...},
            json={...},
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        print(f"Groq request failed: {e}")
        return "Entry saved. Mood analysis unavailable right now.", 502

    if response.status_code != 200:
        print(f"Groq returned {response.status_code}: {response.text}")
        return "Entry saved. Mood analysis unavailable right now.", 502
```

Three failure shapes, all now handled:

| # | Failure | Where it surfaces |
|---|---|---|
| a | Groq replies with an error (`401`/`429`/`503`) | the `if` on `status_code` |
| b | Groq never replies (DNS, refused) | `requests.post` **raises** → the `except` |
| c | Connection hangs forever | `timeout=10` → raises `Timeout` → the `except` |

`requests.exceptions.RequestException` is the **parent** of every error `requests` raises,
so one `except` catches all of them.

**Two principles encoded here:**
1. **An error the user cannot act on should not be shown to them in detail.** The user gets
   a plain sentence; `print()` logs `401 invalid_api_key` for *you*.
2. **`500` says "I'm broken." `502` says "the thing behind me is broken."** The save worked
   — so `502`.

### e) Verified in production

- **Success path:** browser OK, `POST /entries 200`, row written with `mood_label='stressed'`,
  `mood_score=4`, reflection filled.
- **Failure path** (deliberately induced bad key): browser showed
  *"Entry saved. Mood analysis unavailable."*; terminal printed
  `Groq returned 401: {"error":{"message":"Invalid API Key",...}}`; server logged
  `"POST /entries HTTP/1.1" 502`; and the DB **still had the entry**, with `NULL` mood.

**The row survives every failure.** That was the whole design.

---

## 🧠 5. The design decision, restated (now with evidence)

**Save FIRST, then analyze.** `INSERT` (mood = `None`) → call API → `UPDATE` the same row.

Why not one `INSERT` at the end with everything known? Because everything between
`commit()` (line 49) and the `UPDATE` (line 85) can fail — network, DNS, timeout, bad key,
rate limit, malformed JSON, the process being killed. **Any of those and the writing is
gone forever.** Save-first means the entry is on disk before the network is touched.

Cost: one extra local SQLite write. Benefit: no user ever loses an entry.

---

## 🚧 6. START HERE TOMORROW — startup API key check

**Decision made: build the startup key validation first.**

Validate the key once at boot: hit Groq, and if the key is bad, **fail loudly at startup**
instead of discovering it one journal entry at a time. *Fail fast beats fail quietly.*

### ⚠️ The trap — this is the question to answer first

> **Where does the check go so it runs under BOTH `flask run` and `python app.py`?**

This is the **third time** this exact shape has appeared:

1. `connect_db()` inside `if __name__ == "__main__":` → skipped under `flask run` → no table
2. `.env` loading → turned out to be fine (verified from source)
3. Now: a startup key check → putting it in the `__main__` block means it **silently does
   not run under `flask run`** — a safety net with a hole exactly where you use it.

Note: `@app.before_first_request` was **removed in Flask 3.x** — that is not the answer.

Hint: what runs when a module is *imported*? You proved in `demo_import.py` that
`import` **executes the file top-to-bottom**. Where does `flask run`'s import land?

**Think about it before writing code.**

---

## 📋 7. The rest of the queue

| # | Item | Status |
|---|---|---|
| 1 | Security (key revoked, `.env` ignored) | ✅ done |
| 2 | Status code + timeout + network errors | ✅ done |
| 3 | Save-first ordering (INSERT → API → UPDATE) | ✅ done |
| 4 | Template `NULL` handling | ✅ done |
| 5 | Delete probe files | ⬜ **not done** |
| 6 | Commit `git rm -r --cached venv` if uncommitted | ⬜ check |
| 7 | Startup key check | ⬜ **next** |
| 8 | Sweep / retry for `NULL` rows | ⬜ after #7 |

### Files to delete (#5) — all throwaway, none are part of the app

```
probe_sqlite.py   probe_api.py   probe_none.py   probe_null.py (or prob_null.py)
check_key.py
show_db.py        ← keep only if you'll actually reuse it; decide on purpose
```

---

## 🔮 8. Open design questions (for later, not now)

1. **Retry needs state.** To cap retries ("try 3 times, then mark failed") the app must
   remember how many times it tried. That needs a new column (`retry_count` /
   `analysis_status`).
2. **Adding a column breaks the template.** `index.html` uses *positional* indices —
   `each_entry[2]`, `each_entry[3]`, `each_entry[5]`. Insert a column mid-schema and every
   index shifts by one, **silently**. Fix by looking up `sqlite3.Row` (access columns by
   name). Do this *before* adding columns, while there are only 2 rows to worry about.
3. **Failures are not all alike.** `429`/`503`/network = transient → retry. `401` = global
   config fault → retrying is pointless; *you* must fix the key. **Match the scope of the
   response to the scope of the failure.**
4. **The actual answer to "what if the key is bad":** it's an operator problem, not an
   entry problem. (a) make it **visible** to the operator (logs/alerting — a `print()` in a
   terminal you aren't watching is not visibility), and (b) keep a **recoverable backlog**.
   **The `NULL` rows already ARE that backlog** — fix the key, sweep, everything catches up.
5. `requirements.txt` is a full `pip freeze` including a whole Jupyter stack. It should be
   trimmed to the app's real dependencies.
6. `request.form["entry_text"]` raises `BadRequestKeyError` if the field is missing. No
   validation on the form at all.
7. `save_entry` has debug leftovers: `print(data)` (line 70) and the final `return` string.

---

## 🤖 9. On the model being probabilistic — observed, not asserted

The **same entry text** was submitted twice. The model returned:

| | mood_label | mood_score |
|---|---|---|
| first submission | `'content'` | 8 |
| second submission | `'motivated'` | 8 |

Same input, different label. There is no `f(text) → label` mapping. Both readings are
defensible. **Design accordingly:** never build logic that assumes a stable label for a
given text, and never treat a disagreement between runs as a bug.

---

## 🪞 10. The wrong prediction (worth remembering)

Mid-session I asserted, confidently, that `app.run()` does **not** load `.env` and that
`python app.py` would therefore fail to authenticate.

**I was wrong.** From the installed source:

```
flask/app.py:546   def run(self, host=None, port=None, debug=None, load_dotenv: bool = True, ...)
flask/app.py:623       if get_load_dotenv(load_dotenv):
flask/app.py:624           cli.load_dotenv()
```

`app.run()` loads `.env` and defaults to on.

**The lesson is not "the mentor was wrong." It is:**
- A confident-sounding claim is **not** evidence — including mine.
- When someone contradicts something you directly observed, **trust your observation** and
  ask for their evidence.
- The fix is mechanical: *show me the line of code, or run the experiment.*

**And the meta-lesson:** my *recon* claim ("nothing loads `.env`") was correct and observed.
My *follow-up* claim ("and `app.run()` wouldn't either") was invented and merely
plausible-sounding. **Those are different things and must be labelled differently.**

---

## 📝 11. Session closing ritual — 2026-09-21

**1. What felt most unclear and now makes sense?**
> "How to handle a problem with the API call so the whole program doesn't crash. It now
> makes sense, and I realised all I needed to do was think deeply — the answer was there
> all along."

**2. What broke, and what did the error teach you?**
> "The program crashing every time the API call threw an error. It taught me the importance
> of catching exceptions and checking status codes."

**3. Two sentences — what did you build?**
> "The try-except block that catches exceptions and checks the status code, as well as
> inserting and updating rows in the database."

**4. What would you do differently next session?**
> "I'll follow through more intentionally."

---

## 💬 12. Pick up here tomorrow

> "I'm back. Read SESSION_NOTES.md. I'm building the startup API key check.
> First question to settle: **where does it go so it runs under both `flask run` and
> `python app.py`?** — given that `if __name__ == '__main__':` is skipped by `flask run`."

**Also outstanding:** delete the probe files (#5), and check whether
`git rm -r --cached venv` was committed (#6).
