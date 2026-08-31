# 01 — Frameworks Compared

> Goal: stop memorising frameworks. Learn the **seven slots** every framework fills, then read any framework as a set of answers.

---

## 1. The seven slots

Every HTTP framework, in every language, solves the same seven problems. That's it. Once you can name the slots, a new framework takes an afternoon instead of a month.

| # | Slot | The question |
|---|---|---|
| 1 | **Transport adapter** | How do raw socket bytes become an object your code can read? |
| 2 | **Router** | How does `METHOD + path` select a handler? |
| 3 | **Interception** | How do you run cross-cutting logic around a handler? |
| 4 | **Dependency provision** | How does a handler get a DB session / current user / config? |
| 5 | **Validation & serialisation** | How does untrusted input become a typed value, and back out again? |
| 6 | **Lifecycle** | What is created when, and destroyed when? |
| 7 | **Composition** | How do routes and their collaborators group into features? |

And one meta-slot that determines the *feel* of everything else:

| | **Metadata channel** | How does the framework learn your intent — decorators, type hints, config, or plain code? |

That last one is the deepest fork in the road, so we start there.

---

## 2. The metadata channel — the real dividing line

A framework needs to know things about your handler that plain code doesn't say: *this param comes from the path, this one from the query, this returns 201, this requires a superuser.* How you tell it defines the framework's personality.

### Three answers

**(a) Decorators / annotations carry the metadata.** NestJS, Spring, ASP.NET.

```ts
@Controller('users')
export class UsersController {
  @Get(':id')
  @UseGuards(SuperuserGuard)
  findOne(@Param('id', ParseIntPipe) id: number) {}
}
```

The metadata is *attached to* the code. Requires a runtime reflection system — NestJS needs `reflect-metadata` and TypeScript's `emitDecoratorMetadata` to recover constructor parameter types, because TS types are erased at runtime.

**(b) The type annotations ARE the metadata.** FastAPI. This is the unusual one.

```python
@router.get("/{user_id}/", response_model=UserOut)
async def read_user(user_id: int, session: AsyncSession = Depends(get_session)):
```

`user_id: int` is simultaneously: the path parser, the validator, the coercion rule, the OpenAPI schema, and the editor's type. **One declaration, five jobs.** Python keeps annotations at runtime (`__annotations__`), so no reflection library is needed — introspection is native.

This is FastAPI's central bet, and it's why Pydantic is inseparable from it. It's also why FastAPI generates genuinely accurate OpenAPI for free while most frameworks require you to hand-write or decorate it.

**(c) No metadata channel — just code.** Hono, Express, Go, Koa.

```ts
app.get('/users/:id', superuserGuard, async (c) => {
  const id = Number(c.req.param('id'))
})
```

Nothing is implicit. You parse, you check, you return. Types come from TypeScript generics threaded through the call chain, not from a runtime system.

### The trade

| | Decorators | Type hints | Plain code |
|---|---|---|---|
| Boilerplate | low | lowest | highest |
| Magic / indirection | high | medium | none |
| Runtime cost | reflection at boot | introspection at boot | zero |
| Debuggability | "where did this 403 come from?" | "why did this dep run?" | trivial |
| Type/runtime drift | **possible** (types erased) | impossible (types *are* runtime) | possible (types erased) |
| Docs generation | needs extra decorators | free and accurate | manual or inferred |

> **The insight worth keeping:** in TypeScript, types vanish at runtime, so any runtime behaviour driven by "types" is actually driven by decorators or by a separately-declared schema (Zod). In Python, annotations survive, so the type *is* the schema. This single language difference explains most of the divergence between FastAPI and NestJS.

---

## 3. Slot 1 — Transport adapters

This is the layer people skip, and it's the one that explains the most.

### WSGI (Python, sync) — 2003

```python
def app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"hello"]
```

