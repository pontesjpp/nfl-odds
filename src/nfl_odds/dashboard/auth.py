import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional
from fastapi import Request
import pyotp

# Helper functions for dynamic environment variables
def get_admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", os.getenv("ADMIN_SECRET", "admin123")).strip()

def get_mfa_secret() -> str:
    return os.getenv("MFA_SECRET", "").strip()

def get_token_secret() -> str:
    return os.getenv("TOKEN_SECRET", os.getenv("ADMIN_SECRET", get_admin_password() or "biskate-analytics-token-secret-change-in-prod")).strip()

def get_token_expiry() -> int:
    return int(os.getenv("TOKEN_EXPIRY_SECONDS", str(24 * 3600)))

def get_auth_config():
    mfa = get_mfa_secret()
    pwd = get_admin_password()
    return {
        "mfa_enabled": bool(mfa),
        "admin_password_configured": bool(pwd),
    }

def verify_totp(code: str) -> bool:
    mfa = get_mfa_secret()
    if not mfa:
        return True
    clean_secret = mfa.replace(" ", "").upper()
    try:
        totp = pyotp.TOTP(clean_secret)
        # valid_window=1 allows +-30 seconds time drift
        return bool(totp.verify(code.strip(), valid_window=1))
    except Exception as e:
        print(f"Error validating TOTP: {e}")
        return False

def verify_credentials(password: str, totp_code: Optional[str] = None) -> bool:
    admin_pwd = get_admin_password()
    if not admin_pwd:
        return False
    
    # Constant-time comparison to prevent timing attacks
    pass_matches = hmac.compare_digest(
        password.strip().encode("utf-8"),
        admin_pwd.encode("utf-8")
    )
    if not pass_matches:
        return False
        
    mfa = get_mfa_secret()
    if mfa:
        if not totp_code:
            return False
        return verify_totp(totp_code)
        
    return True

def create_admin_token() -> str:
    """Generates a secure HMAC-SHA256 signed bearer token."""
    token_secret = get_token_secret()
    expiry = get_token_expiry()
    payload = {
        "admin": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + expiry
    }
    raw_payload = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    
    signature = hmac.new(
        token_secret.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256
    ).digest()
    b64_sig = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{b64_payload}.{b64_sig}"

def verify_admin_token(token: Optional[str]) -> bool:
    if not token:
        return False
        
    if token.startswith("Bearer ") or token.startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
        
    # Support direct ADMIN_SECRET string for automated CLI or dev backward-compatibility
    direct_secret = os.getenv("ADMIN_SECRET", "")
    if direct_secret and hmac.compare_digest(token.strip().encode("utf-8"), direct_secret.strip().encode("utf-8")):
        return True
        
    parts = token.split(".")
    if len(parts) != 2:
        return False
        
    b64_payload, b64_sig = parts
    
    token_secret = get_token_secret()
    expected_sig = hmac.new(
        token_secret.encode("utf-8"),
        b64_payload.encode("utf-8"),
        hashlib.sha256
    ).digest()
    expected_b64_sig = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")
    
    if not hmac.compare_digest(b64_sig, expected_b64_sig):
        return False
        
    try:
        padded = b64_payload + "=" * (-len(b64_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        if payload.get("admin") is not True:
            return False
        if time.time() > payload.get("exp", 0):
            return False
        return True
    except Exception:
        return False

def is_request_admin(request: Request) -> bool:
    """Checks header (Authorization / x-admin-token / x-admin-secret), cookies, or query parameters."""
    auth_header = (
        request.headers.get("Authorization")
        or request.headers.get("x-admin-token")
        or request.headers.get("x-admin-secret")
    )
    if auth_header and verify_admin_token(auth_header):
        return True
        
    cookie_token = request.cookies.get("nfl_admin_token")
    if cookie_token and verify_admin_token(cookie_token):
        return True
        
    query_key = request.query_params.get("admin_key")
    if query_key and verify_admin_token(query_key):
        return True
        
    return False
