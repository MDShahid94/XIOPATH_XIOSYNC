import importlib
import os

import pytest
from pydantic import ValidationError


@pytest.fixture()
def auth_module(monkeypatch):
    monkeypatch.setenv("XIOPATH_ENV", "test")
    monkeypatch.setenv("XIOPATH_JWT_SECRET", "test-secret-that-is-long-enough-for-ci-only")
    import api.routers.auth as auth

    return importlib.reload(auth)


def test_public_signup_schema_rejects_role(auth_module):
    with pytest.raises(ValidationError):
        auth_module.SignupRequest(
            username="normal_user",
            password="correct-horse-battery-staple",
            role="admin",
        )


def test_login_schema_rejects_privilege_claims(auth_module):
    with pytest.raises(ValidationError):
        auth_module.LoginRequest(
            username="normal_user",
            password="correct-horse-battery-staple",
            role="admin",
        )


def test_username_validation_rejects_punctuation(auth_module):
    with pytest.raises(ValidationError):
        auth_module.SignupRequest(username="invalid-name", password="long-enough-password")


def test_production_rejects_default_secret(monkeypatch):
    monkeypatch.setenv("XIOPATH_ENV", "production")
    monkeypatch.delenv("XIOPATH_JWT_SECRET", raising=False)

    import api.routers.auth as auth

    with pytest.raises(RuntimeError, match="XIOPATH_JWT_SECRET"):
        importlib.reload(auth)

    monkeypatch.setenv("XIOPATH_ENV", "test")
    monkeypatch.setenv("XIOPATH_JWT_SECRET", "test-secret-that-is-long-enough-for-ci-only")
    importlib.reload(auth)
