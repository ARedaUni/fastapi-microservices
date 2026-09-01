"""Load generation for the users service.

`make load` for the web UI, `make load-headless` for a repeatable number.

The read mix is a ladder in database work per request, so a run tells you
which layer saturated first rather than just "it got slow":

| Endpoint              | Queries | What it measures                    |
|-----------------------|---------|-------------------------------------|
| `/api/v1/home/`       | 0       | event loop, routing, JWT decode     |
| `/api/v1/users/{id}/` | 1       | + one asyncpg round trip            |
| `/api/v1/users/`      | 2       | + the superuser check before the list |

`LoginUser` is deliberately a separate class. bcrypt is CPU work handed to a
thread pool, so it has its own ceiling -- see the comment on
`asyncio.to_thread` in `app/core/security.py` -- and mixing logins into a read
test only hides which wall you hit. Select one class per run.
"""

import os

from locust import HttpUser, between, constant, task
from locust.exception import StopUser

EMAIL = os.environ["FIRST_USER_EMAIL"]
PASSWORD = os.environ["FIRST_USER_PASSWORD"]


def get_token(client) -> str | None:
    """The access token, or None with the failure already recorded as a request.

    Locust counts a 4xx as a failure on its own, but not the missing token that
    follows it, so the caller gets None rather than a KeyError storm.
    """
    with client.post(
        "/api/v1/login/",
        data={"username": EMAIL, "password": PASSWORD},
        name="POST /api/v1/login/",
        catch_response=True,
    ) as response:
        if response.status_code != 200:
            response.failure(f"login returned {response.status_code}")
            return None
        return response.json()["access_token"]


class ReadUser(HttpUser):
    """Logs in once, then reads. The default class."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        token = get_token(self.client)
        if token is None:
            raise StopUser()
        self.client.headers["Authorization"] = f"Bearer {token}"

        # The seeded superuser's own id, so the per-id read hits a row that
        # exists without hardcoding 1.
        response = self.client.get("/api/v1/users/", name="GET /api/v1/users/")
        if response.status_code != 200 or not response.json():
            raise StopUser()
        self.user_id = response.json()[0]["id"]

    @task(10)
    def home(self) -> None:
        self.client.get("/api/v1/home/", name="GET /api/v1/home/")

    @task(5)
    def read_user(self) -> None:
        self.client.get(
            f"/api/v1/users/{self.user_id}/", name="GET /api/v1/users/{id}/"
        )

    @task(3)
    def read_users(self) -> None:
        self.client.get("/api/v1/users/", name="GET /api/v1/users/")

    @task(1)
    def health(self) -> None:
        self.client.get("/api/health/", name="GET /api/health/")


class LoginUser(HttpUser):
    """Nothing but logins, with no think time. Finds the bcrypt ceiling, which
    is a different number from the read ceiling."""

    wait_time = constant(0)

    @task
    def login(self) -> None:
        get_token(self.client)
