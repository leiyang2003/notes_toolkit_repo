from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import quote, unquote, urlparse, urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str


class AuthError(Exception):
    def __init__(self, message: str, code: str = "unauthorized") -> None:
        super().__init__(message)
        self.code = code


def parse_origin_list(raw: str) -> set[str]:
    out = set()
    for part in (raw or "").split(","):
        value = part.strip().rstrip("/")
        if value:
            out.add(value)
    return out


def safe_next_url(raw: str, *, allow_origins: set[str]) -> str:
    value = (raw or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if origin in allow_origins:
            return value
    return "/"


def append_query(url: str, key: str, value: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={quote(value, safe='')}"


class GoogleVerifier:
    def __init__(self) -> None:
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.allow_insecure = os.environ.get("ALLOW_INSECURE_GOOGLE", "").strip() == "1"
        self._cache: dict[str, tuple[float, AuthUser]] = {}
        self._lock = threading.Lock()

    def _cache_get(self, token: str) -> Optional[AuthUser]:
        now = datetime.now().timestamp()
        with self._lock:
            item = self._cache.get(token)
            if not item:
                return None
            exp, user = item
            if exp < now:
                self._cache.pop(token, None)
                return None
            return user

    def _cache_set(self, token: str, user: AuthUser, exp_ts: float) -> None:
        with self._lock:
            self._cache[token] = (exp_ts, user)

    def _jwt_payload_unsafe(self, token: str) -> dict:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        try:
            raw = base64.urlsafe_b64decode(payload.encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def verify(self, bearer_token: str) -> AuthUser:
        token = bearer_token.strip()
        if not token:
            raise AuthError("Missing Bearer token.", code="missing_token")

        cached = self._cache_get(token)
        if cached:
            return cached

        if not self.client_id and not self.allow_insecure:
            raise AuthError("Server auth not configured: set GOOGLE_CLIENT_ID.", code="auth_not_configured")

        if self.allow_insecure and not self.client_id:
            payload = self._jwt_payload_unsafe(token)
            sub = str(payload.get("sub", "")).strip()
            if not sub:
                raise AuthError("Invalid token payload (missing sub).", code="invalid_token")
            exp = float(payload.get("exp", datetime.now().timestamp() + 300))
            user = AuthUser(user_id=sub, email=str(payload.get("email", "")))
            self._cache_set(token, user, exp)
            return user

        req = Request(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AuthError(f"Google token verification failed: {exc}", code="token_verify_failed") from exc

        audience = str(data.get("aud", "")).strip()
        sub = str(data.get("sub", "")).strip()
        if not sub:
            raise AuthError("Invalid Google token: missing sub.", code="invalid_token")
        if self.client_id and audience != self.client_id:
            raise AuthError("Invalid Google token audience.", code="invalid_audience")

        exp = float(data.get("exp", datetime.now().timestamp() + 300))
        user = AuthUser(user_id=sub, email=str(data.get("email", "")).strip())
        self._cache_set(token, user, exp)
        return user


class GoogleOAuthClient:
    def __init__(self) -> None:
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def build_authorize_url(self, state: str) -> str:
        params = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "prompt": "select_account",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    def exchange_code_for_id_token(self, code: str) -> str:
        payload = urlencode(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        req = Request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        id_token = str(data.get("id_token", "")).strip()
        if not id_token:
            raise AuthError("Google token exchange missing id_token.", code="token_exchange_failed")
        return id_token


class SessionManager:
    def __init__(self, secret: str, *, max_age_seconds: int = 14 * 24 * 3600) -> None:
        self.secret = secret.encode("utf-8")
        self.max_age_seconds = max_age_seconds

    def _sign(self, payload_b64: str) -> str:
        sig = hmac.new(self.secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def issue(self, user: AuthUser) -> str:
        payload = {
            "sub": user.user_id,
            "email": user.email,
            "exp": int(time.time()) + self.max_age_seconds,
        }
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify(self, token: str) -> AuthUser:
        raw = token.strip()
        if "." not in raw:
            raise AuthError("Invalid session token.", code="invalid_session")
        payload_b64, sig = raw.split(".", 1)
        expected = self._sign(payload_b64)
        if not hmac.compare_digest(sig, expected):
            raise AuthError("Session signature mismatch.", code="invalid_session")

        payload_raw = base64.urlsafe_b64decode((payload_b64 + "=" * (-len(payload_b64) % 4)).encode("ascii"))
        payload = json.loads(payload_raw.decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp <= int(time.time()):
            raise AuthError("Session expired.", code="session_expired")

        sub = str(payload.get("sub", "")).strip()
        if not sub:
            raise AuthError("Session missing user id.", code="invalid_session")
        return AuthUser(user_id=sub, email=str(payload.get("email", "")).strip())


def build_session_secret() -> str:
    configured = os.environ.get("SESSION_SECRET", "").strip()
    if configured:
        return configured
    return hashlib.sha256(f"{os.getpid()}-{datetime.utcnow().isoformat()}".encode("utf-8")).hexdigest()


def create_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def unquote_cookie(value: str) -> str:
    return unquote(value or "")
