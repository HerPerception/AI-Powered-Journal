"""Application configuration.

Everything that varies between environments is read here, once, from the
environment. Nothing else in the app calls `os.environ` -- if it did, the value
would depend on *where* it was read, which is precisely how the two-launch-path
bug happened.

Note the explicit `load_dotenv()` below. It is not redundant.
"""
import os

from dotenv import load_dotenv

# Load .env here rather than trusting the framework to do it.
#
# Flask's CLI loads it for `flask run`, and `app.run()` loads it too. Gunicorn
# does NEITHER. So relying on the launcher means "is the API key present?"
# depends on how you started the app -- works in every local test, silently
# absent in production. That is the same failure shape as the missing
# python-dotenv declaration: correct on the machine where it was set up by hand,
# wrong everywhere the setup is reproduced from a file.
#
# This turns three launchers into one code path.
load_dotenv()


class Config:
    """Base configuration. Values come from the environment, never the repo."""

    # Fatal if missing -- see create_app(). Signs session cookies; without it
    # Flask cannot issue a login. Must never be committed, so it lives in .env
    # alongside the API key, and .env is gitignored.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Not fatal if missing. A missing Groq key costs mood analysis, not journal
    # entries. The asymmetry is deliberate: match the severity of the response
    # to what the failure actually costs.
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

    # Overridable so tests can point at a throwaway database instead of the
    # real one. Untested code paths are where the isolation bugs will live.
    DATABASE = os.environ.get("JOURNAL_DB", "journal.db")

    # Closed unless someone deliberately opens it. This is the whole invite
    # mechanism: the default is the safe state, and going public is one env var
    # (`ALLOW_PUBLIC_SIGNUP=1`) rather than a code change. When signup is open,
    # every account that registers can post to a page that exists on the public
    # internet -- which is why the default is not "open until you remember to
    # close it".
    ALLOW_PUBLIC_SIGNUP = os.environ.get("ALLOW_PUBLIC_SIGNUP") == "1"

    # Left on everywhere except tests, which POST without a token. Turning this
    # off in production is the single change that reopens every form to
    # cross-site submission, so it is named here rather than defaulted off
    # silently in the test module.
    CSRF_ENABLED = True