One synchronous callable. `environ` is a dict. Returns an iterable of bytes. **No websockets, no server-push, no startup/shutdown hook, no streaming request bodies.** Flask and (classic) Django are WSGI apps.

### ASGI (Python, async) — 2016

```python
async def app(scope, receive, send):
    ...
```

Three arguments:
- `scope` — a dict describing the connection. `scope["type"]` is `"http"`, `"websocket"`, or **`"lifespan"`**.
- `receive` — an async callable you await to get the next inbound event.
- `send` — an async callable you await to push an outbound event.

A minimal HTTP exchange in ASGI messages:

```
← receive() → {"type": "http.request", "body": b"...", "more_body": False}
→ send()    → {"type": "http.response.start", "status": 200, "headers": [...]}
→ send()    → {"type": "http.response.body", "body": b"hello"}
```

Two critical things follow from this design:

1. **`send` being called twice is why streaming works.** The response isn't a return value; it's a sequence of events. You can `send` a `http.response.body` with `more_body: True` a thousand times. Server-sent events, chunked transfer, and streaming LLM tokens are all just this.
2. **`scope["type"] == "lifespan"` is why FastAPI has startup/shutdown at all.** It's a *protocol-level* concept, not a framework feature. The server sends `lifespan.startup` before binding the socket and waits for `lifespan.startup.complete`. See doc 02 §7.

**Starlette** is the library that wraps this raw protocol into `Request`/`Response` objects, routing, and middleware. **FastAPI is Starlette plus Pydantic plus a DI system.** Read that again — it clarifies a lot of confusion:

```
FastAPI
├── Starlette      → routing, Request/Response, middleware, TestClient, websockets
├── Pydantic       → validation, serialisation, settings
├── Depends()      → dependency injection (FastAPI's own, not Starlette's)
└── OpenAPI gen    → derived from function signatures
```

When you read `from starlette.responses import Response` in `app/api/health.py:6`, that's the seam showing.

### The Fetch handler (Hono, Workers, Deno, Bun)

```ts
export default { fetch(request: Request): Response | Promise<Response> {} }
```

A pure function from a **Web Standard `Request`** to a **Web Standard `Response`**. The same `Request`/`Response` classes your browser has. This is the newest model and the most portable — Hono runs unchanged on Cloudflare Workers, Deno, Bun, Node, Vercel, Fastly, and Lambda because it only ever touches standard objects.

Compare the philosophies directly:

| | ASGI | Fetch handler |
|---|---|---|
| Shape | a **protocol** (event stream) | a **function** (value → value) |
| Streaming | explicit multi-`send` | `ReadableStream` in the body |
| Websockets | native (`scope["type"]`) | separate API (`WebSocketPair`) |
| Lifespan | native | **absent by design** |
| Mental model | "I am a connection handler" | "I am a pure-ish function" |

That "lifespan absent by design" is not an oversight — it follows from the deployment model. Workers have no guaranteed warm process, so there is nothing to hold a connection pool *in*. This is why Cloudflare sells Hyperdrive (external pooling) and why edge runtimes push you toward HTTP-based datastores. **Lifecycle design follows deployment model.** Remember that for doc 02.

### Node's `http` module

```js
http.createServer((req, res) => { res.end('hello') })
```

`req` is a `Readable` stream, `res` a `Writable`. Express wraps this and *mutates* both, adding `req.params`, `res.json()`, etc. That mutation-based extension is why Express has no useful types — anything can add anything to `req` at any time.

Structural note: **Node ships an HTTP server in its runtime; Python does not.** That's why Python needs Uvicorn/Hypercorn/Granian as a separate process, and why you see this in the Dockerfile:

```
uvicorn app.main:app --workers 3
   └─ uvicorn supervisor (process manager)
        └─ 3 × uvicorn worker (ASGI server: httptools + uvloop)
             └─ your app
```

