"""CLI helper tests (composition root). Interactive I/O is monkeypatched."""

from university_cli import app


def test_choose_returns_selected_option(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")
    assert app._choose("Pick", ["alice", "bob", "carol"]) == "bob"


def test_choose_reprompts_on_invalid(monkeypatch):
    answers = iter(["0", "9", "x", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert app._choose("Pick", ["alice", "bob"]) == "alice"


def test_resolve_user_uses_explicit_user_without_engine():
    # When --user is given, no directory lookup (engine) is needed.
    assert app.resolve_user(engine=None, user="alice", role_name=None) == "alice"
