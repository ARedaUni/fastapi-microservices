# Modernization

Getting `users/` off Python 3.8 and onto current dependencies, without changing
what the service does. **Done** — the service runs on Python 3.13.15 with
current pins, and the suite is green at both ends.

## What landed

| | |
|---|---|
| `c35cc1a` | Regression net: 19 authz tests, coverage 69.7% → 86.7%. Fixed `update_user` 500ing on a password-less `PUT`. |
| `eba7ae7` | Standalone bug fixes — no version changes. |
| `19222f2` | Pinned the 72-byte password truncation, the one behaviour passlib → bcrypt would have changed. |
| `fcd844c` | Base image: `python:3.13-slim` + uvicorn, one Dockerfile with prod/worker/dev targets. |
| `7e1fa45` | ruff replaces black, isort, flake8 and autoflake. |
| `0173ff5` | The upgrade: Python 3.13 and every dependency. |

## Why the upgrade is one commit

Python, the test stack, Pydantic, SQLAlchemy, FastAPI and arq move together.
Not by preference — the version floors leave no green intermediate state:

| Package | Version | Requires |
|---|---|---|
| fastapi | 0.141.1 | `>=3.10` |
| pytest | 9.1.1 | `>=3.10` |
| alembic | 1.19.1 | `>=3.10` |
| pydantic-settings | 2.15.0 | `>=3.10` |
| mypy | 2.3.1 | `>=3.10` |

Python can't move to 3.13 while Pydantic stays at 1.10.13, which predates it.
The libraries can't move while Python stays at 3.8. Any ordering that splits
those produces a commit that doesn't build.

The three commits either side of it *are* independently green, which is the
point of separating them: `fcd844c` swaps the base image while still on 3.8,
and `7e1fa45` reformats the tree before any code migration touches it.

**The reformat landed before the upgrade, not after** — a deviation from the
original plan, and the reason is worth keeping: black 22.3 and flake8 3.9 don't
run on Python 3.13. Carrying them through the upgrade would have forced an
intermediate bump to black 24+, whose style change reformats the tree anyway.
Either order keeps whitespace out of the migration diff; this order does it
with one reformat instead of two.

## Decisions taken

Checked against PyPI on 2026-08-31; asyncpg and uvloop both ship cp313 wheels
for amd64 and arm64, so the wheel availability that bit this repo before is not
a constraint now.

- **Python 3.13**, not 3.14 — wheels exist for both; 3.13 is the boring choice.
- **`python:3.13-slim` + uvicorn** replaces the archived
  `tiangolo/uvicorn-gunicorn-fastapi`. `--workers 3` in the prod CMD preserves
  the `WEB_CONCURRENCY=3` the old image defaulted to; uvicorn grew its own
  supervisor, so gunicorn stopped earning its place.
- **The seed moved to the migrate step.** It used to run from the base image's
  `PRE_START_PATH` hook, and the whole suite's `superuser_token_headers`
  depends on it. It now runs after `alembic upgrade head` in the compose
  `migrate` service and the k8s `perform-migrations` initContainer — which had
  to grow the app's full env, because `initial_data.py` imports
  `app.core.config` and that validates every setting at import.
- **One Dockerfile, three targets.** `prod` (uvicorn), `worker` (arq), `dev`
  (adds the test and lint tooling). Test dependencies no longer ship in the
  production image. `prod` is last so an untargeted build gets the lean one.
- **passlib → bcrypt 5 directly.** passlib's last release was 2020 and is why
  bcrypt was pinned back to 4.0.1.
- **python-jose → PyJWT.** Two call sites, and jose has the CVE history.
- **ruff** replaces black, isort, flake8 and autoflake.
- **`users/pyproject.toml`** absorbs `setup.cfg`, which is gone. Ruff, pytest,
  coverage and mypy config now sit next to the code they configure.

## What the upgrade forced in the code

- `BaseSettings` moved to **pydantic-settings**; `@validator(pre=True)` became
  `@field_validator(mode="before")`, and sibling values come off
  `ValidationInfo.data` instead of a `values` dict.
- **`TokenPayload.user_id` needed an explicit `= None`.** A bare `Optional` is
  required in Pydantic v2. Without the default every request 403s.
