"""Verify Supabase access tokens with the project's public signing keys.

Supabase signs access tokens with an asymmetric key (ES256 or RS256) and publishes
the public keys as a JWKS. The gateway caches that set and fetches it again when a
token names a key id it doesn't know, at most once every `min_refresh_s`. Symmetric
algorithms (HS256) are refused, so a leaked legacy secret can't mint tokens here.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx
import jwt

ALGORITHMS = ("ES256", "RS256")


class AuthError(Exception):
    """The token is missing, malformed, expired or not ours."""


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str | None


class KeySource(Protocol):
    async def get(self, kid: str | None) -> jwt.PyJWK | None: ...


class JwksKeys:
    def __init__(
        self,
        url: str,
        client: httpx.AsyncClient,
        *,
        ttl_s: float = 600,
        min_refresh_s: float = 30,
    ) -> None:
        self._url = url
        self._client = client
        self._ttl_s = ttl_s
        self._min_refresh_s = min_refresh_s
        self._keys: dict[str | None, jwt.PyJWK] = {}
        self._fetched_at = float("-inf")
        self._lock = asyncio.Lock()

    def _stale(self, kid: str | None) -> bool:
        age = time.monotonic() - self._fetched_at
        return age > self._ttl_s or (kid not in self._keys and age > self._min_refresh_s)

    async def get(self, kid: str | None) -> jwt.PyJWK | None:
        # One fetch at a time: requests that arrive during it wait for its keys instead
        # of seeing an empty set and refusing a valid token.
        if self._stale(kid) or (kid not in self._keys and self._lock.locked()):
            async with self._lock:
                if self._stale(kid):
                    await self._refresh()
        return self._keys.get(kid)

    async def _refresh(self) -> None:
        self._fetched_at = time.monotonic()
        try:
            resp = await self._client.get(self._url)
            resp.raise_for_status()
            keyset = jwt.PyJWKSet.from_dict(resp.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            if not self._keys:
                raise AuthError(f"signing keys unavailable: {type(exc).__name__}") from exc
            return  # keep serving the keys we have
        self._keys = {k.key_id: k for k in keyset.keys}


class JwtVerifier:
    def __init__(self, keys: KeySource, issuer: str, audience: str = "authenticated") -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        alg = header.get("alg")
        if alg not in ALGORITHMS:
            raise AuthError(f"algorithm {alg!r} is not accepted")
        key = await self._keys.get(header.get("kid"))
        if key is None:
            raise AuthError("unknown signing key")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            user_id = UUID(claims["sub"])
        except (jwt.PyJWTError, ValueError) as exc:
            raise AuthError(str(exc)) from exc
        return Principal(user_id=user_id, email=claims.get("email") or None)


def supabase_verifier(supabase_url: str, client: httpx.AsyncClient) -> JwtVerifier:
    base = supabase_url.rstrip("/")
    keys = JwksKeys(f"{base}/auth/v1/.well-known/jwks.json", client)
    return JwtVerifier(keys, issuer=f"{base}/auth/v1")
