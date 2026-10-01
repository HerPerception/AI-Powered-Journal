"""Fixtures shared by every test module.

These live here rather than in `test_isolation.py` because pytest only shares a
fixture with the module that defines it. `test_cli.py` needs the same app, and a
second copy of the config would drift from the first -- at which point the two
test files would be testing two subtly different applications and neither would
say so.
"""
import pytest

from app import create_app


class TestConfig:
    # A literal, not a secret. It signs test cookies for the duration of one
    # test function and protects nothing.
    SECRET_KEY = "test-only"
    TESTING = True

    # None, and this is what keeps the suite hermetic.
    #
    # analyze_entry raises AnalysisError immediately when the key is falsy, so
    # /entries never reaches the network. The save-first design means the row is
    # written *before* that call, so the entry still lands -- which is exactly
    # the behaviour the isolation test needs to exercise. No mock, no monkeypatch,
    # no recorded fixture, no requests to Groq from CI.
    GROQ_API_KEY = None

    ALLOW_PUBLIC_SIGNUP = True

    # Off, so POSTs in the tests do not have to carry a token. This means the
    # tests do NOT cover csrf_protect -- that needs its own test, and until it
    # has one, CSRF is the least-verified thing in auth.py.
    CSRF_ENABLED = False

    DATABASE = None  # overridden per test


@pytest.fixture
def journal_app(tmp_path):
    """A whole app on a throwaway database. One file per test function."""

    class Config(TestConfig):
        DATABASE = str(tmp_path / "test.db")

    return create_app(Config)


@pytest.fixture
def client(journal_app):
    with journal_app.test_client() as test_client:
        yield test_client


# --------------------------------------------------------------------------
# CSRF
#
# A second app, because CSRF has to be ON to be tested and OFF for everything
# else. The isolation tests POST a dozen times and would have to scrape a token
# for each one -- noise that would bury the thing they are actually asserting.
#
# So there are two apps rather than one app with the check disabled. The
# difference matters: `CSRF_ENABLED = False` is a deliberate, named override,
# and this fixture is what makes sure the real behaviour is still verified
# somewhere. Turning it off everywhere would leave csrf_protect untestable and
# untested, which is how it got to be the least-verified code in auth.py.
# --------------------------------------------------------------------------


class CsrfConfig(TestConfig):
    CSRF_ENABLED = True


@pytest.fixture
def csrf_app(tmp_path):
    class Config(CsrfConfig):
        DATABASE = str(tmp_path / "test.db")

    return create_app(Config)


@pytest.fixture
def csrf_client(csrf_app):
    with csrf_app.test_client() as test_client:
        yield test_client
