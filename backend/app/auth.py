"""Environment-configured JWT helpers for the API."""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Request, WebSocket
from jwt import InvalidTokenError


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "false").lower() == "true"


def create_access_token(subject: str) -> str:
    secret = _secret()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=int(os.getenv("JWT_EXPIRES_MINUTES", "60"))
    )
    return jwt.encode({"sub": subject, "exp": expires_at}, secret, algorithm="HS256")


def credentials_are_valid(username: str, password: str) -> bool:
    expected_username = os.getenv("API_USERNAME")
    expected_password = os.getenv("API_PASSWORD")
    if not expected_username or not expected_password:
        return False
    return hmac.compare_digest(username, expected_username) and hmac.compare_digest(
        password, expected_password
    )


def require_http_auth(request: Request) -> str | None:
    if not auth_required():
        return None
    token = _bearer_token(request.headers.get("authorization"))
    return _decode_token(token)


async def require_websocket_auth(websocket: WebSocket) -> str | None:
    if not auth_required():
        return None
    token = websocket.query_params.get("access_token") or _bearer_token(
        websocket.headers.get("authorization")
    )
    try:
        return _decode_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return None


def _secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    return secret


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def _decode_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")
    if len(token) > 4096:
        raise HTTPException(status_code=400, detail="Bearer token is too long")
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError("Missing token subject")
        return subject
    except InvalidTokenError as error:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from error
