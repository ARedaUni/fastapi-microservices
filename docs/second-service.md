# The Second Service

`users/` is plural as an invitation. This is the decision about what accepted
it, why that one, and the staged build plan that follows.

**The decision: `canvas` — a shared grid where every tile has exactly one
owner, r/place-shaped.** Not because pixel art is interesting, but because a
tile is a _contended_ resource. Two people want the same one, exactly one may
have it, and the services that decide have to agree over a network that
fails.

The grid is `GRID_SIZE × GRID_SIZE` (100×100 today — see
`canvas/app/models/claims.py`). The domain is swappable — seats, gig
tickets, gym slots would all teach the same core lesson — but canvas was
chosen over those because it adds two lessons a plain contended resource
doesn't: everyone has to _watch_ the grid change live, and claiming is
_rate-limited per person_, not just exclusive. Both are covered below.

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

| Second service         | The boundary problem it creates                                                                                           | Verdict                                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `orders`, plain CRUD   | None. Isolated writes, no shared decision.                                                                                | Teaches nothing new                                                                                                                                |
| `catalog` / `products` | Read-heavy caching, a read model that lags                                                                                | Real, but no contention and no consistency problem                                                                                                 |
| `notifications`        | Async fan-out, at-least-once delivery, idempotent consumers                                                               | Good lessons, wrong position — it's a _leaf_. Nothing waits on its answer, so its failures are invisible                                           |
| `payments`             | Idempotency keys, timeouts indistinguishable from failure                                                                 | Excellent, but it is service **3**. It needs something to pay for                                                                                  |
| **`canvas`**           | Two users, one tile. Holds that expire. Everyone else has to see the result live. A claim you didn't pay for must let go. | **Chosen** — every hard lesson falls out of one feature, plus realtime fan-out and per-user rate limiting that a seat booking wouldn't have forced |

## What `canvas` forces you to confront

### 1. Two requests, one tile

There is exactly one correct outcome and your database is the only thing that
can enforce it. You will reach for a distributed lock in Redis, and then
discover Postgres already does it — this is `canvas/app/models/claims.py`
today, not a proposal:

```sql
CREATE UNIQUE INDEX one_live_claim_per_tile
    ON claim (x, y)
    WHERE status IN ('held', 'confirmed');
```

The loser gets an `IntegrityError` you translate to `409` — see
`claim_tile` in `canvas/app/api/v1/claims.py`. No lock, no lease, no
coordination service. `canvas/tests/test_claims.py::test_two_concurrent_claims_for_one_tile_leave_one_winner`
proves it under real concurrency, not a mocked race. Learning _why_ this beats
the lock — the constraint is inside the transaction that writes the row, the
lock is not — is worth more than the feature. **Done.**

### 2. A hold that expires

A tile claimed but never confirmed must come back after `HOLD_MINUTES` (10
today). That is what the arq worker is for — `canvas` has no worker yet;
`status` already models `held` → `confirmed` / `released`, but nothing reads
`expires_at` and acts on it.

Then the real question arrives: what happens when the expiry job fires at the
same moment payment confirms the claim? Both read `status = 'held'`, both
decide they may proceed. The fix is a conditional update and a row count:

```sql
UPDATE claim SET status = 'confirmed'
 WHERE id = :id AND status = 'held';
```

Zero rows updated means someone else won — expire it, refund, or retry. This
one race is the most valuable thing on this page. **Not built.**

### 3. Watching it happen

`GET /api/v1/claims/` today is a poll — the client asks, the server answers
once. r/place's entire premise is that a claim made by a stranger appears on
_your_ screen without you asking. That's a different problem than contention:
fan-out, not exclusion.

The mechanical answer is a pub/sub channel — Redis Pub/Sub for "best effort,
lost if no one's listening," Redis Streams for "replay what you missed since
you reconnected" — with `claim_tile` publishing an event in the same
transaction it commits, and a WebSocket (or SSE) endpoint replaying it to
every connected client. The lesson underneath: a broadcast to N open
connections is not a database write, and a connection that's been open for an
hour needs its own answer to "is this client's auth still valid," because a
bearer token checked once at `connect` time doesn't get re-checked on every
frame the way an HTTP request does. **Not built** — tracked in the gaps table
below.

### 4. One claim per cooldown

