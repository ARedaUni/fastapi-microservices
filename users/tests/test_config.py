import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_a_secret_key_below_the_hmac_minimum_is_rejected() -> None:
    """RFC 7518 section 3.2: an HS256 key must be at least as long as its hash
    output, 32 bytes. PyJWT only warns, once per token signed and never where
    anyone deploying would see it; refusing to build Settings turns that into a
    startup failure instead.
    """
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(SECRET_KEY=SecretStr("secret"))  # type: ignore[call-arg]


def test_a_secret_key_at_the_minimum_is_accepted() -> None:
    key = "x" * 32

    settings = Settings(SECRET_KEY=SecretStr(key))  # type: ignore[call-arg]

    assert settings.SECRET_KEY.get_secret_value() == key
