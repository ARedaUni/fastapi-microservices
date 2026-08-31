from typing import Annotated, Any, Dict, Optional

from pydantic import EmailStr, Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings

# RFC 7518 section 3.2: an HS256 key must be at least as long as the hash it
# feeds, 32 bytes. PyJWT warns below that, once per token signed -- somewhere
# nobody deploying is reading. This refuses to start instead.
HMAC_SHA256_MIN_KEY_BYTES = 32


class Settings(BaseSettings):
    PROJECT_NAME: str

    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    # Stays a plain str rather than PostgresDsn: the Dsn types normalise what
    # they parse, and create_async_engine gets handed this verbatim.
    #
    # Declared `str`, not `Optional[str]`: the validator below always returns one,
    # and pydantic-settings runs before-validators over the default too, so this
    # is never None once the model is built. Saying `Optional` made every caller
    # -- create_async_engine among them -- carry a None case that cannot happen.
    POSTGRES_URI: str = ""

    @field_validator("POSTGRES_URI", mode="before")
    @classmethod
    def validate_postgres_conn(cls, v: Optional[str], info: ValidationInfo) -> str:
        # Truthy, not isinstance: the unset default is now "" rather than None,
        # and an empty string has to fall through to be built like a missing one.
        if v:
            return v
        values: Dict[str, Any] = info.data
        password: SecretStr = values.get("POSTGRES_PASSWORD", SecretStr(""))
        return "{scheme}://{user}:{password}@{host}/{db}".format(
            scheme="postgresql+asyncpg",
            user=values.get("POSTGRES_USER"),
            password=password.get_secret_value(),
            host=values.get("POSTGRES_HOST"),
            db=values.get("POSTGRES_DB"),
        )

    FIRST_USER_EMAIL: EmailStr
    FIRST_USER_PASSWORD: SecretStr

    SECRET_KEY: Annotated[SecretStr, Field(min_length=HMAC_SHA256_MIN_KEY_BYTES)]
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # REDIS_HOST and REDIS_PORT live in app.core.redis.RedisConfig, which the
    # worker imports without this class and everything it requires.


# pydantic-settings populates every field from the environment, but mypy sees a
# no-argument call against a model whose fields are required and reports one
# `call-arg` per field. Neither the mypy nor the pydantic docs cover the case, so
# this takes mypy's documented route: ignore the one code, on the one line.
settings = Settings()  # type: ignore[call-arg]
