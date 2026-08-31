from typing import Optional

from arq.connections import ArqRedis

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