- **bcrypt 5 raises** `ValueError` on passwords over 72 bytes where passlib
  truncated silently, so `security.py` truncates explicitly. Hashes passlib
  wrote still verify — same `$2b$`, same 12 rounds — so deployed passwords keep
  working without a reset. Both halves are pinned by
  `test_a_password_longer_than_72_bytes_is_truncated`.
- SQLAlchemy 2.0: `async_sessionmaker`, `text()` around raw SQL,
  `as_declarative` from `sqlalchemy.orm`, and `async_engine_from_config` in the
  alembic env — wrapping a sync engine in `AsyncEngine` is no longer allowed.
- arq 0.28 dropped the unmaintained aioredis for redis-py, whose `close()` is
  the **deprecated sync shim**; `aclose()` is the coroutine. Shutdown now
  awaits it from a lifespan handler, replacing the `add_event_handler` pair.
- httpx 0.28 removed `AsyncClient(app=...)` in favour of `ASGITransport`;
  pytest-asyncio 1.4 removed the `event_loop` fixture. The session-wide loop
  that fixture was pinning is now declared in `pyproject.toml` — it still
  matters, because the engine is a module-level global whose pooled asyncpg
  connections must not outlive the loop that opened them.

## Verified

```bash
cp .env.example .env
make up && make tests && make lint && make down
```

22 passed, coverage 86.8%, ruff clean. Beyond the suite, which covers neither
the worker nor the production image:

- The arq worker executes a job end to end (enqueue → run → result) on
  uvloop 0.22 + arq 0.28 + Python 3.13.
- The `prod` image target boots uvicorn with 3 workers and serves
  `/api/health/`.
- Lifespan shutdown closes the redis pool cleanly.
- A hash written by passlib 1.7.4 / bcrypt 4.0.1 verifies under the new code.

The cluster path (`minikube start && tilt up`) is not in CI and still needs a
manual check — including the `users-worker-service` deletion in `eba7ae7` and
the seed's new home in the `perform-migrations` initContainer.

## Deferred, deliberately

- **mypy config.** Deferred out of this branch because configuring it against
  Pydantic v1 code that was about to become v2 meant doing the work twice.
  Done since: `follow_imports = "skip"` is gone, `make lint` runs mypy, and CI
  runs `make lint`.

- **SQLAlchemy 1.x `Column()` in the models.** The ORM moved to 2.0 here, but
  the models kept the 1.x declarative style, which tells a type checker
  nothing -- `user.hashed_password` typed as `Column[str]` rather than `str`.
  Done since: the models use `Mapped[]`/`mapped_column()` on a `DeclarativeBase`,
  `user.hashed_password` reveals as `str`, and all three `# type: ignore`s are
  gone. `alembic check` reports no drift, so the DDL is unchanged.
- **`Item`** — a model and a `lazy="selectin"` relationship with no schema,
  CRUD or endpoint. Done since: model, relationship and table are gone, in a
  reversible migration. The cost was a second round trip rather than a join —
  `selectin` emits its own `SELECT ... IN` — and a user read now emits one
  statement where it emitted two.
- **The worker's env boundary.** `app/worker.py` read `os.getenv` directly and
  never imported `app.core.config`, which was the only reason the cluster's
  two-variable env didn't fail validation at import. Done since: the redis
  connection is its own `RedisConfig` in `app.core.redis`, which both the worker
  and the app's lifespan handler use, so the small env is deliberate rather than
  accidental. The worker's `os.getenv` defaults are gone with it -- a missing
  `REDIS_HOST` now stops the process instead of quietly dialling localhost.
- **bcrypt blocking the event loop** on every login. Unchanged by the swap —
  passlib was blocking too.
- **`/api/v1/home/` doesn't check `is_active`.** It depends on
  `get_token_data`, which only decodes the JWT; the active check lives in
  `get_current_user`. A deactivated user's unexpired token still works there.
  Documented by a test rather than changed, since this pass changes no
  behaviour.
- **The dev `SECRET_KEY`.** PyJWT warned that the 6-byte `secret` in
  `.env.example` was below the 32-byte minimum for HS256. Done since:
  `Settings.SECRET_KEY` carries `min_length=32`, so a key that short stops the
  app at startup rather than warning once per token signed. The example values
  in `.env.example` and the k8s Secret are long enough to boot and obviously
  placeholders. The suite went from 48 warnings to none.
