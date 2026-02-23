# VM Lifecycle API

A production-quality REST API for managing OpenStack virtual machine lifecycle operations.

---

## Quick Start (no OpenStack required)

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd <repo-dir>

# 2. Copy environment template
cp .env.example .env

# 3. Start with the local mock stack (no OpenStack credentials needed)
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build redis api keycloak

# 4. Browse the interactive API docs
open http://localhost:8000/docs
```

The local compose stack uses a mock backend with three pre-seeded VMs — no OpenStack credentials needed.

---

## API Surface

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| `GET` | `/health` | Liveness probe | 200 |
| `GET` | `/ready` | Readiness probe | 200 / 503 |
| `GET` | `/api/v1/vms` | List VMs (filterable, paginated) | 200 |
| `POST` | `/api/v1/vms` | Create VM | **202** + task_id |
| `GET` | `/api/v1/vms/{id}` | Get VM details | 200 |
| `DELETE` | `/api/v1/vms/{id}` | Delete VM | **202** + task_id |
| `POST` | `/api/v1/vms/{id}/actions` | Power action (start/stop/reboot/suspend/resume) | **202** |
| `PUT` | `/api/v1/vms/{id}/resize` | Resize VM to new flavor | **202** + task_id |
| `POST` | `/api/v1/vms/{id}/snapshots` | Create snapshot | **202** + task_id |
| `GET` | `/api/v1/vms/{id}/console` | Get noVNC console URL | 200 |
| `GET` | `/api/v1/tasks/{task_id}` | Poll async operation status | 200 |
| `GET` | `/api/v1/flavors` | List compute flavors (paginated) | 200 |
| `GET` | `/api/v1/images` | List OS images (paginated) | 200 |

Long-running operations (create / delete / resize / snapshot) return **202 Accepted** immediately with a `task_id`. Poll `GET /api/v1/tasks/{task_id}` to track completion.

---

## Authentication

Every request requires credentials. Two methods are supported (first match wins):

| Method | Header | When |
|--------|--------|------|
| Bearer token (OIDC) | `Authorization: Bearer <token>` | Keycloak configured (`KEYCLOAK_URL` set) |
| API key | `X-API-Key: <key>` | `API_KEY` set — for CI/CD / scripts |

**RBAC roles** (Keycloak Bearer tokens only):

| Role | Read endpoints | Write endpoints |
|------|---------------|-----------------|
| `vm-reader` | ✓ | ✗ 403 |
| `vm-operator` | ✓ | ✓ |
| API key holder | ✓ | ✓ |

Get a token from Keycloak:
```bash
TOKEN=$(curl -s -X POST $KEYCLOAK_URL/realms/vm-api/protocol/openid-connect/token \
  -d "client_id=vm-api&client_secret=$KEYCLOAK_CLIENT_SECRET" \
  -d "grant_type=password&username=alice&password=..." \
  | jq -r .access_token)
```

---

## Example Requests

### Create a VM

```bash
curl -s -X POST http://localhost:8000/api/v1/vms \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "vm-scada-prod-04",
    "flavor_id": "m1.large",
    "image_id": "img-rhel-9",
    "network_id": "ot-network",
    "metadata": {"env": "prod", "owner": "ot-team"}
  }' | jq .
```

Response:
```json
{
  "data": {
    "task_id": "3fa85f64-...",
    "status": "pending",
    "operation": "create_vm",
    "resource_id": "vm-...",
    "created_at": "2025-01-15T10:30:00Z"
  },
  "meta": {"vm_id": "vm-..."}
}
```

### Poll task status

```bash
curl http://localhost:8000/api/v1/tasks/3fa85f64-... | jq .data.status
# "success"
```

### Stop a VM

```bash
curl -X POST http://localhost:8000/api/v1/vms/{vm_id}/actions \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
```

### List VMs filtered by status

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/vms?status=ACTIVE&limit=10" | jq .
```

