# FastAPI Microservices

[![CI](https://github.com/ARedaUni/fastapi-microservices/actions/workflows/ci.yaml/badge.svg)](https://github.com/ARedaUni/fastapi-microservices/actions/workflows/ci.yaml)

A template for a fully async FastAPI service — Postgres, a background worker,
JWT auth and Kubernetes manifests already wired together, so you start from a
running stack instead of an empty `main.py`.

Clone it, rename the service, delete what you don't need.

## Quickstart

Docker is the only prerequisite.

``` bash
cp .env.example .env
make up
```

That brings up Postgres, Redis, the API and the arq worker, runs the migrations
and seeds the first superuser. The API is on <http://localhost:8000>, the
interactive docs on <http://localhost:8000/api/docs>.

Log in as `admin@admin.com` / `password` (from `.env.example`) and you have a
bearer token:

``` bash
curl -X POST http://localhost:8000/api/v1/login/ \
  -d 'username=admin@admin.com&password=password'
```

`users/app` and `users/tests` are bind-mounted, so edits reload without a
rebuild. Change `users/requirements.txt` and you need `make up` again.

## What's in the box

| | |
|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | The API, on Python 3.13, async top to bottom |
| [SQLAlchemy 2.0](https://docs.sqlalchemy.org/) + [asyncpg](https://magicstack.github.io/asyncpg/) | Postgres access through the async engine |
| [Alembic](https://alembic.sqlalchemy.org/) | Schema migrations, run as their own release-phase step |
| [arq](https://arq-docs.helpmanual.io/) + [Redis](https://redis.io/) | Background jobs, in a worker that shares the image but not the config |
| [PyJWT](https://pyjwt.readthedocs.io/) + [bcrypt](https://github.com/pyca/bcrypt) | Token auth and password hashing, off the event loop |
| [pytest](https://docs.pytest.org/) + [ruff](https://docs.astral.sh/ruff/) + [mypy](https://mypy.readthedocs.io/) | The gates CI runs, all reproducible with `make` |
| [Tilt](https://tilt.dev/) | The Kubernetes dev loop, for when Compose isn't enough |

### Endpoints

Every route the template ships, and who may call it:

| Method | Path | Access |
|---|---|---|
| `POST` | `/api/v1/login/` | Public |
| `GET` | `/api/v1/home/` | Any authenticated user |
| `GET` | `/api/v1/home/another/` | Public — the deliberate counterexample |
| `GET` | `/api/v1/users/` | Superuser |
| `POST` | `/api/v1/users/` | Superuser |
| `GET` | `/api/v1/users/{user_id}/` | Self, or superuser for anyone else |
| `PUT` | `/api/v1/users/{user_id}/` | Superuser |
| `DELETE` | `/api/v1/users/{user_id}/` | Superuser, and never itself |
| `POST` | `/api/v1/tasks/` | **Public** — see [Before you deploy](#before-you-deploy) |
| `GET` | `/api/v1/tasks/{task_id}/` | **Public** — see [Before you deploy](#before-you-deploy) |
| `GET` | `/api/health/` | Public; `204` healthy, `503` when Postgres doesn't answer in 1s |

## Layout

``` text
users/                  one service; the plural name is the invitation to add more
├── app/
│   ├── api/            routers, split by version, plus the health probe
│   ├── core/           config, database engine, redis, security
│   ├── crud/           the generic async repository and its User binding
│   ├── models/         SQLAlchemy models
│   ├── schemas/        Pydantic request and response models
│   ├── main.py         app factory and lifespan
│   └── worker.py       arq WorkerSettings
├── migrations/         alembic, one revision to start from
├── tests/
└── Dockerfile          one image, three targets: prod, worker, dev
k8s/                    manifests, one file per service
scripts/                init-databases.sql -- one database per service
load/                   locust scenarios; `make load`, never started by `make up`
```

## Using it as a template

1. **Rename the service.** `users/` is a directory name, and it appears in
   `docker-compose.yml`, the `Tiltfile` and `k8s/*.yaml`. Nothing imports it —
   the Python package is `app`, which stays.
2. **Generate a real `SECRET_KEY`.** `openssl rand -hex 32`. The app refuses to
   start on a key shorter than 32 characters, so a placeholder fails loudly
   rather than silently signing weak tokens.
3. **Model your own tables.** Add them under `users/app/models/`, import them in
   `users/app/models/__init__.py` so Alembic sees them, then:

   ``` bash
   make migrations msg="add widgets"
   ```

   The migration lands in `users/migrations/versions/`. Read it before you
   commit it — autogenerate is a first draft, not an authority.
4. **Delete the demo surface.** `app/api/v1/home.py` and the `test_task` in
   `app/worker.py` exist to show the shape. They are not load-bearing.

### Adding a second service

1. **Give it a database first.** Two lines in `scripts/init-databases.sql`, and
   the same two in the `postgres-init` ConfigMap in `k8s/postgres.yaml`:

   ``` sql
   CREATE DATABASE orders;
   GRANT ALL PRIVILEGES ON DATABASE orders TO "user";
   ```

   One database per service, never shared. Two services in one database means
   two Alembic histories fighting over a single `alembic_version` table — and
   `make migrations` in either one autogenerating a `drop_table` for the
   other's tables, because they are absent from its metadata.
2. **Copy `users/`** to a sibling directory.
3. **Wire it up.** Build and target in `docker-compose.yml`; a
   `k8s/<name>.yaml` modelled on `k8s/users.yaml`, carrying its own
   `POSTGRES_DB` in its ConfigMap; its name in the `Tiltfile` `services` list.
4. **Trim the copy.** To verify tokens `users/` signed it needs `SECRET_KEY`
   and `get_token_data` from `app/api/deps.py` — not `models/users.py`,
   `crud/` or `security.py`. Verifying a JWT takes the key, not the user table,
   and a service that reaches into another's tables is not a second service.

The two share a Postgres *server* and Redis, and no data. Crossing a process
boundary should stay a deliberate act.

## Before you deploy

Honest limits. Each one is a decision the template defers to you, not a bug:

- **`/api/v1/tasks/` has no authentication.** Anyone who can reach the service
  can enqueue a job and read any job's result by id. Add
  `dependencies=[Depends(get_token_data)]` to the router, as
  `app/api/v1/home.py` does, before this is reachable from anywhere untrusted.
- **Passwords have no policy.** `UserCreate.password` is a bare `str`; an empty
  one is accepted. Add a `Field(min_length=...)` that matches your rules.
- **The checked-in secrets are examples.** `.env.example` and the `Secret` in
  `k8s/users.yaml` carry public values. Both say so; replace all of them.
- **The health probe only covers Postgres.** Redis being down does not fail it.
- **`init-databases.sql` runs once, against an empty data directory.** That is
  every `make up`, since Compose keeps no Postgres volume — but the cluster's
  PVC persists, so a database added after the first deploy needs a manual
  `CREATE DATABASE` or a fresh volume.
- **One replica, no HPA, no resource limits.** `k8s/` is a working development
  cluster, not a production topology.

## Kubernetes

For a cluster-shaped environment:

``` bash
minikube start
tilt up
```

Migrations and the first-superuser seed run as the `perform-migrations`
initContainer in `k8s/users.yaml`, which must exit 0 before the app container
starts. `docker-compose.yml` spells the same thing as a `migrate` service. Both
mean schema changes are release-phase, not something each replica redoes on
every restart — and a failing migration stops the deploy instead of booting the
app against the wrong schema.

## Development

| Command | What it does |
|---|---|
| `make up` | Build and start the stack, waiting for health |
| `make down` | Stop it |
| `make tests` | pytest inside the api container, with the coverage gate |
| `make lint` | `ruff check`, `ruff format --check`, `mypy` |
| `make format` | Fix what `ruff` can fix |
| `make migrations msg="..."` | Autogenerate a migration |
| `make logs` | Tail the api |
| `make shell` | Bash inside the api container |
| `make load` | Load-test the api; web UI on <http://localhost:8089> |
| `make load-headless` | Load-test and print percentiles, then exit |
| `make help` | This table, from the Makefile itself |

CI runs `make up`, `make lint` and `make tests` — the same three commands, on
the same stack. A green pipeline and a working laptop mean the same thing.

### Load testing

`load/locustfile.py` holds two user classes, and you pick one per run:

| Class | What it does | What it finds |
|---|---|---|
| `ReadUser` | Logs in once, then reads | The read ceiling |
| `LoginUser` | Nothing but logins, no think time | The bcrypt ceiling |

``` bash
make load                                      # web UI, pick the class there
make load-headless u=300 r=50 t=45s            # 300 users, 50/s ramp, 45 seconds
make load-headless class=LoginUser u=50 t=20s
```

The read mix is a ladder in database work per request — `/api/v1/home/` runs no
query, `/api/v1/users/{id}/` one, `/api/v1/users/` two — so a run says which
layer saturated, not only that latency rose.

Three things that would otherwise surprise you:

- **`make load-headless` exits non-zero when any request failed.** That is
  locust's own convention, and it makes the target usable as a gate. It is not
  the tooling breaking.
- **You are loading the `dev` target** — one uvicorn process with `--reload`.
  `prod` runs three workers, so these numbers are pessimistic for the read path.
- **The `locust` service sits behind a Compose profile**, so `make up` and CI
  never start it. `docker compose --profile load` is what reaches it.

## Credits

A fork of [Kludex/fastapi-microservices](https://github.com/Kludex/fastapi-microservices)
by Marcelo Trylesinski, itself inspired by
[tiangolo/full-stack-fastapi-postgresql](https://github.com/tiangolo/full-stack-fastapi-postgresql).
This fork brings it onto Python 3.13 and current dependencies, adds the Compose
dev loop, and covers the authorization rules with tests.

## License

MIT, © 2021 Marcelo Trylesinski. See [LICENSE.md](./LICENSE.md).
