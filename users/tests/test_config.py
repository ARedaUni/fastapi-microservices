import base64

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_a_signing_key_that_is_not_a_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="JWT_PRIVATE_KEY"):
        Settings(JWT_PRIVATE_KEY=SecretStr("not-base64-and-not-a-pem"))  # type: ignore[call-arg]


def test_an_hmac_secret_is_not_accepted_as_a_signing_key() -> None:
    """The regression that matters: leaving the old HS256 secret in the
    environment must stop the service, not silently sign with something that
    isn't an RSA key.
    """
    hmac_secret = base64.b64encode(b"x" * 32).decode()

    with pytest.raises(ValidationError, match="JWT_PRIVATE_KEY"):
        Settings(JWT_PRIVATE_KEY=SecretStr(hmac_secret))  # type: ignore[call-arg]
