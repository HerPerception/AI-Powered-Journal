# Session Notes — AI-Powered-Journal

**Last worked: 2026-09-30.** Read this whole file before touching anything.

> **⚠️ THE TESTS HAVE NOT BEEN RUN.**
> `tests/test_isolation.py` was written but never executed — the shell was unavailable
> when it landed. Everything it asserts is *believed*, not *observed*. **Run
> `python -m pytest tests/ -q` before trusting any of the auth work.** If it fails, the
> failure is real and the code is wrong; do not adjust the test to match.

---

## ✅ 0. State of the world right now

| Thing | Status |
|---|---|
| `app.py` | **app factory.** `create_app()` builds the app; `__main__` only starts a dev server. |
| `config.py` | **new.** All `os.environ` reads, one `load_dotenv()` at module top. |
| `db.py` | **new.** Schema versioning via `PRAGMA user_version`, now at **version 3**. |
| `journal.py` | **new.** Blueprint. Both routes `@login_required`, both queries `WHERE user_id = ?`. |
| `analysis.py` | **new.** The only module that talks to Groq. |
| `auth.py` | **new, untested.** Sessions, CSRF, signup/login/logout, `flask create-user`. |
| `templates/` | `base.html` (new), `index.html` (rewritten), `login.html`, `signup.html` |
| `tests/test_isolation.py` | **new, never executed.** |
| `journal.db` | schema v3. Contains the 3 original dev rows, all `analysis_status='ok'`. |
| `.env` | holds `SECRET_KEY` + `GROQ_API_KEY`. **Gitignored, never committed.** |
| `venv/` | untracked. |
| git | clean apart from `.gitignore`. Latest commit below. |

**Recent commits:**

```
090e6bc  Reflect rather than advise; close the mood vocabulary; add a static safety line
bf61f58  Extract an app factory; move configuration out of __main__
2367f60  Validate model output, add schema versioning and accounts
```

---

## 🔐 1. Security

- The exposed Groq key was **revoked and replaced** (2026-09-21). ✅
- `.env` is gitignored and was never committed — verified by scanning every commit for
  `gsk_` / `sk-` shaped strings. **No history rewrite needed.** ✅
- `SECRET_KEY` is **fatal if missing** — without it Flask cannot sign a session cookie, so
  nobody can log in. The app is not partially working; it is entirely not working.
- `GROQ_API_KEY` is **a warning, not fatal** — and the asymmetry is deliberate. See §5.

**Still open (cosmetic):** `venv/` and `__pycache__/*.pyc` are tracked in the index.

---

## 🏗️ 2. What got built — 2026-09-22 to 09-30

### a) The app factory — the third-occurrence pattern, resolved

`debug=True` sat inside `if __name__ == "__main__":`, so `flask run` and `python app.py`
produced **two different servers**:

```
python app.py          flask run
---------------        --------------
Debug mode: on         Debug mode: off
Restarting with stat   (absent)
Debugger is active!    (absent)
Debugger PIN: 115-...  (absent)
```

That was the **fourth** "must run however you launch this" bug — after `connect_db()`,
`.env` loading, and the queued startup key check. Rather than patch a fourth instance, the
factory **dissolves the category**: `flask run`, `gunicorn` and `python app.py` all call
`create_app()`, so anything inside it applies identically to all three.

**This answers the queued question from §6 of the previous notes.** The startup key check
goes in `create_app()` — the one function every launch path calls. It no longer has to be
put in a place that "also runs under `flask run`", because there is no longer a place that
doesn't.

### b) `analysis.py` — every failure collapses into one type

The old code caught only `requests.RequestException`, which is the **transport** layer's
exception. Everything that failed *after* the bytes arrived — JSON parsing, key lookup,
validation — escaped and became a `500`, even though the entry had already saved fine.

`AnalysisError` is now the single exception type for all of it. The caller catches exactly
one thing and cannot let a new failure mode through by not having heard of its class.

| # | Failure | Surface |
|---|---|---|
| a | Groq replies with an error | `status_code != 200` |
| b | Groq never replies | `except RequestException` |
| c | Connection hangs | `timeout=10` |
| d | **Bytes arrived, but they're wrong** | **new — parse + validate** |

(d) was the hole.

### c) Pydantic validation + schema versioning

`MoodAnalysis` is a `BaseModel` enforcing the shape rather than hoping for it: coerces
`"8"` → `8`, rejects `8.5`, rejects a score outside 1–10, rejects a missing key. Anything
that survives it is safe to write to the database.

**`@field_validator(mode="before")` is load-bearing** for `mood_label`. The default
(`"after"`) runs the `Literal` membership check *first*, so a model returning `" Stressed"`
— stray space, capital letter — would be rejected before anything tidied it up. Normalise,
*then* check membership.

### d) The closed mood vocabulary

