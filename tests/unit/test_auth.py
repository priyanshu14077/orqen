import time
import uuid
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from orqen_gateway.auth import AuthError, JwksKeys, JwtVerifier

BASE = "https://ref.supabase.co"
ISSUER = f"{BASE}/auth/v1"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"


class SigningKey:
    def __init__(self, kid: str) -> None:
        self.kid = kid
        self.private = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict[str, Any]:
        public = jwt.algorithms.ECAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        return public | {"kid": self.kid, "alg": "ES256", "use": "sig"}

    def token(self, **claims: Any) -> str:
        body = {
            "sub": str(uuid.uuid4()),
            "email": "dana@example.com",
            "aud": "authenticated",
            "iss": ISSUER,
            "exp": int(time.time()) + 3600,
        } | claims
        return jwt.encode(body, self.private, algorithm="ES256", headers={"kid": self.kid})


class Jwks:
    """Serves the current key set and counts fetches."""

    def __init__(self, *keys: SigningKey) -> None:
        self.keys = list(keys)
        self.fetches = 0

    def client(self) -> httpx.AsyncClient:
        def reply(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == JWKS_URL
            self.fetches += 1
            return httpx.Response(200, json={"keys": [k.jwk() for k in self.keys]})

        return httpx.AsyncClient(transport=httpx.MockTransport(reply))


def verifier(jwks: Jwks, client: httpx.AsyncClient, min_refresh_s: float = 0) -> JwtVerifier:
    return JwtVerifier(JwksKeys(JWKS_URL, client, min_refresh_s=min_refresh_s), ISSUER)


async def test_a_supabase_token_gives_the_user_id_and_email() -> None:
    key = SigningKey("k1")
    jwks = Jwks(key)
    user = uuid.uuid4()
    async with jwks.client() as client:
        who = await verifier(jwks, client).verify(key.token(sub=str(user)))
    assert who.user_id == user
    assert who.email == "dana@example.com"


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"exp": int(time.time()) - 10}, "(?i)expired"),
        ({"aud": "anon"}, "(?i)audience"),
        ({"iss": "https://other.supabase.co/auth/v1"}, "(?i)issuer"),
        ({"sub": "not-a-uuid"}, "(?i)uuid"),
    ],
)
async def test_bad_claims_are_refused(claims: dict[str, Any], error: str) -> None:
    key = SigningKey("k1")
    jwks = Jwks(key)
    async with jwks.client() as client:
        with pytest.raises(AuthError, match=error):
            await verifier(jwks, client).verify(key.token(**claims))


async def test_symmetric_tokens_are_refused_even_with_a_valid_secret() -> None:
    jwks = Jwks(SigningKey("k1"))
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISSUER, "exp": 2**31},
        "legacy-jwt-secret-of-at-least-32-bytes",
        algorithm="HS256",
    )
    async with jwks.client() as client:
        with pytest.raises(AuthError, match="HS256"):
            await verifier(jwks, client).verify(forged)


async def test_a_rotated_key_is_fetched_when_a_token_names_it() -> None:
    old, new = SigningKey("old"), SigningKey("new")
    jwks = Jwks(old)
    async with jwks.client() as client:
        v = verifier(jwks, client)
        await v.verify(old.token())
        jwks.keys.append(new)
        await v.verify(new.token())
        await v.verify(old.token())
    assert jwks.fetches == 2


async def test_unknown_keys_do_not_refetch_on_every_request() -> None:
    key, stranger = SigningKey("k1"), SigningKey("stranger")
    jwks = Jwks(key)
    async with jwks.client() as client:
        v = verifier(jwks, client, min_refresh_s=60)
        await v.verify(key.token())
        for _ in range(3):
            with pytest.raises(AuthError, match="unknown signing key"):
                await v.verify(stranger.token())
    assert jwks.fetches == 1


async def test_concurrent_first_requests_share_one_key_fetch() -> None:
    """Regression: a second request during the first JWKS fetch was refused with 401."""
    import asyncio

    key = SigningKey("k1")
    jwks = Jwks(key)

    def slow(request: httpx.Request) -> httpx.Response:
        jwks.fetches += 1
        return httpx.Response(200, json={"keys": [key.jwk()]})

    async def delayed(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return slow(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(delayed)) as client:
        v = verifier(jwks, client, min_refresh_s=60)
        users = await asyncio.gather(*(v.verify(key.token()) for _ in range(5)))
    assert len(users) == 5
    assert jwks.fetches == 1