Three processes, each with its own event loop, each with its own connection pool.
(This used to be `tiangolo/uvicorn-gunicorn-fastapi` wrapping gunicorn. That
image is archived; uvicorn grew its own `--workers` supervisor, so the extra
process manager stopped earning its place.) Node's equivalent is `cluster` / PM2, and it's an afterthought rather than the default.

### The servlet (Java) and thread-per-request

Spring MVC classically gives each request an OS thread. Simple to reason about (blocking code is fine!) but ~1MB stack per thread caps you around 10k threads. Spring's two escapes:
- **WebFlux + R2DBC** — go fully reactive. Same "colored function" pain as Python (doc 02 §5).
- **Project Loom virtual threads** (Boot 3.2+) — make threads so cheap that blocking is fine again. This is arguably the *better* answer, and neither Python nor JS has it. Go had it from day one with goroutines.

---

## 4. Slot 4 — Dependency provision (the biggest divergence)

This is where FastAPI is most misunderstood, especially by people coming from NestJS or Spring.

### FastAPI: `Depends()` is not an IoC container

```python
async def get_session():
    async with SessionLocal() as session:
        yield session

async def get_current_user(token = Depends(get_token_data), session = Depends(get_session)): ...
```

What it actually does:
- Resolves a **DAG of callables** per request, depth-first.
- **Caches** each callable's result for the duration of that request (so `get_session` runs once even though two branches ask for it).
- Treats a **generator** dependency as setup/teardown — everything before `yield` on the way in, everything after on the way out.

What it does **not** do:
- No constructor injection.
- No object graph built at boot.
- No interface → implementation binding.
- No singleton/transient/request scope configuration.

> **The key reframe: FastAPI's DI is a request-scoped resource provider with RAII semantics. It is closer to a `with` statement than to Spring's `ApplicationContext`.**

The generator form makes this obvious — `get_session` is literally a context manager wearing a dependency's clothes:

```python
async with SessionLocal() as session:   # ← acquire
    yield session                        # ← lend to the handler
                                         # ← release (implicit, on scope exit)
```

The consequence for architecture (doc 03): **`Depends()` is not a dependency-inversion mechanism.** You cannot use it to say "bind `UserRepository` to `SqlAlchemyUserRepository`" the way you would in Nest or Spring. The only inversion hook is `app.dependency_overrides`, and it exists for tests — you can see it in `tests/conftest.py:30`.

### NestJS: a real IoC container

```ts
@Injectable()
export class UsersService {
  constructor(
    @Inject('USER_REPOSITORY') private readonly repo: UserRepository,
  ) {}
}

@Module({
  providers: [
    UsersService,
    { provide: 'USER_REPOSITORY', useClass: SqlUserRepository },
  ],
})
```

- **Singleton by default.** One `UsersService` for the whole app lifetime.
- `Scope.REQUEST` and `Scope.TRANSIENT` are opt-in — and request scope is **contagious**: any provider that depends on a request-scoped one becomes request-scoped too, which is a real performance cliff.
- The `@Inject('USER_REPOSITORY')` string token exists because **TypeScript interfaces don't survive to runtime**. There's no `Type` object to use as a key, so you invent one. Spring doesn't need this — JVM generics/classes are reified enough to bind by interface type directly.

### The comparison

| | Mechanism | Default scope | Interface binding | Teardown |
|---|---|---|---|---|
| **FastAPI** | `Depends(callable)` at the call site | **request** | ✗ (only test overrides) | generator `yield` |
| **NestJS** | constructor injection, module `providers` | **singleton** | ✓ via tokens | `OnModuleDestroy` |
| **Spring** | constructor injection, component scan | **singleton** | ✓ by type | `@PreDestroy` |
| **Hono** | none — closures + `c.set()`/`c.get()` | manual | n/a | `try/finally` around `next()` |
| **Express** | none — `req.foo = bar` in middleware | manual | n/a | manual |
| **Go** | none — explicit construction or `wire` (compile-time) | manual | ✓ (interfaces are structural) | `defer` |

