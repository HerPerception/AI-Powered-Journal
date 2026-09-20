# Session Notes — AI-Powered-Journal

**Last worked: 2026-09-20.** Read this whole file before touching anything.

---

## 🔴 0. DO THIS FIRST — security

Your live Groq API key was printed to the terminal and pasted into a chat session.
**It must be treated as compromised.**

1. Go to console.groq.com → API Keys → **revoke the old key**, create a new one.
2. Put the new key in `.env` (you already have a `.env` file).
3. **`.env` is NOT in `.gitignore`.** Your `.gitignore` currently contains only:

   ```
   journal.db
   venv
   ```

   Add `.env` to it. Then check whether it was ever committed:

   ```bash
   git ls-files | grep -i env
   ```

   If that prints anything, the key is in your git history and needs scrubbing.

The `print(api_key)` line that caused this has already been deleted from `app.py`. ✅

---

## ⚠️ 1. The current state of `app.py` — IT DOES NOT RUN

You are **mid-refactor**. The file is broken on purpose (half-finished). Do not panic.
Nothing is lost — the working version is in git:

```bash
git stash          # or: git checkout app.py   (to throw away the WIP)
```

Three concrete errors, in the order Python will hit them:

### Error A — line 41 has five spaces of indentation

```python
40    user_entry = request.form["entry_text"]
41     conn = connect_db()          # ← 5 spaces, one too many
42    cursor = conn.cursor()
```

Python requires consistent indentation within a block. This is an `IndentationError`
and it fires before any of your code runs.

### Error B — lines 43–45 use names that don't exist yet

```python
cursor.execute(
    "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)",
    (timestamp, user_entry, mood_label, mood_score, reflection))
```

`timestamp`, `mood_label`, `mood_score`, `reflection` are all defined **further down**
(lines 74–77). Python runs top-to-bottom, so at line 44 they are `NameError`s.

**This is the exact question you were about to answer when you had to leave:**

> What should those four names hold *before* the API has answered?
>
> - `timestamp` → `str(datetime.now())`
> - `mood_label`, `mood_score`, `reflection` → **`None`**

That's the answer you already discovered yourself in `probe_none.py` — `None` is the
value that means "no mood yet."

<details>
<summary>Spoiler: the exact edit (try it yourself first)</summary>

Move this line up to just after line 40, and add the three `None`s:

```python
user_entry = request.form["entry_text"]
timestamp = str(datetime.now())
mood_label = None
mood_score = None
reflection = None
conn = connect_db()
cursor = conn.cursor()
cursor.execute(
    "INSERT INTO entries (timestamp, text, mood_label, mood_score, reflection) VALUES (?, ?, ?, ?, ?)",
    (timestamp, user_entry, mood_label, mood_score, reflection))
conn.commit()
```

Then delete lines 77–85 (the old `timestamp = ...` and the whole second INSERT block).
</details>

### Error C — there are now TWO inserts

Line 43–45 inserts the entry. Lines 80–82 insert it **again**. Both fire.
One submitted entry → two rows.

**Lines 80–82 must become an `UPDATE`, not an `INSERT`** — same row, now with the mood
filled in. You need to know *which* row: after the first `execute`,
**`cursor.lastrowid`** holds the id of the row you just inserted. Capture it, then:

```sql
UPDATE entries SET mood_label = ?, mood_score = ?, reflection = ? WHERE id = ?
```

**This is the unfinished piece of the day's work.** If you get stuck, get the file
running first with the two-INSERT bug, then fix the UPDATE separately.

---

## 🧠 2. What you learned today, and the evidence for it

Everything below was *observed by you*, not told to you. The evidence is in your terminal
history and re-runnable via the probe files.

### `connect()` does not create a table — only `CREATE TABLE` does

From `probe_sqlite.py`, first run:

```
1. journal.db exists BEFORE connect?  False
2. journal.db exists AFTER connect?   True (size: 0 bytes)   ← 0 BYTES
3. tables inside this database:       []
4. CASE 1 (table exists, 0 rows) -> []
5. CASE 2 (table missing)        -> RAISED OperationalError: no such table: entries
```

- `sqlite3.connect("journal.db")` creates a **0-byte file**. It is a path, not a database.
- Only `CREATE TABLE` (plus `commit()`) makes it a real database file.

**The trap:** lines 3 and 4 print **identically** (`[]`) but mean opposite things —
"no such table" vs "table with zero rows". Python cannot tell you which you're in.
That's why CASE 2 had to be wrapped in `try/except` to reveal itself.

### `import` RUNS the file

From `demo_name.py` / `demo_import.py`:

```
$ python3 demo_name.py
demo_name.py  -> my __name__ is: __main__

$ python3 demo_import.py
demo_name.py  -> my __name__ is: demo_name     ← printed BY the import
demo_import.py -> my __name__ is: __main__
```

`import demo_name` does not "look up" the file. Python **executes it top-to-bottom**,
right there at the import line, then returns.

