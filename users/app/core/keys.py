"""RSA key material. Imports nothing from `app` -- config validates the key by
calling load_private_key, so the dependency must point one way only.
"""

import base64
import hashlib
import json
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from jwt.algorithms import RSAAlgorithm

ALGORITHM = "RS256"


def load_private_key(encoded_pem: str) -> RSAPrivateKey:
    # Base64 of a PEM, not the PEM: a PEM is multi-line, and .env, a shell
    # export and a k8s Secret each handle multiple lines differently.
    pem = base64.b64decode(encoded_pem, validate=True)
    key = load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError(f"expected an RSA private key, got {type(key).__name__}")
    return key


def public_jwk(private_key: RSAPrivateKey) -> Dict[str, Any]:
    # public_key(), never the private key: to_jwk would serialise d, p and q
    # into a document served to anyone who asks.
    jwk: Dict[str, Any] = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {**jwk, "kid": thumbprint(jwk), "use": "sig", "alg": ALGORITHM}


def thumbprint(jwk: Dict[str, Any]) -> str:
    """RFC 7638 key id: derived from the key so rotation cannot forget it.

    Canonical form is exact -- required members, lexicographic, no whitespace
    -- or this disagrees with every other implementation.
    """
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
