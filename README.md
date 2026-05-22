## BitePlate Backend

Modular monolith FastAPI service for the BitePlate Smart Restaurant Management System.
All ten GoF design patterns from the brief are implemented in their textbook in-process form:

| Pattern        | Location                            |
| -------------- | ----------------------------------- |
| Factory Method | `app/services/menu.py`              |
| Composite      | `app/services/menu.py`              |
| Decorator      | `app/services/menu.py`              |
| State          | `app/services/tables.py`            |
| Command        | `app/services/kitchen.py`           |
| Observer       | `app/services/notifications.py`     |
| Strategy       | `app/services/pricing.py`           |
| Facade         | `app/services/billing.py`           |
| Singleton      | `app/services/history.py`           |
| Iterator       | `app/services/history.py`           |

### Layout

```
backend/
├── main.py                 FastAPI application entry
├── pyproject.toml          uv project
├── alembic.ini, alembic/   migrations
├── Dockerfile              API image
├── Dockerfile.worker       Celery worker / beat image
├── entrypoint.sh           api | worker | beat | migrate | shell
├── docker-compose.yml      redis + rabbitmq + api + worker + beat (DB is external)
├── k8s/                    namespace, configmap, secrets, deployments, ingress
├── .github/workflows/      CI/CD: lint, test, build, push GHCR, kubectl apply
└── app/
    ├── api/v1/endpoints/   HTTP routes (one file per domain)
    ├── core/               security (Keycloak JWT), exceptions, logging
    ├── dto/                Pydantic request/response models
    ├── models/             SQLAlchemy ORM models
    ├── repositories/       data access (BaseRepository<T>)
    ├── services/           business logic + GoF patterns
    └── tasks/              Celery tasks (sms, reservation reminders)
```

### Run locally

Two ways: the one-command **dev** path (recommended), or the manual path that mirrors
production.

**Dev path** — from the project root (one directory up):

```bash
make dev          # auth + backend + dev Postgres, all in containers
make logs         # tail api + worker logs
make test         # pytest inside the api container
make migrate      # alembic upgrade head
make psql         # psql shell into the dev DB
make wipe         # nuke containers + volumes for a clean slate
```

The dev overlay (`docker-compose.dev.yml` in each project) adds a Postgres container
*for local development only*. Production deployment (`docker compose up` without the
overlay, or the K8s manifests) uses an external database.

**Manual / production-like path:**

The **database is external** — neither base docker-compose nor the K8s manifests deploy
Postgres. Stand up your own DB server and point `DATABASE_URL` / `SYNC_DATABASE_URL` at
it. From a docker-compose container, the host machine is reachable as
`host.docker.internal` (already wired via `extra_hosts`).

```bash
# 0. Make sure your external DB has two databases: "biteplate" and "keycloak".
# 1. Start Keycloak
cd ../auth && cp .env.example .env && docker compose up -d
# 2. Start the backend
cd ../backend && cp .env.example .env  # fill in the values
docker compose up -d --build
```

API is then available at <http://localhost:8000>:

- `GET  /health` — health check (unauthenticated)
- `GET  /docs` — OpenAPI / Swagger UI
- `GET  /api/v1/auth/me` — current user from Keycloak JWT

### Migrations

Migrations run automatically on container start. To run them manually:

```bash
docker compose run --rm api migrate
# or, locally
alembic upgrade head
```

### Tests

```bash
uv pip install --system .[dev]
pytest -q
```

### Auth flow

The backend has no user table and no password logic. JWTs are minted by Keycloak and
validated against the JWKS endpoint cached for one hour. Role-based access is enforced
via `Depends(require_role("waiter", "manager"))` on each endpoint.

### CI/CD

`.github/workflows/ci-cd.yml`:

1. Ruff + Pytest on every push and PR.
2. On push to `main`: build the API and worker images, tag with the commit SHA, push
   to GHCR (`ghcr.io/<owner>/biteplate-backend` and `ghcr.io/<owner>/biteplate-worker`).
3. `kubectl set image` against the cluster referenced by the `KUBECONFIG` secret and
   wait for the rollout to complete.

Replace `REPLACE_OWNER` in `k8s/api.yaml` and `k8s/worker.yaml` with your GitHub user
or organisation before first deploy.
