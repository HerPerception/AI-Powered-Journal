# Concepts — Quick Reference

Brief definitions of everything used in this project, tied to the file where it appears.
**For the long version — evidence, traps, reasoning — see `LEARNING_LOG.md`.**

File references are by **module**, not line number. Line numbers drifted every session and
made this file rot; module names survive refactors.

---

## A. Request lifecycle (Flask)

**Route / decorator**
`@bp.route("/", methods=["GET"])` binds a URL + HTTP method to a function. `journal.py`

**The lifecycle**
Browser → request → `before_request` hooks → route → function runs → returns a value → Flask
turns it into an HTTP response → browser renders it. Nothing in a view talks to the browser
directly.

**Blueprint**
A named group of routes. `bp = Blueprint("journal", __name__)`. The name becomes the
endpoint prefix: `url_for("journal.index")`. Lets routes live in their own module instead of
all piling into `app.py`. `journal.py`, `auth.py`

**App factory**
`create_app()` builds and returns the app, instead of a module-level `app = Flask(__name__)`.
Every launch path — `flask run`, `gunicorn`, `python app.py` — calls it, so configuration
inside it applies identically to all three. `app.py`

**`before_request`**
A function that runs before *every* request, registered once on the app. Used here for CSRF.
A per-route obligation is an obligation that gets forgotten; this one applies to routes that
do not exist yet. `app.py`

**`context_processor`**
Injects values into every template's context, so each view doesn't have to pass them.
`csrf_token` and `current_user` are exposed this way. `app.py`

**`if __name__ == "__main__":`**
Runs only when the file is executed **directly**. `flask run` **imports** the file instead,
so `__name__` is `"app"` and this block is **skipped**. `app.py` — now contains nothing but
"start a dev server on this machine", which is the only thing that legitimately differs
between launch paths.

**`app.run(debug=True)`**
Dev server. `debug=True` adds auto-reload and an interactive traceback page. The Werkzeug
debugger console is **remote code execution**, guarded only by a PIN printed to a terminal —
so debug defaults to OFF and must be opted into. Never production.

**`request.form.get("entry_text")`**
Reads a submitted field by its `name` attribute. **`.get()` not `["entry_text"]`** — the
subscript form raises `BadRequestKeyError` when the field is absent, turning a bad request
into a crash. `journal.py`, `auth.py`

**Two layers of validation**
`required` on the `<textarea>` is client-side — bypassable with curl. The server-side check
is the real one. Both are useful; only the server one is a guarantee.

**Status codes**
`200` OK · `302` redirect · `400` your input was wrong · `401` your key is bad · `403`
forbidden · `429` rate limited · `500` *I* am broken · `502` *the thing behind me* is broken.

---

## B. Database (SQLite & SQL)

**`sqlite3.connect("journal.db")`**
Opens the database at that path, creating a **0-byte file** if it doesn't exist. That file is
a path, not yet a database.

**`row_factory = sqlite3.Row`**
Makes rows readable by **column name** as well as position. This is what retired the
`each_entry[2]` fragility. `db.py`

**`PRAGMA user_version`**
SQLite's built-in schema version counter. `migrate()` reads it, applies any migration
numbered above it, and writes the new version. `db.py`

**Migrations are append-only**
Each migration takes version N−1 → N. **Never edit one that has shipped** — editing an
applied migration means two databases claiming the same version have different shapes. If
it's wrong, add a new one that corrects it. `db.py`

**`ALTER TABLE ADD COLUMN` appends**
New columns go on the end, so existing column *order* is preserved. Positional indices
survive — which is why `index.html`'s old `each_entry[2]/[3]/[5]` kept working through
migration 2. A table rebuild would reorder and break it silently. `db.py`

**`PRAGMA journal_mode = WAL`**
Lets readers proceed alongside one writer. Without it, gunicorn workers plus a background
worker on the same file start returning "database is locked". Paired with `timeout=5.0` so a
blocked writer waits rather than failing. `db.py`

**`?` placeholders**
Parameterized queries. Values travel separately from the SQL text, so a value can never be
interpreted as SQL. This is what prevents SQL injection.

**`commit()`**
Makes a write durable and visible to **other connections**.

**`cursor.lastrowid`**
The id of the row just inserted. **Readable only until the connection closes.** Capture it
before `conn.close()`. `journal.py`

**`UPDATE ... SET ... WHERE id = ? AND user_id = ?`**
The `user_id` clause is redundant today — the id came from our own `INSERT` one function
above. It is there because "provably mine" is a property of the *current code*, not of the
statement. If `entry_id` ever arrives from a form field, the version without it is already a
breach and this version is already correct. `journal.py`

