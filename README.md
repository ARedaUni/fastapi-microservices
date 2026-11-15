# FastAPI Microservices

[![CI](https://github.com/ARedaUni/fastapi-microservices/actions/workflows/ci.yaml/badge.svg)](https://github.com/ARedaUni/fastapi-microservices/actions/workflows/ci.yaml)

A template for a fully async FastAPI service — Postgres, JWT auth and Kubernetes manifests already wired together, so you start from a
running stack instead of an empty `main.py`.

Clone it, rename the service, delete what you don't need.

## Quickstart

Docker, [minikube](https://minikube.sigs.k8s.io/), `kubectl` and
[Tilt](https://tilt.dev/) are the prerequisites.

``` bash
make cluster   # once
make up
```

That deploys `k8s/` with Tilt: Postgres, Redis, both services and `canvas`'
worker. Migrations and the seed run, and it waits until everything is ready.
Tilt's UI is on <http://localhost:10350>. The API is on <http://localhost:8000>, the
interactive docs on <http://localhost:8000/api/docs>.

Log in as `admin@admin.com` / `password` (from the Secret in `k8s/users.yaml`) and you have a
bearer token:

``` bash
curl -X POST http://localhost:8000/api/v1/login/ \
  -d 'username=admin@admin.com&password=password'
```

That token is good at `users` only. Add `&audience=canvas` for one that
`canvas` accepts, and that `users` then refuses.

Tilt syncs `app/` and `tests/` into the running pods, so edits reload without
a rebuild. Anything else in a service's directory, such as `requirements.txt` or
a migration, triggers a rebuild and redeploy on its own.

## What's in the box

| | |
|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | The API, on Python 3.13, async top to bottom |
| [SQLAlchemy 2.0](https://docs.sqlalchemy.org/) + [asyncpg](https://magicstack.github.io/asyncpg/) | Postgres access through the async engine |
| [Alembic](https://alembic.sqlalchemy.org/) | Schema migrations, run as their own release-phase step |
| [PyJWT](https://pyjwt.readthedocs.io/) + [bcrypt](https://github.com/pyca/bcrypt) | Token auth and password hashing, off the event loop |
| [pytest](https://docs.pytest.org/) + [ruff](https://docs.astral.sh/ruff/) + [mypy](https://mypy.readthedocs.io/) | The gates CI runs, all reproducible with `make` |
| [Tilt](https://tilt.dev/) | The dev loop: deploys `k8s/`, syncs code into the pods |

### Endpoints

<http://localhost:8000/api/docs> lists every route, generated from the code, so
it cannot drift. Who may call each one is tested in `users/tests/test_authz.py`.

## Layout

``` text
users/                  one service; the plural name is the invitation to add more
├── app/
│   ├── api/            routers, split by version, plus the health probe
│   ├── core/           config, database engine, keys, security
│   ├── crud/           the generic async repository and its User binding
│   ├── models/         SQLAlchemy models
│   ├── schemas/        Pydantic request and response models
│   └── main.py         app factory
├── migrations/         alembic, one revision to start from
├── tests/
└── Dockerfile          one image, two targets: prod, dev
k8s/                    manifests, one file per service
load/                   locust scenarios; `make load`, never started by `make up`
```

## Using it as a template

1. **Rename the service.** `users/` is a directory name, and it appears in
   the `Tiltfile` and `k8s/*.yaml`. Nothing imports it —
   the Python package is `app`, which stays.
2. **Generate a real signing key.** The value is base64 of a PEM, on one line:

   ```sh
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 | base64 | tr -d '\n'
   ```

   into `JWT_PRIVATE_KEY`. The `tr` is not optional: GNU `base64` wraps at 76
   columns, and the key is decoded with `validate=True`, which rejects the
   newlines. The app refuses to start on anything that is not a loadable RSA
   key, so a placeholder fails at boot rather than at the first login.
3. **Model your own tables.** Add them under `users/app/models/`, import them in
   `users/app/models/__init__.py` so Alembic sees them, then:

   ``` bash
   make migrations msg="add widgets"
   ```

   The migration lands in `users/migrations/versions/`. Read it before you
   commit it — autogenerate is a first draft, not an authority.
4. **Need background jobs?** `canvas/app/worker.py` is the arq worker to copy:
   one with a real job, rather than a demo kept around for its shape.

### Adding a second service

1. **Give it a database first.** Two lines in the `postgres-init` ConfigMap in
   `k8s/postgres.yaml`:

   ``` sql
   CREATE DATABASE orders;
   GRANT ALL PRIVILEGES ON DATABASE orders TO "user";
   ```

   One database per service, never shared. Two services in one database means
   two Alembic histories fighting over a single `alembic_version` table — and
   `make migrations` in either one autogenerating a `drop_table` for the
   other's tables, because they are absent from its metadata.
2. **Copy `users/`** to a sibling directory.
3. **Wire it up.** A `k8s/<name>.yaml` modelled on `k8s/users.yaml`, carrying
   its own `POSTGRES_DB` in its ConfigMap; its name and a `docker_build` in the
   `Tiltfile`.
4. **Trim the copy.** To verify tokens `users/` signed it needs `JWT_ISSUER`,
   `JWKS_URL` and roughly the thirty lines in `canvas/app/core/security.py` —
   not `models/users.py`, `crud/` or a signing key. Verifying a JWT takes a
   published public key, not the user table, and a service that reaches into
   another's tables is not a second service.
5. **Pin its own name as the audience.** Clients log in with
   `audience=<name>` and get a token only that service accepts. `users`
   needs no change: it keeps no list of services.

The two share a Postgres *server*, and no data. Crossing a process
boundary should stay a deliberate act.

## Before you deploy

Honest limits. Each one is a decision the template defers to you, not a bug:

- **Passwords have no policy.** `UserCreate.password` is a bare `str`; an empty
  one is accepted. Add a `Field(min_length=...)` that matches your rules.
- **The checked-in secrets are examples.** The Secrets in `k8s/users.yaml` and
  `k8s/postgres.yaml` carry public values. Replace all of them.
- **Any shape-valid audience is granted.** Login mints a token for whatever
  service name the client asks for, with no per-service policy ("only admins
  get `payments` tokens"). Add an allowlist to `login` the day one service
  needs to be harder to reach than another.
- **No refresh tokens, no revocation, no sessions, no MFA.** A token is live until
  `exp`; shortening `ACCESS_TOKEN_EXPIRE_MINUTES` is the only lever. Rotating
  the signing key invalidates every outstanding token at once, which is a
  blunt instrument, not a revocation list.
- **One signing key, and no rotation procedure.** The JWKS is a list so two
  keys *can* be live at once, but nothing here publishes a second one or ages
  the first out.
- **`postgres-init` runs once, against an empty data directory.** `make down`
  deletes the volume, so the next `make up` re-runs it; short of that, a
  database added later needs a manual `CREATE DATABASE`.
- **One replica, no HPA, no resource limits.** `k8s/` is a working development
  cluster, not a production topology.

## Kubernetes

There is no other way to run the stack: `k8s/` is the one description of
which processes exist, and Tilt is how they get to a cluster.

Migrations and the first-superuser seed run as the `perform-migrations`
initContainer in `k8s/users.yaml`, which must exit 0 before the app container
starts. That means schema changes are release-phase, not something each replica redoes on
every restart — and a failing migration stops the deploy instead of booting the
app against the wrong schema.

## Development

| Command | What it does |
|---|---|
| `make cluster` | Create the minikube cluster, once |
| `make up` | Deploy the stack with Tilt, waiting until it is ready |
| `make down` | Stop Tilt and delete what it deployed |
| `make tests` | pytest inside each service's pod, with the coverage gate |
| `make contract` | Cross-service tests: the two services still agree about a token |
| `make lint` | `ruff check`, `ruff format --check`, `mypy` |
| `make format` | Fix what `ruff` can fix |
| `make migrations msg="..."` | Autogenerate a migration; `svc=canvas` for the other service |
| `make logs` | Tail users |
| `make shell` | Bash inside the users pod |
| `make load` | Load-test users from inside the cluster; web UI on <http://localhost:8089> |
| `make load-headless` | Load-test and print percentiles, then exit |
| `make help` | This table, from the Makefile itself |

CI runs `make up`, `make lint`, `make tests` and `make contract` — the same four
commands, on the same stack. A green pipeline and a working laptop mean the same
thing.

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

The read mix is a ladder in database work per request — `/.well-known/jwks.json` runs no
query, `/api/v1/users/{id}/` one, `/api/v1/users/` two — so a run says which
layer saturated, not only that latency rose.

Three things that would otherwise surprise you:

- **`make load-headless` exits non-zero when any request failed.** That is
  locust's own convention, and it makes the target usable as a gate. It is not
  the tooling breaking.
- **You are loading the `dev` target** — one uvicorn process with `--reload`.
  `prod` runs three workers, so these numbers are pessimistic for the read path.
- **Locust runs inside the cluster**, held by Tilt until `make load` triggers
  it. Through a port-forward a run would measure kubectl's tunnel, not the
  service.

## Credits

A fork of [Kludex/fastapi-microservices](https://github.com/Kludex/fastapi-microservices)
by Marcelo Trylesinski, itself inspired by
[tiangolo/full-stack-fastapi-postgresql](https://github.com/tiangolo/full-stack-fastapi-postgresql).
This fork brings it onto Python 3.13 and current dependencies, adds the Tilt
dev loop, and covers the authorization rules with tests.

## License

MIT, © 2021 Marcelo Trylesinski. See [LICENSE.md](./LICENSE.md).