### List flavors (paginated)

All three catalog endpoints (`/vms`, `/flavors`, `/images`) accept the same `limit` and `offset` query parameters:

```bash
curl "http://localhost:8000/api/v1/flavors?limit=10&offset=0" | jq .
curl "http://localhost:8000/api/v1/images?limit=5&offset=10" | jq .
```

Response shape:
```json
{ "data": [...], "total": 12, "page": 1, "page_size": 10 }
```

---

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — fast Rust-based package manager (`pip install uv`)
- Docker & Docker Compose

`uv` replaces Poetry/pip entirely and is typically **10–100× faster**. No lock-file generation step, no plugin install, no virtual env preamble.

### Local development (without Docker)

```bash
# Install all deps (creates .venv automatically)
uv sync --all-groups

# Start local Redis (required by tests.local.app) in another terminal
docker compose up -d redis

# Start local dev server with mock backend (no OpenStack needed)
make local-run

# Or target a real OpenStack cluster (requires REDIS_URL)
make run

# Start the arq worker (required for durable background tasks in production)
make worker
```

### Run tests

```bash
# Using pytest directly
uv run pytest                          # all tests + coverage
uv run pytest tests/integration/test_vms.py -v    # specific file
```

### Lint & type-check

```bash
make fmt          # black + isort (auto-format)
make lint         # flake8 + flake8-bugbear
make typecheck    # mypy
make ci           # fmt + lint + typecheck + test in one shot
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values. At least one of `API_KEY` or `KEYCLOAK_URL` must be set.

### App

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8000` | Host port published by Docker Compose |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `API_KEY` | _(empty)_ | Static key for `X-API-Key` header (CI/CD / scripts) |
| `REDIS_URL` | _(required)_ | Redis URL for task store and arq queue (e.g. `redis://localhost:6379`) |
| `TASK_TTL_SECONDS` | `86400` | Task record TTL in Redis (seconds) |

### OpenStack

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENSTACK_AUTH_URL` | `https://openstack.example.internal:5000/v3` | Keystone v3 endpoint |
| `OPENSTACK_USERNAME` | `api-svc` | Service account username |
| `OPENSTACK_PASSWORD` | _(empty)_ | Service account password |
| `OPENSTACK_PROJECT_NAME` | `default-project` | Target project/tenant |
| `OPENSTACK_PROJECT_DOMAIN_NAME` | `Default` | Project domain |
| `OPENSTACK_USER_DOMAIN_NAME` | `Default` | User domain |
| `OPENSTACK_REGION_NAME` | `RegionOne` | Target region |
| `OPENSTACK_DEFAULT_NETWORK_ID` | _(empty)_ | Fallback network UUID for VM creation |

### Keycloak / OIDC

| Variable | Default | Description |
|----------|---------|-------------|
| `KEYCLOAK_URL` | _(empty)_ | Base URL — set to enable OIDC Bearer token auth |
| `KEYCLOAK_REALM` | `vm-api` | Realm name |
| `KEYCLOAK_CLIENT_ID` | `vm-api` | Client ID for introspection |
| `KEYCLOAK_CLIENT_SECRET` | — | Client secret for introspection |
| `KEYCLOAK_READER_ROLE` | `vm-reader` | Role required for read (GET) endpoints |
| `KEYCLOAK_OPERATOR_ROLE` | `vm-operator` | Role required for mutating endpoints |

---

## Connecting to a Real OpenStack Cluster

1. Populate all `OPENSTACK_*` variables in your `.env`
2. Ensure the service account has at minimum:
   - Nova: `compute:get`, `compute:create`, `compute:delete`, `compute:start`, `compute:stop`, `compute:reboot`, `compute:resize`
   - Glance: `image:get`
3. Start: `docker compose up --build`

---

## Docker

### Build image

```bash
docker build -t vm-lifecycle-api:latest .
```

### Run standalone (production image)

