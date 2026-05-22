# BitePlate — Architecture

A Smart Restaurant Management System demonstrating **11 GoF design patterns** (the canonical 10 plus Chain of Responsibility middleware). Built as a polyrepo of three independent services, deployed via per-repo CI/CD pipelines to a single Kubernetes cluster behind a managed reverse proxy with Let's Encrypt TLS.

---

## 1. Component map

```
                                  ┌─────────────────────────────────────────┐
                                  │            Internet (browser)           │
                                  └────────────────────┬────────────────────┘
                                                       │ HTTPS :443
                                                       ▼
                            ┌──────────────────────────────────────────────┐
                            │  VPS  62.113.58.138  (Ubuntu 24 + k3s)       │
                            │                                              │
                            │  ┌────────────────────────────────────────┐  │
                            │  │ Traefik Ingress (routes by Host:)      │  │
                            │  └─┬─────────────────┬──────────────────┬─┘  │
                            │    │ app.<nip.io>    │ api.<nip.io>     │ auth.<nip.io>
                            │    ▼                 ▼                  ▼    │
                            │  ┌───────────┐  ┌──────────┐  ┌─────────────┐│
                            │  │ Frontend  │  │ Backend  │  │  Keycloak   ││
                            │  │   nginx   │  │ FastAPI  │  │     24      ││
                            │  │ Vue + Vite│  │ uvicorn  │  │ (H2 embed.) ││
                            │  │ namespace │  │ namespace│  │ namespace   ││
                            │  │ biteplate-│  │ biteplate│  │ biteplate-  ││
                            │  │ frontend  │  │          │  │ auth        ││
                            │  └───────────┘  └────┬─────┘  └─────────────┘│
                            │                      │                       │
                            │  ┌───────────┐  ┌────▼─────┐                 │
                            │  │  Redis    │◄─┤ Celery   │                 │
                            │  └───────────┘  │ Worker + │                 │
                            │  ┌───────────┐  │  Beat    │                 │
                            │  │ RabbitMQ  │◄─┤(in-ns)   │                 │
                            │  └───────────┘  └──────────┘                 │
                            │                                              │
                            │  cert-manager (issues Let's Encrypt certs)   │
                            └──────────────────┬───────────────────────────┘
                                               │ TCP :5432
                                               ▼
                            ┌──────────────────────────────────────────────┐
                            │   Postgres VPS  95.216.199.114  (Ubuntu)     │
                            │   postgres 16 — database `biteplate`         │
                            └──────────────────────────────────────────────┘
```

---

## 2. Three repos, three pipelines

| Repo                              | Stack                            | Image registry                                    | Deploy target                  |
| --------------------------------- | -------------------------------- | ------------------------------------------------- | ------------------------------ |
| `SHOXAKONG/biteplate-backend`     | FastAPI + Celery + Alembic       | `ghcr.io/shoxakong/biteplate-backend` + `-worker` | namespace `biteplate`          |
| `SHOXAKONG/biteplate-frontend`    | Vue 3 + Vite (SPA) + nginx       | `ghcr.io/shoxakong/biteplate-frontend`            | namespace `biteplate-frontend` |
| `SHOXAKONG/biteplate-auth`        | Keycloak 24 + realm-import JSON  | (no image — upstream `quay.io/keycloak/keycloak`) | namespace `biteplate-auth`     |

Each repo has its own `.github/workflows/ci-cd.yml`:

1. **Lint/test stage** — `ruff` + `pytest` (backend), `vue-tsc` + `vite build` (frontend), JSON + YAML validate (auth).
2. **Build & push images** — only on `main` push, tagged with the short git SHA + `latest`.
3. **Deploy** — `kubectl apply -f k8s/` then `kubectl set image` with the new tag to force a rolling update.

---

## 3. Design patterns

All under `backend/app/services/` (plus middleware under `app/core/`):

