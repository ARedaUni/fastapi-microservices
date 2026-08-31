import pytest

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
