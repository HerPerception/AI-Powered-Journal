"""CSRF protection, tested.

`csrf_protect` was the least-verified code in `auth.py` -- it is switched off in
the main test config, so every isolation test POSTs straight past it. Nothing
checked that it worked at all.

Three things have to be true, and they fail in different ways:

1. A POST with **no token** is rejected.
2. A POST with a **wrong token** is rejected.
3. A POST with the **real token** is accepted -- and the work actually happens.

(3) is not decoration. (1) and (2) would both pass if `csrf_protect` rejected
*everything*, which would be a broken app that looks secure. Same shape as
LEARNING_LOG 31: an assertion is only worth something if the only way to reach
it is the thing you meant to test.
"""
import re

from db import connect_db

PASSWORD = "password123"

# Scrapes the hidden input out of a rendered page. A slightly ugly regex in
# service of a real property: a browser can only obtain a token by loading a
# page, and this makes the test do the same thing a browser does rather than
# reaching into the session dict and manufacturing one.
TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def token_for(client, path="/signup"):
    """Load a page, return the CSRF token it rendered."""
    html = client.get(path).get_data(as_text=True)
    match = TOKEN_RE.search(html)
    assert match, f"no csrf_token input rendered by {path}"
    return match.group(1)


def signup_data(token=None):
    data = {"email": "a@example.com", "password": PASSWORD}
    if token is not None:
        data["csrf_token"] = token
    return data


def user_count(app):
    conn = connect_db(app.config["DATABASE"])
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    conn.close()
    return count


def test_post_without_a_token_is_rejected(csrf_app, csrf_client):
    response = csrf_client.post("/signup", data=signup_data())

    assert response.status_code == 400
    assert user_count(csrf_app) == 0, "the request was rejected but the work ran anyway"


def test_post_with_a_wrong_token_is_rejected(csrf_app, csrf_client):
    # Load the page first, so the session genuinely holds a token. Without this
    # the request would be rejected merely because the session has no token yet
    # -- which would pass while proving nothing about comparison.
    csrf_client.get("/signup")

    response = csrf_client.post("/signup", data=signup_data("not-the-real-token"))

    assert response.status_code == 400
    assert user_count(csrf_app) == 0


def test_post_with_the_real_token_is_accepted(csrf_app, csrf_client):
    token = token_for(csrf_client)

    response = csrf_client.post("/signup", data=signup_data(token))

    # 302 to /login is signup's success path. 400 would mean the token was
    # rejected; anything else means the route never ran.
    assert response.status_code == 302

    # The precondition, per LEARNING_LOG 31. A redirect alone does not prove a
    # user was created -- it proves the route returned. The row is the claim.
    assert user_count(csrf_app) == 1


def test_get_requests_are_not_blocked(csrf_client):
    """Only state-changing methods are checked.

    If `csrf_protect` ever lost its method guard, every GET would 400 and the
    site would be completely unusable -- a loud failure, but worth pinning.
    """
    assert csrf_client.get("/signup").status_code == 200
    assert csrf_client.get("/login").status_code == 200


def test_a_token_from_another_session_is_rejected(csrf_app):
    """The token is per-session, not a shared secret.

    This is the actual security property. A single global token would satisfy
    every test above and defend against nothing -- an attacker could fetch the
    app's one token from any page and use it. The check has to be against *the
    session making the request*.
    """
    with csrf_app.test_client() as alice:
        alice_token = token_for(alice)

    with csrf_app.test_client() as mallory:
        # Mallory gets her own token first. Without this she would be rejected
        # for having no token at all, and the test would pass without ever
        # comparing alice_token to anything.
        mallory.get("/signup")

        response = mallory.post("/signup", data=signup_data(alice_token))

    assert response.status_code == 400
    assert user_count(csrf_app) == 0