| #  | Pattern                  | File                  | What it does                                            |
| -- | ------------------------ | --------------------- | ------------------------------------------------------- |
| 1  | Factory                  | `menu.py`             | Creates menu items by type (Beverage / Main / Dessert)  |
| 2  | Composite                | `menu.py`             | `Menu = Category(Item, Item, Category(Item))`           |
| 3  | Decorator                | `menu.py`             | Wraps items with discount / surcharge / tax             |
| 4  | State                    | `tables.py`           | Free → Occupied → Reserved → Cleaning transitions       |
| 5  | Command                  | `kitchen.py`          | Ticket commands with `undo()`                           |
| 6  | Strategy                 | `pricing.py`          | 5 pricing strategies (happy hour, member, surge, etc.)  |
| 7  | Facade                   | `billing.py`          | Single entrypoint hiding tax / discount / split logic   |
| 8  | Singleton                | `history.py`          | Single global bill-history collector                    |
| 9  | Iterator                 | `history.py`          | Range / filter iterators over bill history              |
| 10 | Observer                 | `notifications.py`    | Order events → subscribers (SMS, log, queue)            |
| 11 | Chain of Responsibility  | `core/middleware.py`  | RequestID → Timing → Logging → Errors → RateLimit       |

---

## 4. Auth flow (login)

```
Browser                Frontend (SPA)         Backend FastAPI         Keycloak
   │                        │                       │                     │
   │  POST /login           │                       │                     │
   ├───────────────────────►│                       │                     │
   │                        │ POST /api/v1/auth/    │                     │
   │                        │      login            │                     │
   │                        ├──────────────────────►│                     │
   │                        │                       │ POST /realms/       │
   │                        │                       │  biteplate/...token │
   │                        │                       │ grant=password      │
   │                        │                       │ client=biteplate-   │
   │                        │                       │   frontend          │
   │                        │                       ├────────────────────►│
   │                        │                       │  {access, refresh}  │
   │                        │                       │◄────────────────────┤
   │                        │   tokens + role       │                     │
   │                        │◄──────────────────────┤                     │
   │  store + redirect      │                       │                     │
   │◄───────────────────────┤                       │                     │
```

Subsequent API calls send `Authorization: Bearer <access_token>`. Backend validates JWT signature against Keycloak's JWKS endpoint and uses the `realm_access.roles` claim for RBAC.

**Roles:** `admin_root`, `waiter_*`, `customer_*`, `chef_*` — each with a different SPA experience and a different scope of allowed endpoints.

---

## 5. Networking & TLS