**The default-scope difference is the one to internalise.** FastAPI says "a dependency is a per-request thing" — which is why `get_session` is natural and a singleton service is awkward. Nest says "a dependency is an application-lifetime object" — which is why services are natural and per-request data is awkward. Neither is wrong; they're optimising different cases.

### Hono's answer, and why it's more like FastAPI than it looks

```ts
type Env = { Variables: { session: Session } }
const app = new Hono<Env>()

app.use(async (c, next) => {
  const session = await open()
  c.set('session', session)
  try { await next() } finally { await session.close() }
})

app.get('/users', (c) => { const s = c.get('session') })   // typed!
```

That middleware is **structurally identical** to `get_session`: acquire, lend, release. The onion `await next()` plays the role of `yield`. The difference is that Hono makes you write it and thread the type through a generic, where FastAPI infers it from the signature.

---

## 5. Slot 3 — Interception, and NestJS's five-way split

NestJS decomposes "run something around a handler" into five distinct concepts. This is genuinely useful vocabulary even if you never write Nest, because it names things FastAPI leaves unnamed.

Nest's execution order:

```
Request
  → Middleware        (Express-level, no DI context awareness)
  → Guards            (authz: return boolean → 403)
  → Interceptors      (pre)  (wrap, transform, cache, time)
  → Pipes             (validate + transform params)
  → ═══ HANDLER ═══
  → Interceptors      (post) (transform response)
  → Exception Filters (catch → HTTP response)
Response
```

The FastAPI translation:

| NestJS | FastAPI equivalent | In this repo |
|---|---|---|
| **Middleware** | ASGI / Starlette middleware | *none* |
| **Guard** | a `Depends()` that raises `HTTPException` | ✅ `on_superuser` (`api/deps.py:52`) |
| **Interceptor** | middleware, or a decorator | *none* |
| **Pipe** | a Pydantic model / typed param — automatic | ✅ `user_in: UserCreate` |
| **Exception Filter** | `@app.exception_handler(...)` | ❌ **missing** |

Two things fall out of this table immediately:

1. **`dependencies=[Depends(on_superuser)]` is exactly a Guard.** Run for side effects, discard the return, raise to reject. When you see that pattern in `api/v1/users.py:21`, you're looking at Nest's Guard implemented with the DI system instead of a dedicated concept. That's FastAPI's style throughout — *fewer concepts, each used for more things.*

2. **This repo has no exception filter layer, and that's a real gap.** The `update_user` bug (passing `None` to bcrypt) surfaces as a bare 500 with a stack trace. A domain-exception → HTTP-status mapping layer is one of the highest-value things you can add, and it becomes essential in doc 03 (a domain layer must raise domain errors, not `HTTPException`).

### Middleware shapes side by side

```python
# Starlette / ASGI — the raw form
class TimingMiddleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        # ... before
        await self.app(scope, receive, send)
        # ... after
```

```ts
// Hono / Koa — the onion
app.use(async (c, next) => {
  const start = Date.now()
  await next()                          // ← everything downstream happens here
  c.res.headers.set('X-Time', `${Date.now() - start}`)
})
```

```js
// Express — the linked list
app.use((req, res, next) => { next() })  // no await; you cannot "run after" easily
```

**Express's `next()` is not awaitable**, which is why "do something after the response" in Express requires hooking `res.on('finish')`. Koa invented the onion model specifically to fix this, and Hono inherited it. FastAPI/Starlette's `BaseHTTPMiddleware` gives you the onion shape too — but note it has known performance and streaming caveats; pure ASGI middleware is the escape hatch.

---

## 6. Slot 5 — Validation, and the direction of truth

Three libraries, three directions:

```python
# Pydantic — annotation IS the schema.  types ──→ runtime
class UserCreate(BaseModel):
    email: EmailStr
    password: str
```