### `__name__ == "__main__"` — the guard

- Run a file **directly** → `__name__` is `"__main__"`
- A file is **imported** → `__name__` is the module name (the filename minus `.py`)

`if __name__ == "__main__":` means *"only do this if I was started on purpose, not
pulled in as a helper."* Without it, importing a file would fire its side effects —
including `app.run()` starting a server you never asked for.

### Indentation = ownership

A line pushed right belongs to the line above it. This is the whole reason the bug
below happened:

```python
if __name__ == "__main__":
    connect_db()          # ← INSIDE the if → skipped when the if is False
    app.run(debug=True)
```

### 🐛 The bug you found and fixed

`flask run` **imports** `app.py` instead of running it directly. So `__name__` was
`"app"`, not `"__main__"`, so the `if` block was skipped, so `connect_db()` never ran,
so the table never existed. Observed live:

```
File "/home/student/AI-Powered-Journal/app.py", line 32, in banana
    cursor.execute("SELECT * FROM entries")
sqlite3.OperationalError: no such table: entries
"GET / HTTP/1.1" 500
```

**The fix:** every route calls `connect_db()` itself, so it no longer depends on *how*
the app was launched. The duplicated `CREATE TABLE` inside `save_entry` was deleted —
the schema now lives in exactly one place. `flask run` and `python app.py` both work.

**After the fix:** `GET / → 200` and `POST /entries → 200`. The whole pipeline works.

### Connection vs Cursor

- **Connection** — the pipe to the file. Has `.execute()` and `.close()`. **No `.fetchall()`.**
- **Cursor** — runs queries and holds rows. Has `.execute()`, `.fetchall()`, `.fetchone()`.

`connect_db()` returns a **Connection**. Naming it `cursor` produced:

```
AttributeError: 'sqlite3.Connection' object has no attribute 'fetchall'
```

**Mental model: a Connection can run a statement but cannot hand you back rows.**

### The API's error response is *valid JSON* — this one matters

From `probe_api.py` (deliberately wrong key):

```
1. status_code: 401
2. raw body   : {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}
3. r.json() SUCCEEDED -> dict with keys: ['error']
4. body['choices'] -> RAISED KeyError: 'choices'
```

The error body parses perfectly. **`r.json()` will NOT catch a failed API call.**
The garbage flows through and blows up later at `data["choices"]` as a `KeyError` —
an error that points at the wrong place entirely.

**`response.status_code` is never read anywhere in `app.py`.** 401, 429, 500, 503 all
flow straight into `data["choices"]`.

### Jinja renders `None` as the literal text "None"

From `probe_none.py`:

```
None   -> 'mood_label: [None]'     ← the WORD "None" shown to the user
''     -> 'mood_label: []'
'calm' -> 'mood_label: [calm]'
```

So under the new save-first design, entries whose mood hasn't arrived yet would render
as `None` on the homepage. Fix in `templates/index.html`:

```jinja
{{ each_entry[3] or "" }}
```

`None or ""` → `""`. (You predicted "empty string" — Jinja does not do that for free.)

### The model's output shape changes when you change models

- An **older** model put its thinking *inside* `content`, wrapped in `</think>` tags —
  that's why the commented-out `model_text.find("</think>")` lines exist in `app.py`.
  You had to strip them before `json.loads` would work.
- **`openai/gpt-oss-20b`** puts thinking in a **separate field**:

  ```python
  'message': {
      'content':   '{"mood_label":"excited","mood_score":8,...}',   # clean JSON
      'reasoning': 'We need to parse the entry: "Hello world!!!..."' # the thinking
  }
  ```

Same prompt, same code — different model, different shape. Those `</think>` lines are
now dead code, and the `.replace("```json", "")` lines are a *bandaid for a different,
older failure*. Each bandaid patches one specific historical failure mode and nothing else.

---

## 📐 3. The design decision you made, and why

**The problem:** a user types a journal entry and hits Save. If the API call fails, the
entry existed only in the browser's textarea and in a Python variable. Both die.
**Their writing is lost forever.**

**Option A — save only when the API fails.** You rejected this correctly. Its guarantee
is *"the entry is saved, unless something actually went wrong"* — which is backwards.
The save-on-failure code does not run if the process is killed, the machine reboots, the
connection drops, or an unanticipated exception escapes.

**Option B — save FIRST, then analyze. ✅ CHOSEN.**

> "The entry is on disk before we ever touch the network."

1. `INSERT` the entry immediately, with `mood_label`/`mood_score`/`reflection` as `None`
2. Call the API
3. `UPDATE` that same row with the mood

**Cost:** one extra local SQLite write per request. **Benefit:** no user ever loses an entry.

**Consequence you must handle:** rows now exist with `NULL` mood values, so the template
must not render "None" (see the Jinja section above).

