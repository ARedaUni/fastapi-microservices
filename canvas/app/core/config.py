from typing import Any, Dict, Optional

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Trimmed from `users/`: this service owns tiles, not accounts.

    No FIRST_USER_*, and no SECRET_KEY yet -- stage 3 adds the key when this
    service starts verifying tokens `users` signed. Extra variables in the
    environment are ignored, which is why the shared .env can carry the users
    service's settings without this refusing to start.
    """

    PROJECT_NAME: str

    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_URI: str = ""

    @field_validator("POSTGRES_URI", mode="before")
    @classmethod
    def validate_postgres_conn(cls, v: Optional[str], info: ValidationInfo) -> str:
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


settings = Settings()  # type: ignore[call-arg]