**⚠️ `UPDATE` without `WHERE` overwrites every row.** Silently, no undo.

**`None` → `NULL`**
Python's `None` is stored as SQL `NULL`. Same value, two names.

**Three-valued logic**
SQL comparisons return **TRUE, FALSE, or UNKNOWN**. Anything compared to `NULL` is
**UNKNOWN**, and `WHERE` keeps only TRUE rows — so `NULL` rows **silently vanish** from
comparisons.

**`IS NULL` vs `= NULL`**
`x = NULL` is always UNKNOWN, so it matches nothing, ever.

**`NULL` ≠ `''`**
`NULL` = "unknown — never computed." `''` = "known, and the answer was blank." Conflating
them kills `WHERE mood_label IS NULL` — which is the retry queue.

**Index on `entries.user_id`**
Every read now filters by owner. Without the index that's a full table scan per page load.
Migration 3. `db.py`

---

## C. Talking to the model (HTTP + LLM)

**`requests.post(url, headers=, json=, timeout=)`**
HTTP POST with a JSON body. `analysis.py`

**`Authorization: Bearer <key>`**
How the API key is presented. A missing key produces `Bearer None` → `401` **identical to a
wrong key** — which is why a missing dependency can masquerade as a bad credential.

**`timeout=10`**
Gives up after 10 seconds and **raises**. Without it a hung connection waits forever and the
browser spins.

**`response.status_code`**
The **only** reliable success signal.

**`response.json()`**
Parses the body. **Succeeds even on an error response**, because error bodies are valid JSON
(`{"error": {...}}`). Never use it to detect failure.

**`except requests.exceptions.RequestException`**
The **parent** of every error `requests` raises, so one clause catches HTTP errors, network
failures, and timeouts. But it is the **transport** layer's exception — it catches nothing
that happens *after* the bytes arrive. `analysis.py`

**`AnalysisError`**
The single exception type every failure funnels into: transport, bad status, unexpected
envelope, unparseable content, and content that parses but is wrong. The caller catches
exactly one thing and cannot accidentally let a new failure mode through. `analysis.py`

**`response_format={"type": "json_object"}`**
Groq's JSON mode. **It constrains the content, not the envelope** — the response is still a
full chat-completion object with `choices[0].message`, and the model's thinking still arrives
in the sibling `reasoning` field. `analysis.py`

**`message.content` vs `message.reasoning`**
Sibling fields. `content` holds the JSON; `reasoning` holds the thinking. Older models
embedded thinking *inside* `content` in `</think>` tags, which is what the old `.replace()`
band-aids were patching. Those are dead code for the current model.

**`_extract_json_object()`**
Finds the outermost `{` … `}` in whatever came back, so prose before or after the object, or
markdown fences around it, all survive. It looks for the **structure** instead of patching a
specific string. Still raises if there is no object at all — that case is something to
report, not paper over. `analysis.py`

**`.replace("```json", "")` — band-aids**
Each patches **one specific historical failure mode**. Every band-aid is a bet the model
won't fail a different way tomorrow.

---

## D. Validating model output (Pydantic)

**`BaseModel`**
Declares the shape you require and **enforces** it: coerces `"8"` → `8`, rejects `8.5`,
rejects a missing key, rejects an empty string. Anything that survives is safe to store.
`analysis.py`

**`Field(ge=, le=, min_length=, max_length=)`**
Numeric and length bounds, checked by the model rather than by hand-written `if`s.

**`ValidationError`**
Raised when the data doesn't match. Caught and re-raised as `AnalysisError`, so the caller
still only catches one type.

**`model_validate_json()`**
Parse-and-validate in one step, from a string.

**`@field_validator(mode="before")`**
Runs **before** the type's own checks. Load-bearing for `mood_label`: the default `"after"`
mode runs the `Literal` membership test *first*, so `" Stressed"` — stray space, capital —
would be rejected before anything tidied it up. **Normalise, then check membership.**
`analysis.py`

**`Literal[...]` + `get_args()`**
A closed set of allowed values, and the tuple of those values at runtime, so the prompt text
and the validator are **derived from one definition** and cannot drift apart. `analysis.py`

---

## E. Accounts & sessions

**Session cookie**
Client-held and **signed, not encrypted**. It is a claim about who you are, not proof. Never
put anything in it you'd be unhappy to see forged. `auth.py`

**`session.clear()` before storing the user id on login**
**Session fixation.** Without it, an attacker who plants a session cookie in your browser
before you log in keeps the same session id after you log in — and therefore keeps your
logged-in session. `auth.py`

**`current_user()`**
Looks the user up from the database on every call rather than trusting a copy in the session.
Returns `None` when logged out. `auth.py`