- **DNS:** [`nip.io`](https://nip.io) wildcard — `*.62.113.58.138.nip.io` → `62.113.58.138` (free, no registrar needed).
- **Ingress:** Traefik (bundled with k3s) — routes by `Host:` header to the right `Service`.
- **TLS:** [cert-manager](https://cert-manager.io) + Let's Encrypt HTTP-01 challenge — auto-issued, auto-renewed.
- **Three hostnames:**
  - `https://app.62.113.58.138.nip.io` → frontend
  - `https://api.62.113.58.138.nip.io` → backend
  - `https://auth.62.113.58.138.nip.io` → Keycloak

---

## 6. Build-time vs runtime configuration

| Setting                    | Where set                            | Why                                          |
| -------------------------- | ------------------------------------ | -------------------------------------------- |
| `VITE_API_BASE`            | Frontend Docker build-arg            | Vite bakes env vars into the static bundle   |
| `DATABASE_URL`             | k8s Secret `biteplate-secrets`       | Per-environment, never in image              |
| `KEYCLOAK_SERVER_URL`      | k8s ConfigMap `biteplate-config`     | Public, in-cluster service DNS               |
| `KEYCLOAK_ADMIN_PASSWORD`  | k8s Secret `biteplate-secrets`       | Needed for user creation via admin REST API  |
| Image tag                  | `set image` from CI (short git SHA)  | Forces a rolling update each deploy          |

---

## 7. Operational topology

- **Compute:** 1× Ubuntu 24 VPS running k3s (single-node).
- **Database:** 1× separate Postgres 16 VPS (better disk isolation, easier backups).
- **Storage:** Keycloak uses embedded H2 (dev-grade — would swap to external Postgres for HA).
- **Observability:** structured JSON logs via `structlog`, `kubectl logs`, `k9s` for interactive ops.
- **CI/CD:** GitHub Actions per repo, GHCR for image hosting.

---

## 8. Notable engineering decisions / fixes

| Problem                                         | Resolution                                                                  |
| ----------------------------------------------- | --------------------------------------------------------------------------- |
| Twilio rejected Uzbekistan numbers              | Switched to Eskiz.uz SMS API                                                |
| Nuxt 3 vite-node IPC errors in Docker           | Rebuilt as pure Vue 3 + Vite SPA                                            |
| GHCR rejects uppercase image names              | Added `${OWNER,,}` lowercase expansion in workflow                          |
| Keycloak `--auto-build` removed in v24          | Switched to `start --import-realm` (auto-build is implicit without `--optimized`) |
| Realm import only runs on first start           | Used `kcadm.sh` to apply `directAccessGrantsEnabled` + audience mapper      |
| Multi-issuer JWT validation                     | Backend's `security.py` accepts multiple issuer URLs (in-cluster + public)  |
| DB DSN placeholder `db.example.internal`        | Patched cluster Secret with real Postgres VPS DSN                           |
| `imagePullSecrets` with short-lived GITHUB_TOKEN | Made GHCR packages public, dropped pull secret entirely                    |
| Frontend nginx on :80 vs manifest :3000         | Fixed manifest port to match container                                      |
| `biteplate.example` placeholder domain          | `sed`-replaced with `62.113.58.138.nip.io` across all manifests + realm     |
| No cert-manager installed                       | Installed cert-manager + `letsencrypt-prod` ClusterIssuer                   |
| Wrong client got `directAccessGrantsEnabled`    | Backend hard-codes `biteplate-frontend` as LOGIN_CLIENT_ID — fixed that one |
| Missing `KEYCLOAK_ADMIN_USERNAME / PASSWORD`    | Added to backend Secret for user-creation REST calls                        |
| Slow Keycloak first-boot timing out rollout     | Added `startupProbe` (5 min budget) + `terminationGracePeriodSeconds: 60`   |
| Single-replica scheduling pressure              | Reduced `replicas: 2` → `1` with `maxSurge: 1, maxUnavailable: 0`           |

---

## 9. What's intentionally simple (academic scope)

- Single-node k3s (not multi-node HA).
- Keycloak with embedded H2 (not externalized Postgres).
- `nip.io` DNS (would be a real domain in production).
- No horizontal pod autoscaler, no `PodDisruptionBudget`.
- No external secret manager (Vault / Sealed Secrets) — `Secret`s stored directly in cluster.
- No metrics stack (Prometheus / Grafana) — removed at user's request.

---

## 10. Repository layout

```
biteplate/
├── backend/                       # FastAPI + Celery
│   ├── app/
│   │   ├── api/v1/endpoints/      # flat REST endpoint modules
│   │   ├── core/
│   │   │   ├── middleware.py      # Chain of Responsibility
│   │   │   └── security.py        # JWT validation, multi-issuer
│   │   ├── services/              # all 10 GoF patterns live here
│   │   └── models/                # SQLAlchemy 2 async ORM
│   ├── alembic/                   # DB migrations
│   ├── k8s/                       # api / worker / beat / configmap / rabbitmq / redis
│   ├── Dockerfile                 # API image
│   ├── Dockerfile.worker          # Celery image
│   ├── ARCHITECTURE.md            # this file
│   └── .github/workflows/ci-cd.yml
│
├── frontend/                      # Vue 3 SPA
│   ├── src/
│   │   ├── lib/api.ts             # fetch wrapper with token refresh
│   │   ├── stores/auth.ts         # Pinia auth store
│   │   └── views/                 # per-role pages
│   ├── k8s/                       # frontend + configmap
│   ├── Dockerfile                 # multi-stage Vite build → nginx
│   └── .github/workflows/ci-cd.yml
│
└── auth/                          # Keycloak
    ├── realm/biteplate-realm.json # imported on first start
    ├── k8s/                       # keycloak deploy / svc / ingress
    └── .github/workflows/ci-cd.yml
```

---

## 11. Bootstrap from scratch (cluster-side, one-time)

```bash
# 1. Install k3s
curl -sfL https://get.k3s.io | sh -

# 2. Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
kubectl -n cert-manager wait --for=condition=Available deploy --all --timeout=180s

# 3. Create Let's Encrypt ClusterIssuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    email: <your-email>
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: traefik
EOF

# 4. Push to each of the 3 repos' main branch — CI handles the rest.
```

---

## 12. URLs (live)

- App:  https://app.62.113.58.138.nip.io
- API:  https://api.62.113.58.138.nip.io/docs
- Auth: https://auth.62.113.58.138.nip.io