```bash
docker run -p 8000:8000 \
  -e OPENSTACK_AUTH_URL=https://... \
  vm-lifecycle-api:latest
```

### Run with mock backend (no credentials)

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build redis api keycloak
```

### Production compose

```bash
cp .env.example .env
# Edit .env with real OpenStack credentials
docker compose up -d
# Starts: redis + api + worker (arq)
```

---

## Project Structure

```
vm-lifecycle-api/
├── app/
│   ├── main.py                    # App factory — wires middleware, handlers, routers
│   ├── api/
│   │   ├── oidc.py                # Keycloak OIDC introspection + API-key fallback; RBAC deps
│   │   ├── deps.py                # FastAPI DI providers and type aliases (ReadAuthDep, WriteAuthDep)
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │           ├── vms.py             # VM CRUD
│   │           ├── vm_actions.py      # Power actions, resize, snapshots, console
│   │           ├── tasks.py           # Async task polling
│   │           ├── flavors.py
│   │           ├── images.py
│   │           └── health.py
│   ├── core/
│   │   ├── config.py              # pydantic-settings
│   │   ├── exceptions.py          # Domain exception hierarchy
│   │   ├── handlers.py            # Exception handlers + domain→HTTP translation
│   │   ├── middleware.py          # Request logging middleware
│   │   └── logging.py             # structlog JSON setup
│   ├── schemas/
│   │   ├── common.py              # APIResponse, PaginatedResponse
│   │   ├── enums.py               # VMState, VMAction, TaskStatus
│   │   ├── task.py                # TaskResponse
│   │   ├── vms.py                 # VMCreate, AddressInfo, VMResponse
│   │   ├── vm_actions.py          # VMActionRequest, VMResizeRequest, SnapshotCreateRequest, ConsoleResponse, SnapshotResponse
│   │   ├── flavor.py              # FlavorResponse
│   │   ├── image.py               # ImageResponse
│   │   └── health.py              # HealthResponse, ReadinessResponse
│   ├── services/
│   │   ├── base.py                # Abstract service interface
│   │   ├── openstack_service.py   # Facade — connection lifecycle + routing
│   │   ├── _compute.py            # Nova sub-client (VMs, flavors, snapshots)
│   │   ├── _image.py              # Glance sub-client (images)
│   │   └── task_store.py          # Redis-backed async task store
│   └── workers/
│       ├── tasks.py               # arq task functions (VM background ops)
│       └── main.py                # WorkerSettings + startup/shutdown hooks
├── tests/
│   ├── conftest.py
│   ├── integration/
│   │   ├── test_auth.py
│   │   ├── test_health.py
│   │   ├── test_vms.py
│   │   ├── test_vm_actions.py
│   │   ├── test_tasks.py
│   │   ├── test_flavors.py
│   │   └── test_images.py
│   ├── unit/
│   │   ├── services/
│   │   │   ├── test_facade.py         # OpenStackService connection + routing
│   │   │   ├── test_compute.py        # ComputeClient (Nova)
│   │   │   ├── test_images.py         # ImageClient (Glance)
│   │   │   └── test_task_store.py     # RedisTaskStore
│   │   ├── test_config.py
│   │   ├── test_logging.py
│   │   ├── test_handlers.py
│   │   ├── test_oidc.py
│   │   ├── test_deps.py
│   │   └── test_workers.py
│   ├── local/
│   │   └── app.py                 # Local dev entry point (mock backend)
│   └── mocks/
│       ├── openstack.py           # MockOpenStackService
│       └── factories.py           # factory_boy fixtures
├── docs/
│   ├── ARCHITECTURE.md
│   ├── postman_collection.json    # Importable Postman test suite (43 tests)
│   └── postman_collection_oidc.json   # OIDC-only tests (requires Keycloak)
├── keycloak/
│   └── realm-vm-api.json             # Realm seed: vm-api realm, vm-api client, alice + bob
├── scripts/
│   ├── get_tokens.py              # Fetch Keycloak reader/operator tokens for OIDC testing
│   └── seed_mock.py               # Seed the local mock backend via /dev/seed
├── Dockerfile                     # Production image (builder → runtime)
├── Dockerfile.local               # Local dev image (builder → local)
├── docker-compose.yml             # Production (real OpenStack)
├── docker-compose.local.yml       # Local dev (mock backend)
├── Makefile
├── pyproject.toml
└── .env.example
```

---

## Design Highlights

- **Async-first**: All endpoints are `async`. Blocking `openstacksdk` calls run in a thread pool via `asyncio.to_thread()`.
- **Durable background jobs**: `arq` enqueues VM operations (create, delete, resize) in Redis so tasks survive worker restarts and scale across multiple uvicorn workers.
- **OIDC authentication**: Keycloak token introspection per request — tokens revoked instantly, no signature key rotation needed. API key fallback for CI/CD scripts.
- **RBAC**: `vm-reader` role for GETs, `vm-operator` for mutations. API key holders get full access.
- **Dependency injection**: Service backend is swappable at runtime — mock for PoC/tests, real for production.
- **202 pattern**: Long-running operations return immediately with a task ID; no hanging HTTP connections.
- **Structured logging**: JSON output compatible with Elastic/Loki/Splunk for energy sector compliance.
- **Non-root container**: The Docker image runs as an unprivileged `appuser` user.
- **Fast installs**: `uv` replaces pip in CI and Docker builds — typically 10–50× faster.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture writeup including roadmap.

---

## Postman Test Suite

Two Postman collections live in [`docs/`](docs/):

| Collection | File | Tests | Requires |
|------------|------|-------|----------|
| Main | [`postman_collection.json`](docs/postman_collection.json) | 43 | Local mock stack (`make local-up`) |
| OIDC | [`postman_collection_oidc.json`](docs/postman_collection_oidc.json) | 3 | Live Keycloak instance |

### Import & run (main collection)

1. Open Postman → **Import** → select `docs/postman_collection.json`
2. In the collection **Variables** tab, set:
   - `base_url` → `http://localhost:8000`
   - `api_key` → your static API key (default: `changeme`)
