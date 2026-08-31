# Modernization

Getting `users/` off Python 3.8 and onto current dependencies, without changing
what the service does.

## Where we are

| | |
|---|---|
| `c35cc1a` | Regression net: 19 authz tests, coverage 69.7% → 86.7%. Fixed `update_user` 500ing on a password-less `PUT`. |
| `eba7ae7` | Standalone bug fixes — no version changes. |
| *next* | The upgrade itself. |

## The upgrade lands as one change

Python, the test stack, Pydantic, SQLAlchemy, FastAPI, arq and the lint tools
move together. Not by preference — the version floors leave no green
intermediate state to stop at:

| Package | Latest | Requires |
|---|---|---|
| fastapi 0.141.1 | | `>=3.10` |
| pytest 9.1.1 | | `>=3.10` |
| alembic 1.19.1 | | `>=3.10` |
| pydantic-settings 2.15.0 | | `>=3.10` |
| mypy 2.3.1 | | `>=3.10` |

Python can't move to 3.13 while Pydantic stays at 1.10.13, which predates it.
The libraries can't move while Python stays at 3.8. Any ordering that tries to
split those produces a commit that doesn't build, so staging it more finely
would mean inventing stepping stones that can't be verified — worse than one
change that is green at both ends.

The suite from `c35cc1a` is what makes this safe to do in one go. It is the
reason phase 0 came first.

Two things stay separable, and should be their own commits inside the change:

- **The reformat.** Replacing black/isort/flake8/autoflake with ruff rewrites
  the tree. Landing it last, on its own, keeps it from burying the migration
  diff in whitespace.
- **The base image.** `tiangolo/uvicorn-gunicorn-fastapi` is archived, and it
  supplies `/start-reload.sh` and the `PRE_START_PATH` hook that runs
  `alembic upgrade head` and the `initial_data.py` seed. That seed is what the
  whole suite's `superuser_token_headers` depends on, so it needs an explicit
  new home before anything else can be verified.

## Decisions taken

Checked against PyPI on 2026-08-31; asyncpg and uvloop both ship cp313 and
cp314 wheels for amd64 and arm64, so the wheel availability that bit this repo
before is not a constraint now.

- **Python 3.13**, not 3.14 — wheels exist for both; 3.13 is the boring choice.
- **`python:3.13-slim` + uvicorn** replaces the archived base image. The seed
  moves to the `migrate` compose service, which already runs to completion
  before the API starts.
- **passlib → bcrypt 5.x directly.** passlib's last release was 2020 and is
  why `bcrypt` is pinned back to 4.0.1. Calling bcrypt is a few lines; it drops
  a dependency rather than swapping one.
- **python-jose → PyJWT.** Two call sites, and jose has the CVE history.
- **ruff** replaces black, isort, flake8 and autoflake — four upgrades become
  one tool.
- **Split dev and prod requirements.** Test dependencies currently ship in the
  production image.

## Deferred, deliberately

- **mypy config.** `follow_imports = skip` suppresses nearly everything today.
  Configuring it against Pydantic v1 code that becomes v2 is work done twice;
  it belongs with the lint change.
- **`Item`** — a model and a `lazy="selectin"` relationship with no schema,
  CRUD or endpoint, costing a join on every user read. A design call.
- **The worker's env boundary.** `app/worker.py` reads `os.getenv` directly and
  never imports `app.core.config`, which is the only reason the cluster's
  two-variable env doesn't fail validation at import. Fragile, but load-bearing.
- **bcrypt blocking the event loop** on every login.
- **`/api/v1/home/` doesn't check `is_active`.** It depends on `get_token_data`,
  which only decodes the JWT; the active check lives in `get_current_user`. A
  deactivated user's unexpired token still works there. Documented by a test
  rather than changed, since this pass changes no behavior.

## Verifying

```bash
cp .env.example .env
make up && make tests && make lint && make down
```

CI runs exactly these. The cluster path (`minikube start && tilt up`) is not in
CI and needs a manual check — including the `users-worker-service` deletion in
`eba7ae7`.