```ts
// Zod — schema is the source, type is derived.  schema ──→ types
const UserCreate = z.object({ email: z.string().email(), password: z.string() })
type UserCreate = z.infer<typeof UserCreate>
```

```ts
// class-validator — decorators drive runtime, types are SEPARATE
class UserCreate {
  @IsEmail() email: string      // ← the decorator and the type can disagree
  @IsString() password: string
}
```

| | Source of truth | Can types & runtime drift? |
|---|---|---|
| Pydantic | the annotation | **No** — same declaration |
| Zod | the schema | **No** — type is inferred |
| class-validator | the decorator | **Yes** — nothing checks `@IsEmail` against `string` |

Pydantic and Zod arrive at the same guarantee from opposite ends. class-validator is the weak one, and it's why a lot of the Nest ecosystem has been migrating to Zod (`nestjs-zod`).

### "Parse, don't validate"

Both Pydantic and Zod follow this principle, and it's worth stating explicitly:

- **Validate** = check a value, return a boolean, keep using the original untrusted value.
- **Parse** = check a value and return a *new, differently-typed* value that carries the proof.

```python
UserCreate(**payload)   # returns a UserCreate, or raises. There is no "unvalidated UserCreate".
```

Once you hold a `UserCreate`, the fact that the email is well-formed is **encoded in the type**. You never re-check it. This is what makes the schema ladder in `app/schemas/user.py` powerful — see doc 03 §4.

### Serialisation direction

Watch how each framework gets data *out*:

- **FastAPI**: `response_model=UserOut` — the response is **filtered through** a schema. A field not on `UserOut` cannot escape, even if the object has it. This is a security property, not a convenience.
- **NestJS**: `ClassSerializerInterceptor` + `@Exclude()`/`@Expose()` — opt-out by default unless you enable `excludeExtraneousValues`.
- **Hono**: `c.json(obj)` — whatever you hand it. Safety is your problem.

FastAPI's outbound filtering is genuinely one of its best features and it's underappreciated. `app/api/v1/users.py:21` returns ORM `User` objects with `hashed_password` on them; `response_model=List[UserOut]` is what stops the hash from reaching the client.

---

## 7. Slot 7 — Composition & modularity

```python
# FastAPI — URL prefix trees, nothing more
router = APIRouter(prefix="/api")
router.include_router(v1_router)   # which itself includes home/login/tasks/users
```

```ts
// Hono — sub-apps mounted on a path
app.route('/api/v1', v1App)
```

```ts
// NestJS — a real module graph with ENCAPSULATION
@Module({
  imports: [AuthModule],
  controllers: [UsersController],
  providers: [UsersService, SqlUserRepository],
  exports: [UsersService],          // ← only this is visible to importers
})
export class UsersModule {}
```

**Only NestJS has encapsulation.** A provider not listed in `exports` is invisible outside its module — a compile-time-ish enforced boundary. FastAPI's `APIRouter` is *purely* URL grouping; it has no visibility rules whatsoever. Your only encapsulation in Python is the import system and social convention (`_private` naming).