3. Use the **Collection Runner** to execute all tests in order

### Coverage (main collection)

| Folder | Requests | Tests |
|--------|----------|-------|
| — | Reset Mock State | 1 |
| System | Health, Readiness | 4 |
| Images | List Images | 3 |
| Flavors | List Flavors | 3 |
| VMs | List, Create, Get, Get 404 | 8 |
| VM Actions | Console URL, Reboot, Stop, Start, Resize, Snapshot, Delete | 14 |
| Tasks | Poll Task, Poll Task (wait for completion), Poll 404 | 5 |
| Auth | Valid key, Wrong key, Missing creds | 3 |

### OIDC collection

Import `docs/postman_collection_oidc.json` separately. A local Keycloak instance is started automatically by `make local-up` on port **8085** with the `vm-api` realm pre-seeded.

Pre-seeded test users (password `changeme` for both):

| Username | Role | Use for |
|----------|------|---------|
| `alice` | `vm-reader` | `bearer_token` variable |
| `bob` | `vm-operator` | `operator_token` variable |

Obtain tokens:
```bash
# prints both Alice (reader) and Bob (operator) Bearer tokens, plus API_KEY
make get-tokens
```

Paste the printed token values into the OIDC collection variables in Postman.

### How state is managed

The runner must execute requests **in order** (top to bottom). Key IDs are chained automatically via collection variables:

- `List Images` → saves `image_id`
- `List Flavors` → saves `flavor_id`
- `List VMs` → saves `seeded_active_vm_1`, `seeded_active_vm_2`, `seeded_shutoff_vm` from the pre-seeded mock data (guaranteeing correct initial VM states for each action test)
- `Create VM` → saves `vm_id` and `task_id`

---
