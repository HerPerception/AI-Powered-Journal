"""Makes the project root importable from the tests.

pytest walks up from each test file to the first directory without an
`__init__.py` and puts *that* on `sys.path`. For `tests/test_isolation.py` with
no `tests/__init__.py`, that directory is `tests/` -- so `from app import
create_app` fails with ModuleNotFoundError even though app.py is sitting right
there in the parent.

A conftest.py at the root is found first, and pytest adds its directory (the
project root) to `sys.path` as part of collecting it. So this file needs no
contents to do its job. It is here, with this comment, because an empty file
with no explanation looks like an accident and gets deleted.

The alternative is `pythonpath = ["."]` under `[tool.pytest.ini_options]` in a
pyproject.toml. Same effect, needs pytest 7+.
"""
