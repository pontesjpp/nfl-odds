import os
import pyotp
import pytest
from fastapi.testclient import TestClient
from nfl_odds.dashboard.auth import (
    verify_credentials,
    create_admin_token,
    verify_admin_token,
)
from nfl_odds.dashboard.api import app

@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test_admin_pass")
    monkeypatch.setenv("MFA_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("TOKEN_SECRET", "test_token_secret_123")
    monkeypatch.setenv("READ_ONLY_MODE", "true")

def test_credentials_verification():
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    valid_code = totp.now()
    
    assert verify_credentials("test_admin_pass", valid_code) is True
    assert verify_credentials("wrong_pass", valid_code) is False
    assert verify_credentials("test_admin_pass", "000000") is False

def test_token_creation_and_validation():
    token = create_admin_token()
    assert verify_admin_token(token) is True
    assert verify_admin_token(f"Bearer {token}") is True
    assert verify_admin_token("invalid.token.here") is False

def test_api_security_protection():
    client = TestClient(app)
    
    # 1. Unauthenticated visitor cannot run pipeline / scraper
    res = client.post("/api/run-pipeline")
    assert res.status_code == 403
    
    # 2. Authenticate via login endpoint
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP")
    res = client.post("/api/auth/login", json={
        "password": "test_admin_pass",
        "totp_code": totp.now()
    })
    assert res.status_code == 200
    token = res.json()["token"]
    
    # 3. Check status
    res = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["is_admin"] is True