**`@login_required`**
Decorator that redirects to the login page when `current_user()` is `None`. The decorator
must run **before** the handler, not merely produce a redirect after it — otherwise the
handler saves the data and then redirects. `auth.py`, `journal.py`

**`generate_password_hash` / `check_password_hash`**
Werkzeug's password hashing. **Never store a password.** Store a hash; compare hashes.

**`sqlite3.IntegrityError` on a `UNIQUE` column**
Checking "does this email exist?" and *then* inserting is a race — two simultaneous signups
both pass the check. Let the `UNIQUE` constraint enforce it and catch the failure. `auth.py`

**One message for both login failures**
Wrong password and unknown email produce the same reply. Distinguishing them is a free
account-enumeration oracle. `auth.py`

**CSRF**
A per-session token in a hidden form field, checked against the session on every
state-changing request. Without it, a third-party page can submit your forms as you. `auth.py`

**`secrets.compare_digest()`**
**Constant-time** comparison. `==` short-circuits on the first differing byte, leaking the
token one byte at a time to anyone who can measure response time. `auth.py`

**Logout is POST, not GET**
A GET logout fires from any `<img>` tag on any site. `auth.py`

**Closed-by-default signup**
`ALLOW_PUBLIC_SIGNUP` is off unless set. The safe state is the default, and going public is
one env var rather than a code change. `config.py`

**Isolation is structural, and tested**
Every journal route has `@login_required`; every entries query has `WHERE user_id = ?`. A
missing login check gives you a redirect you notice — **a missing `WHERE` gives you someone
else's diary and no error at all.** Hence `tests/test_isolation.py`.

---

## F. Environment & git

**A venv is a folder + `pyvenv.cfg`**
The marker file is the only thing that makes Python treat the folder as a venv. Without it,
`venv/bin/python` silently uses the **system** packages — `ModuleNotFoundError` for a package
you can see on disk.

**Activation ≠ configuration**
`(venv)` in your prompt only means your **shell** knows the path.

**`load_dotenv()` at module top**
Flask's CLI loads `.env` and `app.run()` does too — **gunicorn does neither**. Relying on the
launcher means "is the key present?" depends on how you started the app: works in every local
test, silently absent in production. One explicit call makes three launchers one code path.
`config.py`

**`os.environ` is read in exactly one file**
If values are read in many places, what you get depends on *where* it was read — which is
precisely how the two-launch-path bug happened. `config.py`

**`.gitignore` doesn't untrack**
It only stops **new** files. Already-tracked files keep being tracked until
`git rm -r --cached <path>`.

**A freeze records what IS installed**
Not what should be. Hand-adding a package to `requirements.txt` without installing it makes
the file lie in the opposite direction — and that is how `python-dotenv` came to be missing
while the app ran fine on the machine where it had been installed by hand.

---

## G. Design decisions (the "why", in one line each)

**Save first, analyse second**
`INSERT` with `NULL` mood → call the API → `UPDATE` the same row. Everything between can
fail — network, key, timeout, killed process. Saving first means **the writing is on disk
before the network is ever touched.** `journal.py`

**`NULL` is the retry queue**
`analysis_status='pending'` rows are findable and recoverable. Fix the cause, sweep,
everything catches up. This only works because of two earlier decisions: save before the API
call, and store `None` instead of `''`.

**Match the response to the scope of the failure**
`SECRET_KEY` missing → fatal, nobody can log in. `GROQ_API_KEY` missing → warning, one
feature degrades. Refusing to boot over a recoverable fault turns a degraded feature into a
total outage. `app.py`

**Log the detail, show a summary**
`app.logger.warning` the `401` for yourself; show the user one plain sentence. An error they
can't act on shouldn't be shown to them in detail.

**A closed vocabulary beats a hopeful prompt**
The prompt *defined* the score's 1–10 scale, so scores were stable across runs. It never
defined the label's vocabulary, so labels weren't. **A defined range is an anchor; an
undefined one is an invitation.** `analysis.py`

**Banning a form does not remove an intent**
A prompt rule against advice did not stop advice — it came back as *"What small step could
help you start moving forward?"* That is advice wearing a question mark. Prompt rules reduce
a behaviour; they do not guarantee its absence.

**The safety line is static HTML, not a prompt instruction**
A prompt saying "mention crisis resources if appropriate" is a probability — missable,
arguable, degradable by an unusual entry. A line no model produces cannot fail. It lives in
`base.html`, so every page inherits it by extending. `templates/base.html`

---

*Last updated 2026-09-30.*
*Not yet covered (doesn't exist yet): the background analysis worker, the `pending`-row
sweep, and the CSRF test.*
