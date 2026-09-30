"""The test that makes the privacy claim true.

`WHERE user_id = ?` is a habit. This is the thing that fails the build when the
habit slips. A privacy bug does not announce itself the way a crash does -- the
page renders, the request is a 200, and the only symptom is that someone is
reading a stranger's diary and neither of them knows.
"""
import pytest

from app import create_app
from db import connect_db

PASSWORD = "password123"


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

    # Off, so the POSTs below do not have to carry a token. This means the tests
    # do NOT cover csrf_protect -- that needs its own test, and until it has one,
    # CSRF is the least-verified thing in auth.py.
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


def register_and_login(client, email):
    """Signup does not log you in -- it redirects to the login page. Both steps."""
    client.post("/signup", data={"email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})


def test_entries_are_isolated_between_accounts(journal_app, client):
    register_and_login(client, "a@example.com")
    client.post("/entries", data={"entry_text": "AAAA secret diary"})
    client.post("/logout")

    register_and_login(client, "b@example.com")
    client.post("/entries", data={"entry_text": "BBBB secret diary"})

    # The precondition, and the reason this test is worth anything.
    #
    # Without it, the two assertions at the bottom would pass on a database
    # where saving is broken and the table is empty -- A's entry would be
    # absent from B's page because it is absent from everywhere. "Not visible"
    # and "not there" are different claims, and only one of them is privacy.
    conn = connect_db(journal_app.config["DATABASE"])
    rows = conn.execute("SELECT text, user_id FROM entries ORDER BY id").fetchall()
    conn.close()

    assert [row["text"] for row in rows] == ["AAAA secret diary", "BBBB secret diary"]
    assert None not in {row["user_id"] for row in rows}, "an entry has no owner"
    assert len({row["user_id"] for row in rows}) == 2, "both entries share one owner"

    # The claim. We are logged in as B.
    body = client.get("/").get_data(as_text=True)
    assert "BBBB secret diary" in body
    assert "AAAA secret diary" not in body


def test_anonymous_visitor_is_sent_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_visitor_cannot_post_an_entry(journal_app, client):
    response = client.post("/entries", data={"entry_text": "written by nobody"})
    assert response.status_code == 302

    conn = connect_db(journal_app.config["DATABASE"])
    count = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"]
    conn.close()

    # The redirect is the visible half. This is the half that matters: the
    # decorator must run *before* the handler, not merely produce a redirect
    # after it. A handler that saves and then redirects would satisfy the first
    # assertion and fail this one.
    assert count == 0
