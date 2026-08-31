import pytest
from pydantic import ValidationError

from app.core import redis


def test_get_pool_raises_a_named_error_when_the_pool_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callers get a named error rather than an AttributeError on None.

    monkeypatch rather than asserting the global is already None: the lifespan
    handler sets `pool` and never clears it, so whether it is None here depends
    on whether an earlier test used the `client` fixture.
    """
    monkeypatch.setattr(redis, "pool", None)

    with pytest.raises(RuntimeError, match="not initialised"):
        redis.get_pool()


def test_redis_config_is_importable_without_the_app_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker needs redis and nothing else.

    app.core.config validates the database and the secret key at import, so a
    worker importing it would crash under the cluster's two-variable env. This
    is the guard on the boundary that keeps that true.
    """
    monkeypatch.setenv("REDIS_HOST", "redis-service")
    monkeypatch.setenv("REDIS_PORT", "6379")

    config = redis.RedisConfig()  # type: ignore[call-arg]

    assert config.REDIS_HOST == "redis-service"
    assert config.REDIS_PORT == 6379


def test_redis_config_requires_a_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail at startup rather than silently dialling localhost in a cluster."""
    monkeypatch.delenv("REDIS_HOST", raising=False)

    with pytest.raises(ValidationError):
        redis.RedisConfig()  # type: ignore[call-arg]
