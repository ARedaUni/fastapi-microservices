# The Second Service

`users/` is plural as an invitation. This is the decision about what accepts
it, why that one, and the staged build plan that follows.

**The decision: `bookings` — a service that sells seats for events.** Not
because ticketing is interesting, but because a seat is a *contended*
resource. Two people want the same one, exactly one may have it, and the
services that decide have to agree over a network that fails.

The domain is swappable. Gig tickets, cinema seats, train seats, gym class
slots — pick whichever you'll enjoy looking at. The criterion is contention,
and everything below survives the swap.

## Why the noun doesn't matter

Copy `users/` to `orders/`, give it its own database, wire it into
`docker-compose.yml` and the `Tiltfile`, and you have learned one thing: how
to copy a directory. Alembic, arq, the three Dockerfile targets and the
health probe are all already familiar. Two isolated CRUD apps that happen to
trust the same JWT are not a distributed system; they are one system deployed
twice.

The lessons only appear when two services must agree on something and one of
them is down. So the second service should be chosen for **the failure it
forces you to handle**, not for the table it owns.

## The candidates

| Second service | The boundary problem it creates | Verdict |
|---|---|---|
| `orders`, plain CRUD | None. Isolated writes, no shared decision. | Teaches nothing new |
| `catalog` / `products` | Read-heavy caching, a read model that lags | Real, but no contention and no consistency problem |
| `notifications` | Async fan-out, at-least-once delivery, idempotent consumers | Good lessons, wrong position — it's a *leaf*. Nothing waits on its answer, so its failures are invisible |
| `payments` | Idempotency keys, timeouts indistinguishable from failure | Excellent, but it is service **3**. It needs something to pay for |
| **`bookings`** | Two users, one seat. Holds that expire. Money that must not be taken for a seat you didn't get. | **Recommended** — every hard lesson falls out of one feature |

## What `bookings` forces you to confront

### 1. Two requests, one seat

There is exactly one correct outcome and your database is the only thing that
can enforce it. You will reach for a distributed lock in Redis, and then
discover Postgres already does it:

``` sql
CREATE UNIQUE INDEX one_live_claim_per_seat
    ON reservations (event_id, seat_id)
    WHERE status IN ('held', 'confirmed');
```

The loser gets an `IntegrityError` you translate to `409`. No lock, no lease,
no coordination service. Learning *why* that beats the lock — the constraint
is inside the transaction that writes the row, the lock is not — is worth more
than the feature.

### 2. A hold that expires

A seat reserved but unpaid must come back after ten minutes. That is what the
arq worker is for. Today `test_task` in `users/app/worker.py` sleeps for ten
seconds and returns a string; here the worker becomes load-bearing.

Then the real question arrives: what happens when the expiry job fires at the
same moment the payment confirms? Both read `status = 'held'`, both decide
they may proceed. The fix is a conditional update and a row count:

``` sql
UPDATE reservations SET status = 'confirmed'
 WHERE id = :id AND status = 'held';
```

Zero rows updated means someone else won — expire it, refund, or retry. This
one race is the most valuable thing on this page.

### 3. Identity without the user table

`bookings` verifies a token `users` signed. To do that it needs three things
out of `users/`, and nothing else:

| What it needs | Where it lives now |
|---|---|
| `SECRET_KEY` and `ALGORITHM` | `users/app/core/config.py`, `users/app/core/security.py` |
| `get_token_data` | `users/app/api/deps.py` |
| `TokenPayload` | `users/app/schemas/token.py` |

Not `crud/`, not `models/users.py`, not `security.py`'s bcrypt half.
Verifying an HS256 signature takes the key, not the user table — and a
service that reaches into another's tables is not a second service.

Then you will want the buyer's email for the confirmation, and the token
carries only `user_id` and `exp` (see `create_access_token`). You are now at
the actual fork in the road:

| Option | What you gain | What you now own |
|---|---|---|
| Call `users` over HTTP per request | Always current | `bookings` is down whenever `users` is down — a distributed monolith with extra latency |
| Copy the email into `bookings` at signup | No runtime coupling | A staleness problem, and a backfill for every existing user |
| Publish `UserRegistered`, keep a local projection | No runtime coupling, self-healing | An event bus, eventual consistency, and replay |

There is no right answer. Making that choice with a real cost attached is the
lesson; reading about it is not.

### 4. An honest third service

`payments` follows naturally: a fake gateway you make deliberately slow and
flaky. Now you have a saga — reserve seat, charge card, confirm booking —
and three things to learn from it:

- **Compensation.** The charge fails, so the seat must be released. There is
  no rollback across a network.