**Ordering note:** finish this (#3) *before* writing the status-code handling (#2).
Otherwise #2's failure path still loses the entry.

---

## 📋 4. The work queue

| # | Item | Status |
|---|---|---|
| 1 | Revoke exposed Groq key; `.env` into `.gitignore` | 🔴 **NOT DONE — see section 0** |
| 2 | `response.status_code` check before `.json()` | ⬜ not started |
| 3 | Save-first ordering (INSERT → API → UPDATE) | 🟡 **half-done, file is broken** |
| 4 | Template `NULL` handling (`or ""`) | ⬜ not started |
| 5 | Delete probe files + `journal.db.bak` | ⬜ not started |

### Detail on #2 — the status-code check

Goes at line 57-ish, **before** `data = response.json()`:

```python
if response.status_code != 200:
    ...
```

**What you know at that moment:** the body is valid JSON shaped
`{"error": {"message": "...", "type": "..."}}` — so the reason is readable via
`response.json()["error"]["message"]`.

**Classify, don't treat them all alike:**

| Status | Meaning | Who can fix it |
|---|---|---|
| 401 / 403 | **your** key is bad | you, not the user |
| 429 | rate limited, temporary | nobody — retry later |
| 500 / 503 | Groq is down, temporary | nobody |

**Principle: an error the user cannot act on should not be shown to them in detail.**
A journal writer doesn't need `invalid_api_key`. They need *"Saved — but mood analysis
is unavailable right now."* Log the detail for yourself; show them a sentence they
understand.

**What status do YOU return?** Currently Flask decides (500). The accurate one is
**502** — your app is a gateway and its upstream misbehaved. 500 says "I'm broken";
502 says "the thing behind me is broken." Choose deliberately.

**Two more things for the same edit:**
- `requests.post(...)` has **no `timeout=`**. With no timeout a hung connection blocks
  that request forever and the user's browser spins. Add one (~10s).
- `raise_for_status()` + `except requests.RequestException` catches **HTTP errors and
  network errors** (connection refused, DNS failure, timeout) in one place. An explicit
  `if` catches only the HTTP kind. Your call — but know what each one misses.

---

## 🗂️ 5. Files in this directory

| File | What it is |
|---|---|
| `app.py` | the app — **currently broken, mid-refactor** |
| `templates/index.html` | entry list + form |
| `probe_sqlite.py` | throwaway experiment (missing file / missing table) |
| `probe_api.py` | throwaway experiment (what a bad API call returns) |
| `probe_none.py` | throwaway experiment (Jinja + None) |
| `demo_name.py` / `demo_import.py` | throwaway experiment (`__name__`) |
| `journal.db` | the database — gitignored, recreated automatically |
| `journal.db.bak` | the old db, renamed during testing — **delete it** |
| `run` | *(nothing yet)* |

**All probe/demo files are throwaway.** Read them, re-run them if useful, then delete
(item #5 above). They are not part of the app.

**Database state:** `journal.db` currently exists (created during the `flask run` test)
and contains the `entries` table with **at least one test entry** from your "Hello
world!!!" submission. `journal.db.bak` is the pre-test copy.

---

## ❓ 6. Open questions to answer tomorrow

1. **What were those four names before the API answered?** (Error B above.) You were
   one step from answering this. Don't read the spoiler until you've tried.
2. What SQL verb updates an existing row, and how does it know *which* row?
3. Should `timestamp` still be set at line 77, or has its meaning changed now that the
   row is created earlier? (What does the timestamp now represent — submission time, or
   analysis time? Which do you want?)
4. If an entry is saved with `NULL` mood because the API failed — should there be a way
   to retry the analysis later? What would that need?
5. That form has no validation. What does `request.form["entry_text"]` do if the field
   is missing entirely? (It's not the same as an empty string.)
6. `index.html` still uses positional indices (`each_entry[2]`, `each_entry[3]`). What
   happens to those numbers if you add a column to the table? What would make them
   stable? (Look up `sqlite3.Row`.)

---

## 📝 7. Session closing ritual — still owed

You left before completing this. **Answer these first when you come back** — they're
what converts the session into retained knowledge:

1. What concept felt most unclear at the start and now makes sense?
2. What broke today, and what did the error teach you?
3. If you had to explain what you built today in two sentences, what would you say?
4. What would you do differently next session?

**What was understood:** `connect()` ≠ `CREATE TABLE`; no-table vs empty-table;
`import` runs a file; `__name__ == "__main__"`; indentation as ownership;
Connection vs Cursor; status codes and API error shape; Jinja and `None`;
why save-first beats save-on-failure.

**What was built:** the `flask run` bug was found *and fixed* — routes now call
`connect_db()`, the schema lives in one place, and both launch methods work.
The save-first refactor was started.

**What remains:** section 4, items 1–5. Plus the UPDATE that completes item 3.

---

## 💬 8. Pick up here tomorrow

> "I'm back. Read SESSION_NOTES.md. I was about to fix Error B in `app.py` —
> setting the four mood names to their pre-API values so the first INSERT can run.
> Let me try it first, then we'll finish the UPDATE."
