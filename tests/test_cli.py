"""CLI registration.

This file exists because of a bug that a green test suite did not catch.

`auth.py` defines `@bp.cli.command("create-user")`, which reads as
`flask create-user`. It actually registers as `flask auth create-user`, because
`Blueprint.cli` namespaces its commands under the blueprint name unless
`cli_group` says otherwise. The code, the README and the session notes all said
`flask create-user`; nothing verified it, and it stayed broken through a passing
`pytest` run.

Why the isolation tests couldn't catch it: they drive the app through
`test_client()`, which exercises **routes**. A CLI command is not a route -- it
never passes through routing, `before_request`, or a view function. A suite that
only tests one entry point says nothing about the others.

So this asserts the entry point itself. It is one line, it costs nothing, and it
is the difference between "the command exists" and "the command was named
correctly in a docstring."
"""


def test_create_user_command_is_registered(journal_app):
    """`flask create-user` must resolve without the blueprint prefix.

    With signup closed by default this is the ONLY way to create an account, so
    a missing or mis-namespaced command means the app has no way in at all.

    Uses `journal_app.cli.commands` rather than shelling out to `flask`, so the
    test does not depend on which app the CLI happens to discover on disk.
    """
    assert "create-user" in journal_app.cli.commands


def test_create_user_is_not_namespaced_under_the_blueprint(journal_app):
    """The failure mode, asserted directly.

    `cli_group` defaults to `_sentinel`, which registers the commands as a
    nested group under the blueprint name. If someone removes the explicit
    `cli_group=None` from `create_app()`, the check above still passes --
    `auth` becomes a command -- and `flask create-user` breaks again. This names
    the specific thing that went wrong so the regression is unambiguous.
    """
    assert "auth" not in journal_app.cli.commands
