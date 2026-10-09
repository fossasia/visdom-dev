# Copyright 2017-present, The Visdom Authors
import pytest

from app.admin.panel import StaffAuth
from app.config import settings


@pytest.mark.parametrize("secure", [True, False])
def test_the_staff_cookie_follows_the_secure_cookie_setting(monkeypatch, secure):
    monkeypatch.setattr(settings, "COOKIE_SECURE", secure)
    backend = StaffAuth(secret_key="not-a-real-secret")
    assert backend.middlewares[0].kwargs["https_only"] is secure


def test_the_staff_cookie_stays_on_the_admin_path():
    backend = StaffAuth(secret_key="not-a-real-secret")
    assert backend.middlewares[0].kwargs["path"] == "/admin"