Observed: the **same entry** across four runs gave labels `sad` / `stressed` / `frustrated`
/ `stressed`, while `mood_score` stayed at `3` / `4` / `4` / `4`.

**Why the score was stable and the label wasn't:** the prompt *defines* the score's scale
("1 to 10, where 10 is very positive"). It never defined the label's vocabulary, so the
model reached for a fresh synonym each time. **A defined range is an anchor; an undefined
one is an invitation.**

`MoodLabel` is now a `Literal` of 11 words, and **the prompt text and the Pydantic type are
both derived from it** (`get_args`), so they cannot drift apart.

> *Caveat: n=4. This is an observation, not a measurement. It says the variance was real
> and that the fix targets the right cause — not that it eliminates variance.*

### e) Reflect, don't advise — and where that failed

The prompt was rewritten to forbid advice, action-suggesting questions, diagnosis, persona
claims, and clinical language. **Banning a form does not remove an intent.** Advice came
back wearing a question mark:

> *"What small step could help you start moving forward?"*

That is advice. It has a `?` on the end. And run 1 — which predated **both** prompt edits —
*already* advised and offered presence, which tells you this is the **model's default
disposition**, not something the prompt caused. Prompt rules reduce it; they do not
guarantee it.

**Which is why the crisis line is static HTML, not a model instruction.** A prompt saying
"mention crisis resources if appropriate" is a *probability* — missable, arguable,
degradable by an unusual entry. A line that no model produces cannot fail. It now lives in
`base.html`, so **every page inherits it by extending the base** — there is nothing to
remember, and a page added later gets it for free.

---

## 🔒 3. Auth — the privacy model

Three sentences, and the second one is the dangerous one:

1. Every journal route has `@login_required`.
2. Every query touching entries carries `WHERE user_id = ?`.
3. Every state-changing request carries a CSRF token.

**A missing login check gives you a redirect you notice. A missing `WHERE` gives you
someone else's diary and no error at all.** That asymmetry is why (2) needs a test rather
than care.

**The test's precondition is the whole point.** `tests/test_isolation.py` asserts both rows
are *in the table*, owned by *two different users* — **before** asserting neither is
visible. Without that, `assert "AAAA" not in body` passes just as happily on an empty
database. **"Not visible" and "not there" are different claims and only one is privacy.**

**The suite needs no network.** `GROQ_API_KEY = None` → `analyze_entry` raises instantly →
but the row was already inserted *before* that call. The save-first design from 09-21 is
what makes this test hermetic: no mock, no recorded fixture, no request to Groq from CI.

### The four decisions in `auth.py`

| Decision | Why |
|---|---|
| `session.clear()` **before** storing the user id on login | Session fixation. Otherwise a cookie planted before you log in survives it. |
| One message for wrong password *and* unknown email | Distinguishing them is a free account-enumeration oracle. |
| Logout is **POST**, not GET | A GET logout fires from any `<img>` tag on any site. |
| Signup **closed by default** (`ALLOW_PUBLIC_SIGNUP`) | Opening the door to strangers is a deliberate env var, not something you get by forgetting to close it. |

**Not done, and on the list:** `check_password_hash` only runs when the user exists, so an
unknown email returns measurably faster than a wrong password. Fixing it means hashing a
dummy password on the miss path. It is a timing side channel.

**The invite path is `flask create-user <email>`.** Because signup is off, this is how
accounts get made. It also claims the three ownerless dev rows — but **only when it creates
the first user**, and deliberately *not* in the public signup route: unreferenced rows must
never be adopted by whoever happens to register next.

---

## 🧱 4. Schema — migration 2 and 3

**`PRAGMA user_version`** is SQLite's built-in schema version counter. Each migration is a
function taking version N−1 → N. **They are never edited once shipped** — editing an
applied migration means two databases claiming the same version have different shapes.

**`ALTER TABLE ADD COLUMN` appends**, so the original columns kept indices 0–5 and
`index.html`'s positional `each_entry[2]/[3]/[5]` survived. That is a property of the
migration, not of the template — a table rebuild would reorder them and the page would
silently show mood scores where reflections belong.

**That fragility is now retired.** `index.html` reads `entry["text"]`, `entry["mood_label"]`,
`entry["reflection"]` — by name, via `row_factory = sqlite3.Row` in `db.py`.

Migration 3 adds an index on `entries.user_id`, because every read now filters by it.

---

## 📋 5. The queue

