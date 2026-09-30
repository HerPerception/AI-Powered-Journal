"""Application factory, and the entry point for a local dev server.

## Why a factory instead of a module-level `app`

`debug=True` used to sit inside `if __name__ == "__main__":` at the bottom of
this file. `flask run` imports the module and skips that block, so the *same
file* launched two ways produced two different servers:

    python app.py          flask run
    ---------------        --------------
    Debug mode: on         Debug mode: off
    Restarting with stat   (absent)
    Debugger is active!    (absent)
    Debugger PIN: 115-...  (absent)

That was the fourth time a "must apply however you launch this" concern hid
inside the `__main__` guard. (The others: `connect_db()` not running, and .env
loading being the framework's job rather than ours.)

A factory closes the gap structurally rather than patching a fourth instance of
it: `flask run`, `gunicorn` and `python app.py` all call `create_app()`, so
everything inside it applies identically no matter which one started the
process. Configuration lives in one place, and the `__main__` block is reduced
to "start a development server on this machine" -- which is the only thing that
legitimately differs.

## The startup key check

This is where the check from SESSION_NOTES 6 belongs. It was queued with the
question "where does it go so it runs under BOTH `flask run` and `python app.py`?"
The answer is inside the factory, because the factory is the one thing every
launch path calls.

Note it runs on *import* of this module too -- which is what `flask run` does.
And under the reloader (debug mode), the app is imported in a second process, so
the factory runs twice. Anything expensive or stateful in here pays that cost
twice. Hence: the check below reads configuration and logs. It makes no network
call.
"""
import os

from flask import Flask

from config import Config
from journal import bp as journal_bp


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        # Fatal, deliberately. Without a secret key Flask cannot sign a session
        # cookie, so no user can log in -- the app is not partially working, it
        # is entirely not working. Failing here means you find out at boot with
        # a readable message, instead of at the first login with a confusing one.
        raise RuntimeError(
            "SECRET_KEY is not set, so sessions cannot be signed. Generate one:\n"
            "    python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "then add it to .env as SECRET_KEY=<value>. .env is gitignored and "
            "must stay that way -- anyone with this value can forge a login."
        )

    if not app.config.get("GROQ_API_KEY"):
        # NOT fatal, and the asymmetry with SECRET_KEY above is the point.
        #
        # A missing Groq key costs mood analysis and nothing else. The entry is
        # inserted before the API is ever called, so the writing is already on
        # disk and the row keeps analysis_status='pending' until a key exists.
        # Refusing to boot would turn a degraded feature into a total outage --
        # and would lose every entry written while the key was wrong, which is
        # exactly what the save-first design exists to prevent.
        #
        # Match the response to the scope of the failure. This failure is
        # recoverable, so the app must stay up to be recovered into.
        app.logger.warning(
            "GROQ_API_KEY is not set. Entries will save, but none will be analysed."
        )

    app.register_blueprint(journal_bp)
    return app


if __name__ == "__main__":
    # Dev convenience only. Configuration does NOT live here -- that was the bug.
    # Production runs `gunicorn "app:create_app()"`, which never executes this.
    #
    # Debug defaults to OFF so that running this file on a machine that is not
    # yours does not expose the Werkzeug debugger console (remote code execution,
    # guarded only by a PIN printed to a terminal). Opt in explicitly with
    # FLASK_DEBUG=1.
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
