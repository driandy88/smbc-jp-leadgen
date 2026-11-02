"""Single hardcoded account (temporary, per project decision) with signed bearer tokens."""

import hmac

from fastapi import Depends, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.settings import get_settings

SESSION_TTL_S = 7 * 24 * 3600
BILLING_TTL_S = 15 * 60


def _signer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=salt)


def check_login(email: str, password: str) -> bool:
    s = get_settings()
    return (email.strip().lower() == s.login_email.lower()
            and hmac.compare_digest(password.encode(), s.login_password.encode()))


def issue_token(email: str) -> str:
    return _signer("session").dumps({"email": email})


def current_user(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return _signer("session").loads(token, max_age=SESSION_TTL_S)["email"]
    except (BadSignature, SignatureExpired, KeyError):
        raise HTTPException(401, "Sign in again")


def check_passcode(passcode: str) -> bool:
    return hmac.compare_digest(passcode.encode(), get_settings().billing_passcode.encode())


def issue_billing_token(email: str) -> str:
    return _signer("billing").dumps({"email": email})


def billing_access(x_billing_token: str = Header(default=""), user: str = Depends(current_user)) -> str:
    try:
        _signer("billing").loads(x_billing_token, max_age=BILLING_TTL_S)
    except (BadSignature, SignatureExpired):
        raise HTTPException(403, "Billing is locked")
    return user


def initials(email: str) -> str:
    parts = email.split("@")[0].replace("_", ".").split(".")
    return "".join(p[0] for p in parts if p)[:2].upper()