| # | Item | Status |
|---|---|---|
| 1 | Security (key revoked, `.env` ignored) | ✅ |
| 2 | Status code + timeout + network errors | ✅ |
| 3 | Save-first ordering | ✅ |
| 4 | Template `NULL` handling | ✅ |
| 5 | **Run the isolation tests** | ⬜ **DO THIS FIRST** |
| 6 | App factory — the launch-path divergence | ✅ |
| 7 | Validate model output (Pydantic) | ✅ |
| 8 | Schema versioning | ✅ |
| 9 | Closed mood vocabulary | ✅ |
| 10 | Static safety line on every page | ✅ |
| 11 | Accounts, sessions, CSRF, per-user scoping | ✅ **written, unverified** |
| 12 | **Test `csrf_protect`** | ⬜ it is off in tests, so nothing covers it |
| 13 | Deferred/background analysis worker | ⬜ next real feature |
| 14 | Retry/sweep for `pending` rows, capped by `retry_count` | ⬜ |
| 15 | Delete probe files | ⬜ |
| 16 | Deploy (gunicorn) + WAL concurrency tuning | ⬜ |
| 17 | Login timing side channel | ⬜ |
| 18 | Password reset / email verification | ⬜ not started |

### Files to deal with (#15) — throwaway, none are part of the app

```
probe_sqlite.py  probe_api.py  probe_none.py  probe_null.py (or prob_null.py)
check_key.py     show_db.py    demo_import.py demo_name.py
```

**But look at what deleting them costs.** `LEARNING_LOG.md` cites these files **by name as the
proof** for §§1, 2, 7, 11, 13 and 18 — *"How I proved it (`probe_null.py`)"*. Delete them and
the log cites evidence that no longer exists, in a repo where the reader cannot check any of
it. The log would become a set of claims.

That is the same failure this project keeps hitting, one level up: **an assertion is not
evidence, and the remedy is a runnable artifact.**

**Better than deleting: move them to `experiments/` and commit them.** ~8 small files that
each demonstrate one concept, referenced from the log by relative path. They cost nothing,
they run in under a second, and they turn the log from "things the mentor said" into "things
you can re-run."

`show_db.py` is the one genuine exception — it was a convenience, keep it only if you'll
actually use it.

`__pycache__/` and the `.db`/`.db-wal`/`.db-shm` files stay gitignored. That part is right.

---

## 🔮 6. Open design questions

1. **`csrf_protect` is disabled in tests** (`CSRF_ENABLED = False`, named explicitly in
   `config.py` rather than silently patched). This means it is the **least-verified code in
   `auth.py`**. It needs its own test before signup is ever opened to the public.
2. **The worker doesn't exist yet.** `analysis_status` and `retry_count` are columns waiting
   for it. Today's flow is still synchronous: the request blocks on Groq.
3. **Failures are not alike.** `429`/`503`/network are transient → retry. `401` is a global
   config fault → retrying is pointless and would fire hundreds of calls that cannot help.
4. **Match the scope of the response to the scope of the failure.** A missing Groq key costs
   analysis, not entries — so the app boots and warns, rather than refusing to start.
   Refusing to boot would turn a degraded feature into a total outage.
5. `requirements.txt` was trimmed to real app deps; `requirements-dev.txt` carries `pytest`.
6. **`current_user()` opens a database connection**, and it is called by `login_required`,
   by the view, and by the template's nav. That's up to three queries per page load. Not
   fatal at this size; it is the obvious thing to cache per-request later.

---

## 🤖 7. On the model being probabilistic — the accumulated evidence

| Observation | Same input? | Result |
|---|---|---|
| 09-21 | yes | `'content'` / 8, then `'motivated'` / 8 |
| 09-30 | yes, ×4 | labels `sad`/`stressed`/`frustrated`/`stressed`; scores `3`/`4`/`4`/`4` |
| 09-30 | yes | `reasoning` field **survives** `response_format=json_object` |

There is no `f(text) → label` mapping. **Never build logic that assumes a stable label for
a given text, and never treat a disagreement between runs as a bug.**

---

## 🪞 8. The wrong predictions (worth remembering)

**2026-09-21 — the mentor, on `.env`.** Asserted confidently that `app.run()` does not load
`.env`. Wrong; verified from installed source. *The lesson is not "the mentor was wrong" —
it is that a confident-sounding claim is not evidence, including mine.*

**2026-09-30 — the mentor, on the shell prompt.** Read `✗` in the user's zsh prompt as
"last command exited non-zero" and stated it as fact. It was a **dirty-working-tree**
indicator, and the disproof was already in the paste being read. *The same error as the
first one: a plausible reading stated as an observation.*

**2026-09-30 — the user, on `reasoning`.** Predicted the `reasoning` field would vanish under
`response_format=json_object`. Settled empirically: `keys inside message : ['content',
'reasoning', 'role']`. **Only status code tells you a call failed; only dot-access tells you
what's in the envelope.**

---

## 💬 9. Pick up here tomorrow

> "I'm back. Read SESSION_NOTES.md. **First: run `python -m pytest tests/ -q`** — the auth
> work has never been executed. If it fails, the code is wrong, not the test.
>
> Then: the CSRF test (#12), then the background analysis worker (#13) — a poller that
> picks up `analysis_status='pending'` rows and caps retries with `retry_count`."

**Also outstanding:** delete the probe files (#15), and remove the dead
`probe_envelope.py` line from `.gitignore`.
