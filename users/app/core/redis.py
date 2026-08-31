from typing import Optional

from arq.connections import ArqRedis, RedisSettings
from pydantic_settings import BaseSettings


class RedisConfig(BaseSettings):
    """The redis connection on its own, so the worker can have it without the rest.

    app.core.config builds `Settings` at import and validates the database, the
    first-user credentials and the secret key -- none of which the arq worker
    uses. Keeping this here is what lets the worker's deployment carry two
    variables instead of the app's nine, deliberately rather than by accident.

    Required, not defaulted: a missing REDIS_HOST should stop the process, not
    quietly dial localhost inside a cluster.
    """

    REDIS_HOST: str
    REDIS_PORT: int

    def arq(self) -> RedisSettings:
        return RedisSettings(host=self.REDIS_HOST, port=self.REDIS_PORT)


redis_config = RedisConfig()  # type: ignore[call-arg]

pool: Optional[ArqRedis] = None


def get_pool() -> ArqRedis:
    """The pool, or a clear error instead of an AttributeError on None.

    `pool` is populated by the lifespan handler in app.main, so it is set for the
    whole time the app serves requests. Callers reaching it through here get a
    named failure if that ever stops being true.
    """
    if pool is None:
        raise RuntimeError("redis pool is not initialised")
    return pool