This matters enormously for doc 03. In a modular monolith you *want* enforced boundaries between modules, and FastAPI gives you none. Your options:
- Discipline + code review.
- A linter rule (`import-linter` for Python can enforce "layer X may not import layer Y" — this is the pragmatic answer, and I'd recommend adding it to this repo).
- Actually splitting into packages/services.

Nest gets this for free; Python has to buy it.

---

## 8. The whole picture, one table

| Slot | FastAPI | NestJS | Hono | Express | Spring Boot |
|---|---|---|---|---|---|
| **Transport** | ASGI (via Uvicorn) | Express/Fastify adapter | Fetch API | Node `http` | Servlet / WebFlux |
| **Metadata** | type annotations | decorators + reflect-metadata | none (plain code) | none | annotations |
| **Router** | `APIRouter` prefix tree | `@Controller` + module graph | `app.route()` sub-apps | `express.Router()` | `@RequestMapping` |
| **Interception** | middleware + `Depends` | 5 kinds (mw/guard/interceptor/pipe/filter) | onion middleware | `(req,res,next)` | filters + AOP |
| **DI** | request-scoped callables | IoC container, singleton default | none (closures) | none | IoC container, singleton default |
| **Validation** | Pydantic (annotation-driven) | class-validator / Zod | Zod (opt-in) | none | Bean Validation |
| **Lifecycle** | ASGI lifespan | 5 module hooks | **none** (edge model) | manual | `ApplicationContext` |
| **Composition** | prefix grouping | modules **w/ encapsulation** | sub-apps | routers | packages + `@ComponentScan` |
| **Concurrency** | event loop (1 thread/proc) | event loop (1 thread) | event loop / isolate | event loop | thread-per-req or reactive or Loom |
| **API docs** | free & accurate | via `@nestjs/swagger` decorators | via `@hono/zod-openapi` | manual | via springdoc |

### Reading the table

Three clusters emerge:

1. **Batteries-included, container-driven** (NestJS, Spring) — heavy conventions, strong encapsulation, singleton services, great for large teams and long-lived enterprise code. Cost: indirection, boot-time magic, steep onboarding.

2. **Type-driven, moderate magic** (FastAPI) — a small set of concepts (`Depends`, Pydantic model, `APIRouter`) reused everywhere. Excellent single-service ergonomics, free accurate docs. Cost: no encapsulation, no true DI, architecture is entirely up to you.

3. **Minimal, explicit, portable** (Hono, Express, Go) — no magic, tiny runtime, runs anywhere. Cost: you write the wiring, and consistency depends on discipline.

**FastAPI's position is interesting**: it has *more* automation than Hono at the request boundary (validation, docs, serialisation) but *less* structure than Nest above the handler. It automates the edges and leaves the middle empty. That's why doc 03 matters so much — nothing in FastAPI will tell you where your business logic goes.

---

## 9. Mapping it back to this repo

Read these files and name the slot each one fills:

| File | Slot |
|---|---|
| `app/main.py` | 1 (transport wiring) + 6 (lifecycle) |
| `app/api/__init__.py`, `app/api/v1/__init__.py` | 2 + 7 (routing & composition) |
| `app/api/deps.py` | 4 (DI) + 3 (guards) |
| `app/schemas/*.py` | 5 (validation & serialisation) |
| `app/core/config.py` | 5 applied to the environment |
| `app/core/database.py`, `app/core/redis.py` | 6 (process- and lifespan-scoped resources) |
| `app/crud/`, `app/models/` | **none of the seven** — this is *your* code, not framework glue |

That last row is the point. Slots 1–7 are framework concerns. Everything interesting about your application lives *outside* them — and this repo has almost nothing there. That's the gap doc 03 fills.

---

## Exercises

1. **Rewrite `GET /api/v1/users/` in Hono + Zod**, in a scratch file. Nothing to deploy — just write it. Count what FastAPI did for you that you now do by hand (path parsing, validation, response filtering, OpenAPI, auth wiring). Then count what became *clearer* because it's explicit.

2. **Find the Guard.** Locate every place in `app/api/` that implements Nest's Guard concept. Then find the place that should have an Exception Filter and doesn't. (Hint: `app/api/v1/users.py:89`.)

3. **Prove the metadata channel.** Add `full_name: str` to `UserOut` and hit `/api/docs`. Observe that one annotation changed the validator, the serialiser, and the OpenAPI schema simultaneously. Then try to imagine doing the same in Express.

4. **Break the response filter.** Temporarily change `response_model=List[UserOut]` to nothing on `read_users` and hit the endpoint. Watch `hashed_password` appear in the JSON. That's slot 5 earning its keep.

---

**Next:** [02 — Async & Lifecycles](./02-async-and-lifecycles.md)
