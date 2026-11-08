from redis.exceptions import RedisError

from app.adapters.redis_publisher import get_instance as get_redis_publisher
from app.main import app

HEALTH = "/api/health/"


async def test_health_is_ok_when_postgres_and_redis_are_both_reachable(anonymous):
    """The probe canvas-api's own k8s readiness check hits -- both backing
    stores answered, so this pod is fit to receive traffic.
    """
    assert (await anonymous.get(HEALTH)).status_code == 204


async def test_health_reports_503_when_redis_is_unreachable(anonymous):
    """Postgres alone being up is not enough: stage 2 made Redis load-bearing
    for every claim, so a pod that cannot reach it is not actually ready.
    """

    class UnreachableRedis:
        async def ping(self) -> None:
            raise RedisError("connection refused")

    app.dependency_overrides[get_redis_publisher] = lambda: UnreachableRedis()

    assert (await anonymous.get(HEALTH)).status_code == 503
