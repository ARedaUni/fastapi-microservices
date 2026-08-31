# The Map

Four documents. Read them in order — each one is the foundation for the next.

| # | Document | Question it answers |
|---|---|---|
| 01 | [Frameworks Compared](./01-frameworks-compared.md) | What is a web framework *actually* doing, and how do FastAPI / NestJS / Hono / Express / Spring each answer it? |
| 02 | [Async & Lifecycles](./02-async-and-lifecycles.md) | What is an event loop really? Why is `async` viral? What is alive for how long, and who kills it? |
| 03 | [Architecture](./03-architecture.md) | Where does this codebase sit on the MVC → Layered → Hexagonal → Clean spectrum, and what would moving it cost/buy? |
| 04 | [Microservices](./04-microservices.md) | What actually changes when one service becomes two? A staged build plan. |

## The one idea that connects all four

> **Every design decision in a backend is a choice about a boundary: where it sits, what crosses it, and what happens when it fails.**

- **01** is about the boundary between *your code* and *the framework* (who calls whom, what metadata channel carries intent).
- **02** is about the boundary between *your code* and *the outside world* — every `await` is an I/O boundary, and every lifecycle hook is a boundary in time.
- **03** is about boundaries *inside* your process (layers, ports, adapters) — cheap to cross, cheap to move.
- **04** is about boundaries *between* processes — expensive to cross, nearly impossible to move, and they can fail independently.

The progression from 03 to 04 is the whole game: **a boundary you can't get right in-process will not get better once you put a network in the middle of it.**

## How to use these

Don't read them as reference material. Each one ends with **exercises against this repo**. The concepts only stick when you've hit the failure mode yourself.

The single highest-value habit: for every concept, ask *"what breaks if this is absent?"* Async makes no sense until you've blocked an event loop. Hexagonal makes no sense until you've tried to reuse a use-case from a worker and found it welded to `Request`.

## Where this repo actually is right now

An honest baseline, so you know what you're improving:

- **Architecture**: technically-layered (N-tier). Not hexagonal, not clean. No domain layer — business rules live in HTTP handlers.
- **Async**: correct in the SQLAlchemy layer, **incorrect in the password layer** (bcrypt blocks the event loop; see 02 §6).
- **Lifecycles**: uses the deprecated `add_event_handler` API and a module-global for the Redis pool.
- **Microservices**: zero. One service in a folder named as if there will be more.
- **Tests**: excellent fixture technique, ~2 happy-path tests, no coverage of the authorization logic.

All four are improvable, and each maps to one of the documents.