- **Idempotency.** The charge times out. You cannot tell "declined" from
  "succeeded but the response was lost". A client-supplied idempotency key on
  the charge is the only way to retry safely.
- **Reconciliation.** Some bookings will end up stuck anyway. A periodic job
  that finds and resolves them is not a failure of design; it is the design.

### 5. Failures you can actually demo

``` bash
docker compose stop payments
```

…mid-checkout, and watch what your system does. That is a feedback loop a
single service cannot give you, and it is the part that stays fun.

## The roadmap

| # | Service | Owns | The lesson it exists to teach |
|---|---|---|---|
| 1 | `users` ✅ | Accounts, login, token signing | Auth, the template |
| 2 | `bookings` | Events, seats, reservations | Contention, expiring holds, the identity boundary |
| 3 | `payments` | Charges, refunds | Idempotency, timeouts, compensation, sagas |
| 4 | `notifications` | Outbound email | Async consumers, at-least-once, dedupe |

**Stop at four.** A fifth service repeats a lesson you already paid for.

## Build order

Resist scaffolding all four. Each stage is small enough to finish and large
enough to teach something.

| Stage | Build | Done when |
|---|---|---|
| 1 | `bookings` with one table and `POST /reservations`, plus the partial unique index | Two concurrent `curl`s for the same seat return one `201` and one `409` |
| 2 | The arq expiry job | An unconfirmed hold is `released` after its TTL, and a test proves the confirm-vs-expire race resolves one way only |
| 3 | JWT verification, no user table | `bookings` accepts a token `users` signed and rejects one signed with a different key; `bookings` imports nothing from `users` |
| 4 | `payments`, deliberately flaky | Stopping `payments` mid-checkout releases the seat rather than stranding it |
| 5 | Idempotency keys on charge | Replaying the same charge request twice moves money once |
| 6 | Events and `notifications` | Killing `notifications` for a minute loses no confirmation email |

Stage 1 is a weekend and already contains the interesting race. Stage 4 is
where it stops being CRUD.

### Mechanically, per new service

The steps the [README](../README.md#adding-a-second-service) spells out, in
the order they must happen:

1. Its database, in `scripts/init-databases.sql` **and** the `postgres-init`
   ConfigMap in `k8s/postgres.yaml`:

   ``` sql
   CREATE DATABASE bookings;
   GRANT ALL PRIVILEGES ON DATABASE bookings TO "user";
   ```

2. A sibling directory, copied from `users/`, trimmed to what it needs.
3. Build and target in `docker-compose.yml`; `k8s/bookings.yaml` modelled on
   `k8s/users.yaml` with its own `POSTGRES_DB`; its name in the `Tiltfile`
   `services` list.

Compose keeps no Postgres volume, so `make up` re-runs the init script every
time. The cluster's PVC does persist — a database added after the first
deploy needs a manual `CREATE DATABASE` or a fresh volume.

## What this repo doesn't have yet

Four gaps, each of which should stay open until the pain arrives. The pain is
the teaching.

| Gap | When it starts hurting | What you'd add |
|---|---|---|
| No event bus | Service 4. `arq` is a job queue — one consumer per job, no fan-out | Redis Streams (already have Redis) or NATS |
| No outbox | The first time a booking confirms and no email goes out | An `outbox` table written in the same transaction, drained by a worker |
| No cross-service tracing | Service 3, the first "where did this request die?" | OpenTelemetry, trace ID propagated in headers |
| No contract tests | The first time `users` changes a token claim `bookings` reads | Schemathesis against the OpenAPI schema, or a pinned example payload both sides assert on |

## Honest limits

- **This is a learning roadmap, not a product plan.** Four services for a
  seat-booking system is more processes than the problem needs. A single
  FastAPI app with four routers would be the correct production answer, and
  saying so out loud is part of understanding microservices.
- **`payments` is a fake.** It should be. Do not wire a real gateway into a
  system whose purpose is to be broken on purpose.
- **The template's open ends still apply.** `/api/v1/tasks/` is unauthenticated,
  passwords have no policy, and the health probe only checks Postgres. Copying
  `users/` copies all three; see [Before you deploy](../README.md#before-you-deploy).

## What would change the recommendation

- **You want to practise read-scale rather than write-contention.** Then
  `catalog` with a cached read model is the better second service, and this
  page's roadmap does not apply.
- **You already know sagas and compensation.** Skip to an event-sourced
  `bookings` and spend the effort on projections and replay instead.
- **You want the fewest services that still teach something.** Build stages 1
  through 3 only. `bookings` alone, with its expiry race and its
  token-without-a-user-table boundary, is already more than most tutorials get to.
