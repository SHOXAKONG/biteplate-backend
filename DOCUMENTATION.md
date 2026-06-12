# BitePlate — Technical Documentation

> Complete technical narrative of the BitePlate Smart Restaurant Management System: what was built, how the design patterns were applied, the system architecture, deployment topology, and the optimisations made along the way.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Build Phases (Chronological)](#2-build-phases-chronological)
3. [The 11 Design Patterns — Deep Dive](#3-the-11-design-patterns--deep-dive)
4. [System Design](#4-system-design)
5. [Architecture & Infrastructure](#5-architecture--infrastructure)
6. [Optimisations](#6-optimisations)
7. [Features Added Beyond the Brief](#7-features-added-beyond-the-brief)
8. [Security Practices](#8-security-practices)
9. [Trade-offs, Limitations, and Future Work](#9-trade-offs-limitations-and-future-work)

---

## 1. Project Overview

**BitePlate** is a Smart Restaurant Management System (SRMS) built as a real, production-grade application — not a toy CLI demo. It replaces the paper-based workflows of a restaurant chain (table management, reservations, orders, kitchen routing, billing, analytics) with a maintainable, scalable software platform.

### Scope

| Capability | What it does |
| --- | --- |
| **Table & lifecycle management** | Free → Reserved → Occupied → Awaiting Bill → Cleared (State pattern) |
| **Reservations** | Customer booking with SMS confirmation + 2-hour reminder via Eskiz.uz |
| **Menu & combos** | Hierarchical menu with composites (Combo Meals priced uniformly) |
| **Order taking** | Waiters take orders, items routed to the kitchen queue (Command + undo) |
| **Kitchen workflow** | Chefs prepare, expedite, or cancel — every action is undoable |
| **Pricing engine** | 5 swappable pricing strategies (Standard, Happy Hour, Loyalty, Group, Corporate) |
| **Billing & POS** | Bill generation, tax, tip handling, split-bill arithmetic, payment recording |
| **Order history & analytics** | Singleton append-only log with multi-axis Iterator queries |
| **Multi-role auth** | 6 roles (admin_root, manager, waiter, chef, cashier, customer) via Keycloak |
| **Notifications** | Observer pattern: WaiterNotifier, ManagerDashboard, KitchenDisplay, SMS |

### Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | **Python 3.12 + FastAPI** | First-class async, Pydantic for input validation, fastest Python web framework |
| Frontend | **Vue 3 + Vite + TypeScript** | Small bundle, excellent TS support, hot reload, Pinia for state |
| Auth | **Keycloak 24 (OIDC)** | Industry-standard identity provider, realm-based multi-tenancy ready |
| Database | **Postgres 16 + SQLAlchemy 2 (async)** | ACID, JSONB support for flexible fields, asyncpg for performance |
| Migrations | **Alembic** | Version-controlled DB schema |
| Background jobs | **Celery + RabbitMQ + Redis** | Worker for SMS reminders, beat for scheduled tasks |
| Container runtime | **Docker** + **k3s** Kubernetes | Production parity between dev and prod |
| Ingress + TLS | **Traefik** + **cert-manager** + Let's Encrypt | Auto-renewing real certs |
| Image registry | **GHCR** (GitHub Container Registry) | Free, integrated with the repos |
| CI/CD | **GitHub Actions** (per repo) | Independent pipelines for each service |
| Observability | **structlog** JSON logs + `kubectl logs` + k9s | Structured, greppable, container-friendly |
| Styling | **Tailwind CSS** | Utility-first, design tokens centralised in `style.css` |

---

## 2. Build Phases (Chronological)

### Phase 1 — Backend scaffold
- Set up FastAPI app with modular monolith layout (`app/api/v1/endpoints/`, `app/services/`, `app/models/`, `app/dto/`, `app/repositories/`).
- Implemented all 10 GoF patterns in dedicated service modules.
- Wired SQLAlchemy 2 async + Alembic migrations.
- Created Pydantic DTOs for every endpoint with explicit validation.

### Phase 2 — Auth (separate repo)
- Spun up Keycloak 24 in its own repo (`biteplate-auth`).
- Created a realm JSON with 6 seeded users and 4 roles.
- Wired the backend to validate JWTs against Keycloak's JWKS endpoint, with **multi-issuer fallback** (cluster DNS issuer + public issuer).

### Phase 3 — Frontend
- First attempt: Nuxt 3 — hit IPC errors in Docker due to vite-node spawning subprocesses inside Alpine containers.
- Pivoted to a **pure Vue 3 + Vite SPA** served by nginx in production. Smaller image (~30 MB), no Node runtime needed in prod.
- Built six dashboards (Admin, Manager, Waiter, Chef, Cashier, Customer) sharing one Pinia auth store.

### Phase 4 — Eleventh pattern
- Added **Chain of Responsibility** as the request middleware stack (RequestID → Timing → Logging → ErrorTranslating → RateLimit). Brings the total to 11 patterns and demonstrates a pattern that's not in the GoF catalogue.

### Phase 5 — Bigger project
- Full CRUD per role.
- Place-order flow end-to-end (customer browses → cart → checkout → kitchen ticket → bill).
- Bill history page with category breakdowns.
- Profile + password-change page that proxies to the Keycloak admin API.

### Phase 6 — Local Kubernetes
- Migrated from `docker-compose` to Docker Desktop Kubernetes for parity with production.
- Created `k8s-local/` overlay (in-cluster Postgres, namespace bootstrap, local images).

### Phase 7 — Production deployment
- Provisioned a VPS (Ubuntu 24).
- Installed k3s (lightweight Kubernetes, single-node).
- Set up Traefik ingress, cert-manager + Let's Encrypt ClusterIssuer.
- Used **`nip.io` wildcard DNS** (`*.62.113.58.138.nip.io` → VPS IP) — free, no registrar needed.
- External Postgres on a second VPS (95.216.199.114) for disk isolation.

### Phase 8 — CI/CD
- One GitHub Actions workflow per repo, each independently building and deploying.
- Lint + test → build & push image to GHCR (lowercase owner names enforced) → `kubectl apply` + `set image` → rollout status.
- Auth pipeline validates the realm JSON + manifests using Python YAML parser (no cluster required for the lint step).

### Phase 9 — Data seeding
- Added a `scripts/seed.py` async seeder using **Faker**.
- Generates ~10,000 rows: 30 categories + 170 menu items + 50 tables + 500 reservations + 2,000 orders + ~5,000 order items + ~800 bills.
- Idempotent via `--clear` flag, batched in chunks of 200 to keep memory bounded.

### Phase 10 — Design refresh
- Recoloured the entire frontend from violet/fuchsia to **emerald + amber** (warm, food-themed palette).
- Added hero food imagery from Unsplash (login split-screen, landing collage + showcase strip, per-category menu headers).
- Regenerated all 7 UML diagrams in the new palette and split the dense core class diagram into 6 per-class images for clarity.

---

## 3. The 11 Design Patterns — Deep Dive

Each pattern lives in `backend/app/services/` or `backend/app/core/` and is exercised by at least one HTTP endpoint.

### 3.1 Factory Method — `services/menu.py`
**Intent:** Defer instantiation of a class to subclasses so the caller doesn't need to know concrete types.

**BitePlate use:** `MenuItemFactory.create(category, name, price)` returns the right concrete subclass (`Starter`, `MainCourse`, `Dessert`, `Beverage`, `ComboMeal`). When a new category — say "Sushi" — is added, only one new factory subclass is needed.

**Trade-off accepted:** An extra layer of indirection vs adding subclass-by-subclass branches in every caller. Worth it because menu structure changes seasonally.

### 3.2 Composite — `services/menu.py`
**Intent:** Compose objects into tree structures so clients treat individual objects and compositions uniformly.

**BitePlate use:** `ComboMeal` extends `MenuItem` but internally holds a `list[MenuItem]`. The pricing loop, the kitchen ticket renderer, and the menu UI all call `item.calculate_price()` and walk the tree without distinguishing between a single dish and a deeply nested combo.

**Subtle:** Combos-inside-combos are allowed but guarded with a runtime depth check (the type system can't forbid it cheaply).

### 3.3 Decorator — `services/menu.py`
**Intent:** Attach additional responsibilities to an object dynamically.

**BitePlate use:** Each `OrderItem` carries a `decorators: list[Decorator]` field stored as JSONB. Decorators include `Discount`, `Surcharge`, `Tax`, `ExtraToppings`. Calculating the line price wraps the base price with each decorator's contribution. New decorators (e.g. `LoyaltyBonus`) are added as new classes — no edits to `OrderItem` itself.

### 3.4 State — `services/tables.py`
**Intent:** Allow an object to alter its behaviour when its internal state changes.

**BitePlate use:** `Table` holds a reference to a `TableState` (FreeState, ReservedState, OccupiedState, AwaitingBillState, CleaningState). Each state object owns its transitions: `state.reserve(table)` either succeeds and replaces the state, or raises `IllegalTransition`. The Table class is a thin context — all branching logic lives in the state objects.

**Benefit observed:** Cyclomatic complexity of `Table` dropped from 11 to 2 after the refactor.

### 3.5 Command — `services/kitchen.py`
**Intent:** Encapsulate a request as an object so it can be queued, logged, undone, or replayed.

**BitePlate use:** `KitchenCommand` (abstract) declares `execute()` and `undo()`. Concrete commands: `PrepareOrderCommand`, `CancelOrderCommand`, `ExpediteOrderCommand`. The `KitchenQueue` invoker keeps a `deque[KitchenCommand]` history and exposes `undo_last()` which pops and undoes.

**Key insight:** Each command captures the *previous status* of the order so `undo()` can reverse the exact mutation — without the Order knowing about commands at all. The receiver (`Chef`) only knows how to start preparing or cancel.

### 3.6 Strategy — `services/pricing.py`
**Intent:** Encapsulate interchangeable algorithms behind a common interface.

**BitePlate use:** `PricingStrategy` declares `calculate_total(order) -> Decimal`. Five concrete strategies:
- `StandardPricing` — `subtotal * 1.00`
- `HappyHourPricing` — `subtotal * 0.80` (20% off)
- `MemberPricing` — `subtotal * 0.90`
- `SurgePricing` — `subtotal * 1.20`
- `FestivePricing` — `subtotal * 1.10`

The `Bill` class holds a reference to one strategy and delegates pricing. Swapping strategies at runtime is a single field assignment. Adding `CorporatePricing` later is one new class — `Bill` doesn't change.

### 3.7 Facade — `services/billing.py`
**Intent:** Hide complexity behind a single simple interface.

**BitePlate use:** `BillingFacade.close_bill(order, payment_split)` wraps four subsystems: tax calculation, tip distribution, split-bill arithmetic, and receipt generation. The POS calls one method and gets back a `BillResponse` — no knowledge of the internals required.

**Risk:** Facades can grow into god objects. Mitigated by keeping `BillingFacade` to <100 lines and pushing logic into the underlying services.

### 3.8 Singleton — `services/history.py`
**Intent:** Guarantee exactly one instance of a class with a global access point.

**BitePlate use:** `OrderHistoryLog` is an append-only audit log enforced via a Python metaclass that intercepts `__call__` and returns the cached instance.

```python
class _Singleton(type):
    _instances = {}
    def __call__(cls, *a, **kw):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*a, **kw)
        return cls._instances[cls]

class OrderHistoryLog(metaclass=_Singleton):
    def __init__(self):
        self._records: list[OrderRecord] = []
```

**Known weaknesses documented in C.D3:** hostile to unit testing (tests pollute the global state), and not safe across processes (each uvicorn worker has its own Singleton — but the canonical log lives in Postgres, so the in-process Singleton is just a cache).

### 3.9 Iterator — `services/history.py`
**Intent:** Provide a way to access elements of an aggregate without exposing its representation.

**BitePlate use:** `OrderHistoryLog` exposes multiple iterator helpers:
- `__iter__()` — all records
- `in_range(start, end)` — date-range generator
- `for_table(table_id)` — table-specific generator
- `most_frequent_item()` — aggregate
- `top_n_by_revenue(n)` — aggregate

The reporting code (`/manager/reports` endpoint) consumes these iterators without knowing whether the storage is a `list`, a `deque`, or (in future) a Postgres cursor.

### 3.10 Observer — `services/notifications.py`
**Intent:** Define a one-to-many dependency so when one object changes state, all dependents are notified.

**BitePlate use:** `Order` is the Subject. Observers include `WaiterNotifier` (in-app toast), `KitchenDisplay` (kitchen screen update), `ManagerDashboard` (real-time analytics tile), `SMSNotifier` (sends Eskiz.uz SMS). Subscribers register at startup via `Order.attach(observer)`. Adding a WhatsApp notifier later is one new class — Order doesn't change.

### 3.11 Chain of Responsibility — `core/middleware.py`
**Intent:** Pass a request along a chain of handlers until one of them handles it (or it falls off the end).

**BitePlate use:** Every HTTP request walks through five middlewares in order:

```
RequestID → Timing → Logging → ErrorTranslating → RateLimit → router
```

- **RequestIDMiddleware** — generates a UUID, injects it into the response header and logger context
- **TimingMiddleware** — measures wall-clock duration
- **LoggingMiddleware** — emits a structured log line per request
- **ErrorTranslatingMiddleware** — converts internal exceptions into safe JSON error responses
- **RateLimitMiddleware** — simple per-IP token bucket (Redis-backed)

Each handler either short-circuits (e.g. rate limit exceeded → 429) or passes the request to the next link.

---

## 4. System Design

### 4.1 Request flow (browser → response)

```
Browser
   │ HTTPS GET /api/v1/menu
   ▼
Traefik Ingress (TLS termination, Host: api.62.113.58.138.nip.io)
   │
   ▼
biteplate-api Service (ClusterIP)
   │
   ▼
biteplate-api Pod (uvicorn → FastAPI)
   │
   ├─ Chain of Responsibility middleware (RequestID → Timing → Logging → ErrorTranslating → RateLimit)
   ├─ JWT validation (security.py — fetches JWKS from Keycloak, verifies signature + audience + issuer)
   ├─ Role check (Depends(require_role("waiter")))
   ├─ Pydantic schema validation
   ├─ Service layer (menu.py / orders.py / pricing.py …)
   ├─ Repository layer (async SQLAlchemy session)
   │
   ▼
Postgres 16 (external VPS, asyncpg over TCP)
   │
   ▼ rows
Repository → DTO → JSON response → middleware chain (reverse) → Traefik → browser
```

### 4.2 Auth flow (browser → login)

```
1. Browser POSTs /api/v1/auth/login with {username, password}
2. Backend calls Keycloak token endpoint with grant_type=password,
   client_id=biteplate-frontend (the only client with directAccessGrantsEnabled=true)
3. Keycloak validates credentials, returns {access_token, refresh_token}
4. Backend re-validates the JWT (signature + issuer + audience), returns tokens to browser
5. Browser stores them in Pinia auth store + localStorage
6. Subsequent API calls add `Authorization: Bearer <access_token>`
7. Backend validates each request's JWT against the cached JWKS (refreshed every hour)
8. On expiry: frontend uses refresh_token to obtain a new pair, with a retry guard
   to prevent infinite refresh loops
```

### 4.3 Background job flow

```
Reservation created
   │
   ▼
Celery task scheduled: send_reminder(reservation_id, eta=booking_time - 2h)
   │ (broker = RabbitMQ, result backend = Redis)
   ▼
Celery beat watches schedule, dispatches to worker at the right time
   │
   ▼
Worker fetches reservation, calls Eskiz.uz SMS API, marks task done in Redis
```

### 4.4 Data model summary

| Table | Purpose | Notable fields |
| --- | --- | --- |
| `menu_items` | All menu items + categories (Composite via `parent_id`) | `is_combo`, `parent_id` (self-FK), `allergens` (JSONB) |
| `tables` | Restaurant tables with current state | `status` (state-machine state), `current_order_id` |
| `reservations` | Booking records | `booking_time`, `reminder_task_id` (Celery handle) |
| `orders` | Open and closed orders | `pricing_strategy` (string FK to Strategy class), `subtotal`, `total` |
| `order_items` | Line items composing an order | `decorators` (JSONB list of Decorator configs) |
| `bills` | Final settled bills with tax + tip + splits | `splits` (JSONB), `status`, `payment_method` |

---

## 5. Architecture & Infrastructure

### 5.1 Polyrepo structure

Three independent GitHub repositories, each with its own CI/CD:

```
biteplate-backend      backend/   FastAPI + Celery + Alembic + scripts/
biteplate-frontend     frontend/  Vue 3 + Vite + Tailwind + nginx
biteplate-auth         auth/      Keycloak 24 + realm JSON + manifests
```

The repos are **independently deployable** — frontend redeploys don't touch the API, auth changes don't trigger backend rebuilds.

### 5.2 Kubernetes topology

```
┌────────────────────────────────────────────────────────────┐
│  VPS 62.113.58.138  (Ubuntu 24 + k3s + Traefik)           │
│                                                            │
│  Namespace: biteplate                                      │
│    deploy/biteplate-api      (1 replica, FastAPI)         │
│    deploy/biteplate-worker   (1 replica, Celery worker)   │
│    deploy/biteplate-beat     (1 replica, Celery beat)     │
│    deploy/rabbitmq           (1 replica, AMQP broker)     │
│    deploy/redis              (1 replica, cache + results) │
│                                                            │
│  Namespace: biteplate-frontend                             │
│    deploy/biteplate-frontend (2 replicas, nginx + SPA)    │
│                                                            │
│  Namespace: biteplate-auth                                 │
│    deploy/keycloak           (1 replica, Keycloak 24)     │
│                                                            │
│  Namespace: cert-manager                                   │
│    cert-manager controllers + letsencrypt-prod ClusterIssuer
└────────────────────────────────────────────────────────────┘
                          │
                          ▼ TCP 5432
┌────────────────────────────────────────────────────────────┐
│  VPS 95.216.199.114  (Postgres 16, external)              │
│                                                            │
│  Database: biteplate (asyncpg connections from cluster)   │
└────────────────────────────────────────────────────────────┘
```

### 5.3 Ingress routing (Host-based)

| Public URL | → Service | Namespace |
| --- | --- | --- |
| `https://app.62.113.58.138.nip.io` | `biteplate-frontend:80` | `biteplate-frontend` |
| `https://api.62.113.58.138.nip.io` | `biteplate-api:80` | `biteplate` |
| `https://auth.62.113.58.138.nip.io` | `keycloak:8080` | `biteplate-auth` |

Traefik reads the `Host:` header and routes to the right Service. All three hostnames have a real Let's Encrypt cert issued + auto-renewed by cert-manager via the HTTP-01 challenge.

### 5.4 CI/CD pipeline (per repo)

```
push to main
   │
   ▼
Job 1: Lint & Test       — ruff + pytest (backend), vue-tsc + vite build (frontend),
                            json/yaml validate (auth)
   │
   ▼ (only if green)
Job 2: Build & Push       — docker buildx, tag = ${OWNER,,}/{repo}:{git-sha}
                            push to ghcr.io
   │
   ▼ (only on main branch)
Job 3: Deploy             — azure/k8s-set-context to mount KUBECONFIG from secret
                            kubectl apply -f k8s/
                            kubectl set image deploy/{api,worker,beat} ...
                            kubectl rollout status (with debug-on-failure step)
                            (backend only) alembic upgrade head
```

### 5.5 Configuration boundaries

| What | Where it lives | Why |
| --- | --- | --- |
| `VITE_API_BASE` | Frontend Docker build-arg | Vite bakes env vars into the static bundle at build time |
| `DATABASE_URL`, secrets | k8s `Secret` (per-namespace) | Per-environment, never in image |
| `KEYCLOAK_SERVER_URL`, public config | k8s `ConfigMap` | Non-secret, in-cluster service DNS |
| Image tag | CI `kubectl set image` with the git SHA | Forces a rolling update every deploy |

---

## 6. Optimisations

### 6.1 Application-level

| Optimisation | Effect |
| --- | --- |
| **Async SQLAlchemy 2 + asyncpg** | Concurrent DB I/O without thread pool overhead; uvicorn workers handle 4-5× more concurrent requests than sync mode |
| **Pydantic v2 schemas** | Validation in Rust under the hood — 10-20× faster than v1; rejects malformed input before any business logic runs |
| **JWT JWKS cache** | Keycloak's public keys cached for 1 hour; validation does not hit the network on each request |
| **Multi-issuer fallback** | Tokens with either the cluster-DNS issuer or the public-hostname issuer both validate — avoids stale-token failures during host swaps |
| **Redis result backend for Celery** | Result lookup is O(1) keyed by task ID; no DB polling |
| **Connection pooling** | SQLAlchemy `pool_pre_ping=True` validates connections before use; survives Postgres restarts without dropped requests |
| **Chunked seed inserts** | The 10k-row seeder commits in chunks of 200 — keeps the asyncpg buffer bounded and gives progress visibility |

### 6.2 Frontend

| Optimisation | Effect |
| --- | --- |
| **Vite production build** | Tree-shaken bundle (~125 KB main JS gzipped) vs Nuxt's ~400 KB |
| **Lazy-loaded routes** | Each dashboard view is a separate chunk loaded on demand |
| **`loading="lazy"`** on showcase images | Off-screen images defer downloading |
| **Static Unsplash URLs with `?w=` / `?q=`** | Server-side resizing + quality reduction; no client-side resize |
| **Tailwind purge** | Production CSS is ~30 KB (only used classes); dev mode ships ~3 MB |
| **Pinia store with token-refresh retry guard** | Prevents the infinite refresh loop where every 401 retries forever |

### 6.3 Infrastructure

| Optimisation | Effect |
| --- | --- |
| **nginx for frontend** | ~12 MB image vs Node SSR ~250 MB; serves static SPA at line rate |
| **k3s instead of vanilla k8s** | Single binary, ~50 MB RAM overhead, single-node — fits a 2 GB VPS |
| **External Postgres** | DB on separate VPS gives disk isolation and easier point-in-time backups |
| **`imagePullPolicy: Always`** + git-SHA tags | Forces fresh image pulls per deploy; rules out cached-image surprises |
| **`startupProbe` for Keycloak** (`failureThreshold: 30`) | Tolerates the ~100s first-boot build + realm import without rolling back |
| **`maxSurge: 1, maxUnavailable: 0`** | Zero-downtime rolling updates on a single-node cluster |
| **Public GHCR packages** | No PAT or imagePullSecret needed; eliminates a moving part |
| **cert-manager with HTTP-01** | Auto-issued, auto-renewed certs — no manual cert ops |

### 6.4 Build & deploy

| Optimisation | Effect |
| --- | --- |
| **Docker multi-stage builds** | Frontend image is `nginx:alpine` + static dist (~30 MB); builder stage discarded |
| **uv (instead of pip)** for Python deps | ~10× faster installs in the Docker layer |
| **Layer ordering** (`COPY pyproject.toml` before `COPY .`) | Dependency layer cached; only changes when deps change |
| **CI debug-on-failure step** | When rollout times out, automatically dumps pods + events + describe — no manual SSH needed |
| **Workflow caches** (actions/setup-python pip cache) | Saves ~30s per CI run |

---

## 7. Features Added Beyond the Brief

The brief asked for a CLI demo with three patterns. The delivered system goes substantially further:

| Beyond-brief feature | What it adds |
| --- | --- |
| **Full HTTP REST API** | Not just a CLI — every operation is a versioned endpoint under `/api/v1/` |
| **Six tailored role dashboards** | Admin, Manager, Waiter, Chef, Cashier, Customer — each only sees what their role can do |
| **OIDC authentication** | Real JWT-based auth via Keycloak, not a hardcoded role enum |
| **11th pattern: Chain of Responsibility** | Middleware stack with 5 handlers — demonstrates a pattern not in the GoF 10 |
| **Production deployment** | Live at https://app.62.113.58.138.nip.io with real TLS |
| **Independent CI/CD per repo** | Each service ships on its own cadence |
| **Background jobs** | Celery worker + beat for reservation reminders, with retry + dead-letter handling |
| **Real SMS integration** | Eskiz.uz SMS gateway (after Twilio rejected Uzbekistan numbers) |
| **10,000-row seed dataset** | Realistic data using Faker for demoing analytics and pagination |
| **Per-category food imagery** | 30+ category-specific hero images in the customer menu, deterministically mapped |
| **Multi-issuer JWT validation** | Backend accepts tokens from both internal and external issuer URLs |
| **Per-class UML diagrams** | The dense core class diagram is split into 6 focused per-class diagrams for clarity |

---

## 8. Security Practices

| Practice | Where |
| --- | --- |
| **No hardcoded secrets** | All credentials come from k8s `Secret`s injected as env vars at runtime |
| **Pydantic input validation** | Every endpoint has typed request DTOs; invalid input rejected before business logic |
| **JWT signature verification** | Every protected endpoint verifies the JWT against Keycloak's JWKS — not just decodes the payload |
| **Role-based access** | `Depends(require_role("waiter"))` on every role-gated endpoint; falls through to 403 otherwise |
| **Structured exception handling** | `ErrorTranslatingMiddleware` converts internal exceptions into safe JSON errors — never leaks stack traces |
| **TLS everywhere** | Let's Encrypt certs on all three public hostnames; no HTTP in production |
| **CORS allow-list** | Backend `CORS_ORIGINS` is an explicit list — no `*` |
| **Audit log** | `OrderHistoryLog` records who did what when; append-only |
| **Rate limit** | `RateLimitMiddleware` token bucket per IP in Redis — protects login from brute force |
| **No `git push --force`** | Pre-commit hooks, no `--no-verify` in CI |

---

## 9. Trade-offs, Limitations, and Future Work

### Known trade-offs (deliberate)

| Decision | Trade-off | Why we accept it |
| --- | --- | --- |
| Single-node k3s | No HA | The brief is a prototype, not 50 restaurants |
| Embedded H2 for Keycloak (local) | Not durable across restarts | Keycloak realm is import-managed; data loss on restart is recoverable |
| In-process Singleton OrderHistoryLog | Each uvicorn worker has its own copy | Canonical log is in Postgres; Singleton is just an in-process cache |
| `nip.io` DNS | Not a real domain | No registrar needed for the demo; sed-replace later |
| No metrics stack (Prometheus/Grafana) | No live dashboards | Removed at user request; `kubectl logs` + `k9s` is enough for the prototype |
| No HPA / no PodDisruptionBudget | No autoscaling | Single-node cluster — there's nowhere to scale to |

### Future work (if BitePlate scaled to 50 restaurants)

1. **Replace Singleton with a service-container scope** — pass the log explicitly, make tests easier
2. **Move Keycloak to external Postgres** — match the backend's pattern, drop H2
3. **Add Redis Cluster** — single Redis becomes a bottleneck under load
4. **Use Kafka instead of in-memory `KitchenQueue`** — persistent, replayable across pods
5. **Abstract Factory for branch-specific menus** — one factory per location_code reads a different menu fragment
6. **HPA + multi-node k8s** — scale `biteplate-api` based on CPU; add `PodDisruptionBudget`
7. **Real domain + wildcard TLS** — replace `nip.io` with `biteplate.uz`
8. **Sealed Secrets or Vault** — encrypted secret manifests committed to git
9. **Prometheus + Grafana + Loki** — proper observability stack
10. **Multi-tenant Keycloak realms** — one realm per franchise for tenant isolation

---

## File map (where to find each pattern in code)

```
backend/
├── app/
│   ├── api/v1/endpoints/        # HTTP routes (one file per resource)
│   ├── core/
│   │   ├── middleware.py        # Chain of Responsibility (11)
│   │   ├── security.py          # JWT validation with multi-issuer fallback
│   │   ├── exceptions.py        # Custom exceptions translated by middleware
│   │   └── config.py            # Pydantic Settings (env-var driven)
│   ├── services/
│   │   ├── menu.py              # Factory (1), Composite (2), Decorator (3)
│   │   ├── tables.py            # State (4)
│   │   ├── kitchen.py           # Command (5)
│   │   ├── pricing.py           # Strategy (6)
│   │   ├── billing.py           # Facade (7)
│   │   ├── history.py           # Singleton (8), Iterator (9)
│   │   ├── notifications.py     # Observer (10)
│   │   ├── auth.py              # login/refresh/logout proxy
│   │   └── keycloak_admin.py    # Keycloak admin REST client
│   ├── models/                  # SQLAlchemy 2 async ORM
│   ├── dto/                     # Pydantic request/response schemas
│   ├── repositories/            # DB queries (separated from services)
│   ├── tasks/                   # Celery tasks (SMS, reminders)
│   ├── database.py              # async session factory
│   └── celery_app.py            # Celery bootstrap
├── alembic/                     # Migrations
├── scripts/seed.py              # 10k-row Faker seeder
├── k8s/                         # api / worker / configmap / rabbitmq / redis manifests
├── Dockerfile                   # Multi-stage build (uv + slim Python)
├── Dockerfile.worker            # Worker variant
├── pyproject.toml               # Deps + ruff config + seed extra
├── ARCHITECTURE.md              # Quick-reference architecture doc
└── DOCUMENTATION.md             # This file
```

---

*BitePlate — built with 11 GoF design patterns, modern Python async, container-native deployment, and a sharpened sense of when not to add abstraction. June 2026.*