The mechanic r/place is actually famous for: a user may place one tile, then
must wait. That's rate limiting, and it _looks_ like the same shape as
"two requests, one tile" but isn't — the resource being contended is a
timestamp keyed by user, not a row keyed by tile, so the partial-unique-index
trick doesn't apply. The standard answer is a sliding-window or token-bucket
counter in Redis (`INCR` + `EXPIRE`, or a Lua script when the check-and-set
needs to be atomic under concurrency — the same "don't check then act" lesson
as §1, solved with a different tool because the constraint isn't relational).

This one has a dependency the others don't: a cooldown keyed by user requires
a user identity that survives across requests, which means it can't be built
before §5. **Not built.**

### 5. Identity without a user table

`canvas` verifies a token someone else signed. `owner` used to be a free-text
string — anyone could type "ada" into the request body and claim a tile as
her. It is now the `sub` of a token `users` signed, and `canvas` holds no key
that could mint one. **Done** (stages 4a and 4b below). The decision behind it:

| Option                                                                                     | What you get                                                                                                                                                                | What you now own                                                                                                    |
| ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `users` keeps signing HS256, `canvas` verifies with the shared `SECRET_KEY`                | Fastest to build; already how `users`/`canvas` would talk today                                                                                                             | A shared secret every service must hold. With HMAC the key that verifies **is** the key that signs, so `canvas` could mint a token as any user |
| **`users` signs RS256 and publishes `/.well-known/jwks.json`** ← **chosen**                | The private key never leaves `users`; `canvas` holds a public key and can verify but not mint. Rotation becomes possible: two keys in the JWKS, sign with the new, drop the old | Token lifecycle — no refresh tokens, no revocation, no sessions unless you build them                               |
| A real IdP (Keycloak, Hanko, Zitadel) issues tokens; every service verifies against its JWKS | Rotation, revocation, MFA and passkeys for free, on a standard OIDC flow                                                                                                     | Standing infrastructure, and a login ceremony you cannot see inside                                                 |

**Decided: row 2, and built.** `users/app/core/keys.py` derives the `kid` as
an RFC 7638 thumbprint so a new key names itself; `canvas/app/core/security.py`
is thirty lines of `PyJWKClient` behind `asyncio.to_thread`, and knows only
`JWT_ISSUER`, `JWKS_URL` and the string `"canvas"`.

Row 3 was the stated plan for a while and is what a
workplace would pick. It was dropped for a specific reason: everything this
repo is here to teach lives on the *verifying* side of the boundary — a public
key instead of a shared secret, `iss` and `aud` so a token for one service is
not valid at another, a JWKS so keys can rotate without redeploying every
service, and `canvas` importing nothing from `users`. That side is identical
whether Keycloak signs the token or forty lines of PyJWT do. Buying an IdP buys
none of it, and costs a black box in the middle of the one thing being studied.

Row 1 is what the repo does today. Row 2 is about forty lines in `users/` and
thirty in `canvas`.

What row 2 does **not** buy, stated plainly: no refresh tokens, no revocation,
no MFA, and a login ceremony that is still a password. Acceptable here,
unacceptable in production — see
[Before you deploy](../README.md#before-you-deploy).

The escape hatch is the point, not a consolation. `canvas` only ever learns an
issuer URL and a JWKS URL, so row 3 stays available: point it at Hanko or
Zitadel later and `canvas` does not change a line. The same holds for the login
ceremony — replacing the password with passkeys via `py_webauthn` changes how a
human proves themselves inside `users/` without `canvas` noticing. Each swap
re-proves the boundary was drawn in the right place, which is better evidence
than getting it right first time.

Once identity exists, `owner` becomes the token's `sub` claim rather than
user-supplied text, and §4's cooldown key rides along with it.

### 6. An honest third service

`payments` follows naturally: a fake gateway you make deliberately slow and
flaky. A held tile is free; keeping it past the hold window means paying for
it — hold tile, charge card, confirm claim. Now you have a saga, and three
things to learn from it:

- **Compensation.** The charge fails, so the tile must be released. There is
  no rollback across a network.
- **Idempotency.** The charge times out. You cannot tell "declined" from
  "succeeded but the response was lost". A client-supplied idempotency key on
  the charge is the only way to retry safely.
- **Reconciliation.** Some claims will end up stuck anyway. A periodic job
  that finds and resolves them is not a failure of design; it is the design.

### 7. Failures you can actually demo

```bash
docker compose stop payments
```

…mid-claim, and watch what your system does. That is a feedback loop a
single service cannot give you, and it is the part that stays fun.

## The roadmap

| #   | Service               | Owns                           | The lesson it exists to teach                                                               |
| --- | --------------------- | ------------------------------ | ------------------------------------------------------------------------------------------- |
| 1   | `users` ✅            | Accounts, login, token signing | Auth, the template                                                                          |
| 2   | `canvas` — stage 1 ✅ | Tiles, claims                  | Contention, expiring holds, realtime fan-out, per-user rate limiting, the identity boundary |
| 3   | `payments`            | Charges, refunds               | Idempotency, timeouts, compensation, sagas                                                  |
| 4   | `notifications`       | Outbound email                 | Async consumers, at-least-once, dedupe                                                      |

**Stop at four.** A fifth service repeats a lesson you already paid for.
§5 keeps `users` as the signer rather than adding an IdP, so the count is
unchanged either way — swapping a signing algorithm now, or swapping in an IdP
later, changes a mechanism inside an existing service. Neither is a fifth.

## Build order

Resist scaffolding everything at once. Each stage is small enough to finish
and large enough to teach something.

| Stage | Build                                                                             | Done when                                                                                                                  |
| ----- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 1     | `canvas` with the `claim` table, `POST /api/v1/claims/`, the partial unique index | **✅ Done.** Two concurrent claims for one tile return one `201` and one `409` — `canvas/tests/test_claims.py`             |
| 2     | Realtime fan-out: publish on claim, a WebSocket/SSE endpoint replays it           | Two browser tabs on the canvas; a claim made in one appears in the other with no refresh                                   |
| 3     | The arq expiry job                                                                | An unconfirmed hold is `released` after `HOLD_MINUTES`, and a test proves the confirm-vs-expire race resolves one way only |
| 4     | Identity: `users` signs RS256, `canvas` verifies via JWKS — no user table (§5 decided) | `canvas` accepts a token `users` signed and rejects one signed with a different key; `canvas` imports nothing from `users` |
| 5     | Per-user cooldown on claims, backed by Redis                                      | Two claims from the same user inside the cooldown window: the second is `429`, not `201`                                   |
| 6     | `payments`, deliberately flaky                                                    | Stopping `payments` mid-claim releases the tile rather than stranding it                                                   |
| 7     | Idempotency keys on charge                                                        | Replaying the same charge request twice moves money once                                                                   |
| 8     | Events and `notifications`                                                        | Killing `notifications` for a minute loses no confirmation email                                                           |

Stage 1 is done and already contains the interesting race. Stage 6 is where
it stops being CRUD.

**The order actually taken is 4 first, then a page, then 2.** Stage 4 is pulled
forward because stage 5's cooldown key *is* the identity — 5 is blocked on 4 and
nothing else is, while 2 and 3 are blocked on nothing. The page is not on the
list above and earns its place anyway: it buys the thing neither 2 nor 3 does
alone, which is being able to see the canvas, log in, and take a tile in a
browser. Seeing it work is what makes the rest worth building.

| Stage | Build                                                        | Done when                                                                                                                          |
| ----- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| 4a    | `users` signs RS256 and publishes `/.well-known/jwks.json`   | **✅ Done.** `contract/test_users_publishes.py` — the token verifies against the published key and carries `iss`/`sub`/`aud`         |
| 4b    | `canvas` verifies that token; `owner` becomes its `sub`      | **✅ Done.** `contract/test_canvas_accepts.py` — no token → `401`, foreign key → `401`, valid → `201` with `owner` = `sub`           |
| 4c    | A static canvas page                                         | You open a browser, log in, click a tile, and it fills. It holds the token in JS — deliberately wrong, and why a BFF earns its place |

### Mechanically, per new service

Already done for `canvas` — `scripts/init-databases.sql` and
`k8s/postgres.yaml` both carry it, `docker-compose.yml` and the `Tiltfile`
both wire it, per the [README](../README.md#adding-a-second-service). The
same three steps apply to `payments` and `notifications` when their turn
comes:

1. Its database — two lines in `scripts/init-databases.sql` **and** the
   `postgres-init` ConfigMap in `k8s/postgres.yaml`.
2. A sibling directory, copied from `users/` or `canvas/`, trimmed to what
   it needs.
3. Build and target in `docker-compose.yml`; a `k8s/<name>.yaml` modelled on
   `k8s/canvas.yaml`, carrying its own `POSTGRES_DB`; its name in the
   `Tiltfile` `services` list.

Compose keeps no Postgres volume, so `make up` re-runs the init script every
time. The cluster's PVC does persist — a database added after the first
deploy needs a manual `CREATE DATABASE` or a fresh volume.

## What this repo doesn't have yet

Five open, one closed. Each should stay open until the pain arrives -- the
pain is the teaching, and stage 4 is what supplied it for the last row.

| Gap                                    | When it starts hurting                                                                   | What you'd add                                                                            |
| -------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| No realtime channel                    | The moment two people look at the canvas at once — this is the whole point of the domain | Redis Pub/Sub or Streams, published from `claim_tile`, replayed over WebSocket/SSE        |
| No rate limiting                       | The moment one user scripts a claim loop                                                 | A Redis counter or token bucket, keyed by the identity §5 introduces                      |
| No event bus for cross-service fan-out | Service 4 (`notifications`). `arq` is a job queue — one consumer per job, no fan-out     | Redis Streams (already have Redis) or NATS                                                |
| No outbox                              | The first time a claim confirms and no email goes out                                    | An `outbox` table written in the same transaction, drained by a worker                    |
| No cross-service tracing               | Service 3 (`payments`), the first "where did this request die?"                          | OpenTelemetry, trace ID propagated in headers                                             |
| ~~No contract tests~~ **closed**       | Arrived with stage 4 — two services now have to agree what a token is                     | `contract/`, run by `make contract`: two base URLs, a login form and RFC 7519, importing neither `app`                     |

## Honest limits

- **This is a learning roadmap, not a product plan.** Four services for a
  shared pixel canvas is more processes than the problem needs. A single
  FastAPI app with a few routers would be the correct production answer, and
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
  `canvas` and spend the effort on projections and replay instead.
- **You want the fewest services that still teach something.** Build stages 1
  through 3 only. `canvas` alone, with its expiry race and its realtime
  fan-out, is already more than most tutorials get to.
