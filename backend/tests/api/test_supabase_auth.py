import base64
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from app.integrations import supabase_auth

TEST_SUPABASE_URL = "https://test.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"
TEST_KID = "test-kid-1"


def _b64url_uint(value: int, byte_length: int = 32) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(byte_length, "big")).rstrip(b"=").decode()


@pytest.fixture
def ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url_uint(public_numbers.x),
        "y": _b64url_uint(public_numbers.y),
        "kid": TEST_KID,
        "alg": "ES256",
        "use": "sig",
    }
    return pem, jwk


@pytest.fixture(autouse=True)
def _configure_auth(monkeypatch, ec_keypair):
    _, jwk = ec_keypair
    monkeypatch.setattr(settings, "supabase_url", TEST_SUPABASE_URL)
    # Seed the JWKS cache so _fetch_jwks never makes a network call.
    monkeypatch.setattr(supabase_auth, "_jwks_cache", {"keys": [jwk]})
    monkeypatch.setattr(supabase_auth, "_jwks_fetched_at", time.monotonic())


def _make_token(
    pem: bytes,
    *,
    kid: str = TEST_KID,
    issuer: str = TEST_ISSUER,
    audience: str = "authenticated",
    exp_delta: int = 3600,
    sub: str = "11111111-1111-1111-1111-111111111111",
    email: str = "user@example.com",
) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": sub,
        "email": email,
        "aud": audience,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_delta)).timestamp()),
    }
    return jwt.encode(claims, pem, algorithm="ES256", headers={"kid": kid})


def test_validate_token_accepts_valid_token(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem)

    claims = supabase_auth.validate_token(token)

    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["email"] == "user@example.com"
    assert claims["iss"] == TEST_ISSUER
    assert claims["aud"] == "authenticated"


def test_validate_token_rejects_expired_token(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem, exp_delta=-10)

    with pytest.raises(HTTPException) as exc_info:
        supabase_auth.validate_token(token)

    assert exc_info.value.status_code == 401


def test_validate_token_rejects_wrong_issuer(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem, issuer="https://attacker.example.com/auth/v1")

    with pytest.raises(HTTPException):
        supabase_auth.validate_token(token)


def test_validate_token_rejects_wrong_audience(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem, audience="not-authenticated")

    with pytest.raises(HTTPException):
        supabase_auth.validate_token(token)


def test_validate_token_rejects_unknown_kid(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem, kid="some-other-kid")

    with pytest.raises(HTTPException):
        supabase_auth.validate_token(token)


def test_validate_token_rejects_tampered_payload(ec_keypair):
    pem, _ = ec_keypair
    token = _make_token(pem)
    
    # Change the very first letter of the token payload section
    head, payload, signature = token.split(".")
    tampered_payload = ("X" if payload[0] != "X" else "Y") + payload[1:]
    tampered_token = f"{head}.{tampered_payload}.{signature}"

    with pytest.raises(HTTPException):
        supabase_auth.validate_token(tampered_token)


def test_validate_token_rejects_token_signed_by_unknown_key(ec_keypair):
    # A different private key whose public key is NOT in our JWKS.
    rogue_key = ec.generate_private_key(ec.SECP256R1())
    rogue_pem = rogue_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Sign with the rogue key but claim our trusted kid in the header.
    token = _make_token(rogue_pem)

    with pytest.raises(HTTPException):
        supabase_auth.validate_token(token)


def test_validate_token_rejects_malformed_token():
    with pytest.raises(HTTPException):
        supabase_auth.validate_token("not.a.real.token")
