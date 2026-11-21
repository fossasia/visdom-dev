from unittest.mock import MagicMock

import pytest

from app.admin import bootstrap
from app.models import AdminUser


def mock_password_prompts(monkeypatch, *passwords):
    answers = iter(passwords)
    monkeypatch.setattr(
        bootstrap.getpass,
        "getpass",
        lambda _prompt: next(answers),
    )


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["staff@example.com"],
        ["staff@example.com", "admin", "extra"],
    ],
)
def test_main_rejects_wrong_number_of_arguments(argv, monkeypatch):
    getpass_mock = MagicMock()
    session_factory = MagicMock()

    monkeypatch.setattr(bootstrap.getpass, "getpass", getpass_mock)
    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)

    with pytest.raises(SystemExit, match="usage:"):
        bootstrap.main(argv)

    getpass_mock.assert_not_called()
    session_factory.assert_not_called()


def test_main_rejects_invalid_role(monkeypatch):
    getpass_mock = MagicMock()
    monkeypatch.setattr(bootstrap.getpass, "getpass", getpass_mock)

    with pytest.raises(SystemExit, match="role must be one of"):
        bootstrap.main(["staff@example.com", "invalid-role"])

    getpass_mock.assert_not_called()


def test_main_rejects_short_password(monkeypatch):
    session_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)
    mock_password_prompts(monkeypatch, "short")

    with pytest.raises(SystemExit, match="at least 12 characters"):
        bootstrap.main(["staff@example.com", "admin"])

    session_factory.assert_not_called()


def test_main_rejects_password_confirmation_mismatch(monkeypatch):
    session_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)
    mock_password_prompts(
        monkeypatch,
        "correct-horse-battery",
        "different-password-value",
    )

    with pytest.raises(SystemExit, match="passwords did not match"):
        bootstrap.main(["staff@example.com", "admin"])

    session_factory.assert_not_called()


def test_main_creates_new_admin_user(monkeypatch, capsys):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    session_factory = MagicMock(return_value=db)
    hash_password = MagicMock(return_value="hashed-password")

    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)
    monkeypatch.setattr(bootstrap, "get_password_hash", hash_password)
    mock_password_prompts(
        monkeypatch,
        "correct-horse-battery",
        "correct-horse-battery",
    )

    bootstrap.main(["  NEW@EXAMPLE.COM ", " admin "])

    db.query.assert_called_once_with(AdminUser)
    db.query.return_value.filter.assert_called_once()

    created_admin = db.add.call_args.args[0]

    assert isinstance(created_admin, AdminUser)
    assert created_admin.email == "new@example.com"
    assert created_admin.role == "admin"
    assert created_admin.password_hash == "hashed-password"

    hash_password.assert_called_once_with("correct-horse-battery")
    db.commit.assert_called_once()
    db.close.assert_called_once()

    assert capsys.readouterr().out.strip() == "created new@example.com as admin"


def test_main_updates_existing_admin_user(monkeypatch, capsys):
    existing_admin = AdminUser(
        email="staff@example.com",
        role="support",
        password_hash="old-hash",
        is_active=False,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing_admin

    session_factory = MagicMock(return_value=db)
    hash_password = MagicMock(return_value="new-hash")

    monkeypatch.setattr(bootstrap, "SessionLocal", session_factory)
    monkeypatch.setattr(bootstrap, "get_password_hash", hash_password)
    mock_password_prompts(
        monkeypatch,
        "new-secure-password",
        "new-secure-password",
    )

    bootstrap.main(["STAFF@EXAMPLE.COM", " superadmin "])

    assert existing_admin.role == "superadmin"
    assert existing_admin.password_hash == "new-hash"
    assert existing_admin.is_active is True

    db.add.assert_not_called()
    hash_password.assert_called_once_with("new-secure-password")
    db.commit.assert_called_once()
    db.close.assert_called_once()

    assert capsys.readouterr().out.strip() == "updated staff@example.com as superadmin"


def test_main_closes_database_session_when_commit_fails(monkeypatch):
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")

    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        bootstrap,
        "get_password_hash",
        lambda _password: "hashed-password",
    )
    mock_password_prompts(
        monkeypatch,
        "correct-horse-battery",
        "correct-horse-battery",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        bootstrap.main(["staff@example.com", "admin"])

    db.close.assert_called_once()
