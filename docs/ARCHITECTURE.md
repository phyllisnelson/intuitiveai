# Architecture & Design — VM Lifecycle API

## 1. Overview

The VM Lifecycle API provides a vendor-neutral REST interface on top of OpenStack Nova (compute), Glance (images), and the broader OpenStack SDK. Its primary consumers are internal tooling—SCADA provisioning scripts, infrastructure-as-code pipelines, and operator dashboards.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Operator / CI/CD Tool                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/REST
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  VM Lifecycle API (FastAPI)                  │
│                                                                  │
│  ┌──────────┐  ┌──────────────────────┐  ┌─────────────────┐   │
│  │ /health  │  │    API v1 Router     │  │Exception Handler│   │
│  │ /ready   │  │ (vms / flavors /     │  │Request Logger   │   │
│  └──────────┘  │  images / tasks)     │  └─────────────────┘   │
│                │                      │                         │
│                └──────────┬───────────┘                        │
│                           │ Depends()                           │
│              ┌────────────┴────────────┐                        │
│              │                         │                        │
│     ┌────────▼─────────┐    ┌──────────▼──────────┐            │
│     │  Service Layer   │    │    RedisTaskStore    │            │
│     │ BaseOpenStack-   │    │    RedisTaskStore    │            │
│     │ Service (ABC)    │    └──────────┬───────────┘            │
│     └──┬───────────┬───┘              │                        │
│  ┌─────┘           └──────┐           │                        │
│  ▼                        ▼           │                        │
│ MockService        OpenStackService   │                        │
│ (+ create_task)    (+ enqueue_job) ───┤                        │
└─────────────────────────┬─────────────┼────────────────────────┘
                          │             │
           asyncio.to_thread            │ Redis
                          │        ┌────▼──────────────────────┐
                          │        │          Redis             │
                          │        │  task store  │  arq queue │
                          │        └────────────────┬──────────┘
                          │                         │
                          │              ┌───────────▼──────────┐
                          │              │     arq Worker        │
                          │              │ (poll_until_active /  │
                          │              │  do_delete / do_resize│
                          │              └───────────┬──────────┘
                          │                          │ asyncio.to_thread
                          ▼                          ▼
                    ┌─────────────────────────────────────┐
                    │          OpenStack Cluster           │
                    │   Nova  │  Glance  │  Keystone       │
                    └─────────────────────────────────────┘
```

---

## 2. Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Web framework | **FastAPI** | Async-first, auto-generates OpenAPI docs, Pydantic validation |
| OpenStack client | **openstacksdk** | Official SDK; covers Nova and Glance via a single connection |
| Async strategy | **asyncio.to_thread** | Wraps blocking SDK calls without a separate thread pool library |
| Dependency management | **uv + pyproject.toml** | 10–100× faster than pip, single source of truth for deps |
| Containerisation | **Docker (multi-stage)** | Production image is 2-stage (`Dockerfile`: builder → runtime); local dev image is separate (`Dockerfile.local`: builder → local) |
| Logging | **structlog** | Machine-parseable JSON → Elastic / Loki compatible |
| Validation | **Pydantic v2** | Fast, type-safe schema enforcement at the boundary |
| Task store / queue | **Redis** | Shared state for task records and arq job queue; survives API restarts |
| Auth | **Keycloak OIDC + API key** | Token introspection for instant revocation; API key fallback for CI/CD |
| HTTP client | **httpx** | Async HTTP client used for Keycloak introspection calls |
| Testing | **pytest + httpx TestClient** | Zero-mock HTTP client; exercises the full ASGI stack |
| Background jobs | **arq** | Async Redis queue — native asyncio, durable across restarts, no separate broker |
| Manual testing | **Postman collection** | Importable suite covering all endpoints, state transitions, and RBAC |
| Local OIDC | **Keycloak 26 (dev mode)** | Pre-seeded realm with test users; started by `make local-up` on port 8085 |

---

## 3. Project Layout

```
vm-lifecycle-api/
├── app/
│   ├── main.py                    # App factory — wires middleware, handlers, routers
│   ├── api/
│   │   ├── oidc.py                # Keycloak OIDC introspection + API-key fallback; Principal, require_read, require_write
│   │   ├── deps.py                # FastAPI DI providers and type aliases (ReadAuthDep, WriteAuthDep)
│   │   └── v1/
│   │       ├── router.py          # Aggregates v1 sub-routers
│   │       └── endpoints/
│   │           ├── vms.py             # VM CRUD (create / list / get / delete)
│   │           ├── vm_actions.py      # VM sub-resources (actions / resize / snapshots / console)
│   │           ├── tasks.py           # Async task polling
│   │           ├── flavors.py         # Flavor catalog
│   │           ├── images.py          # Image catalog
│   │           └── health.py          # /health  /ready
│   ├── core/
│   │   ├── config.py              # pydantic-settings — env var loading
│   │   ├── exceptions.py          # Domain exception hierarchy
│   │   ├── handlers.py            # handle_domain_error + FastAPI exception handlers
│   │   ├── middleware.py          # RequestLoggingMiddleware
│   │   └── logging.py             # structlog JSON configuration
│   ├── schemas/
│   │   ├── common.py              # APIResponse, PaginatedResponse, ErrorDetail
│   │   ├── enums.py               # VMState, VMAction, TaskStatus
│   │   ├── task.py                # TaskResponse
│   │   ├── vms.py                 # VMCreate, AddressInfo, VMResponse
│   │   ├── vm_actions.py          # VMActionRequest, VMResizeRequest, SnapshotCreateRequest, ConsoleResponse, SnapshotResponse
│   │   ├── flavor.py              # FlavorResponse
│   │   ├── image.py               # ImageResponse
│   │   └── health.py              # HealthResponse, ReadinessResponse
│   ├── services/
│   │   ├── base.py                # Abstract service interface (ABC)
│   │   ├── openstack_service.py   # Facade — connection lifecycle, routes to sub-clients
│   │   ├── _compute.py            # Nova sub-client (VMs, flavors, snapshots)
│   │   ├── _image.py              # Glance sub-client (images)
│   │   └── task_store.py          # RedisTaskStore
│   └── workers/
│       ├── tasks.py               # arq task functions (VM background ops)
│       └── main.py                # WorkerSettings entry point for arq CLI
├── terraform/
│   └── provider-vmapi/            # Custom Terraform provider (Go, plugin framework)
│       ├── main.go
│       ├── go.mod
│       ├── internal/provider/     # Provider config + resources + data sources + API client
│       ├── examples/basic/main.tf # End-to-end usage example
│       └── README.md
├── tests/
│   ├── conftest.py                # Mock service injected via dependency_overrides
│   ├── integration/               # Full ASGI stack tests via TestClient
│   │   ├── test_auth.py
│   │   ├── test_health.py
│   │   ├── test_vms.py
│   │   ├── test_vm_actions.py
│   │   ├── test_tasks.py
│   │   ├── test_flavors.py
│   │   └── test_images.py
│   ├── unit/                      # Isolated function/class tests
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
│   │   └── app.py                 # Local dev entry point (mounts mock backend)
│   └── mocks/
│       ├── openstack.py           # MockOpenStackService — in-memory state machine
│       └── factories.py           # factory_boy fixture factories
├── docs/
│   ├── ARCHITECTURE.md
│   ├── postman_collection.json        # Importable Postman test suite (43 tests)
│   └── postman_collection_oidc.json   # OIDC-only tests (requires Keycloak)
├── keycloak/
│   └── realm-vm-api.json             # Realm seed: vm-api realm, vm-api client, alice + bob
├── scripts/
│   ├── get_tokens.py              # Fetch Keycloak reader/operator Bearer tokens for OIDC testing
│   └── seed_mock.py               # Seed the local mock backend via /dev/seed
├── Dockerfile                     # Production image (builder → runtime)
├── Dockerfile.local               # Local dev image (builder → local)
├── docker-compose.yml             # Production stack (real OpenStack)
├── docker-compose.local.yml       # Local stack (mock backend, no credentials)
├── Makefile
├── pyproject.toml
└── .env.example
```

---

## 4. API Design Decisions

### Versioned Prefix
All resource endpoints live under `/api/v1/`. This allows a non-breaking v2 to be introduced in parallel and deprecated gracefully.

### Asynchronous Operations (202 Accepted)
OpenStack VM creation, deletion, and resize can take 30–300 s. Rather than holding an HTTP connection open, the API returns **202 Accepted** immediately with the full `TaskResponse`. Clients poll `GET /api/v1/tasks/{task_id}` to track completion.

```
POST /api/v1/vms  →  202  { task_id, status: "pending", ... }
GET  /api/v1/tasks/{task_id}  →  200  { status: "success", resource_id: "vm-..." }
```

`AbstractTaskStore.create` returns a `TaskResponse` directly (the record is already in memory). Service methods (`create_vm`, `delete_vm`, `resize_vm`, `create_snapshot`) pass this straight through to the endpoint — no secondary `task_store.get()` call required.

### Action Sub-resource
Rather than exposing `POST /vms/{id}/start` and `POST /vms/{id}/stop` as separate URLs, all power actions go through a single **action sub-resource**:

```
POST /api/v1/vms/{id}/actions  { "action": "stop" }
```

This follows the OpenStack Nova API convention and keeps the URL surface small.

### Standard Response Envelope
Every successful response is wrapped:
```json
{ "data": <resource>,  "meta": {} }
```
All three list endpoints (`/vms`, `/flavors`, `/images`) accept `limit` (1–200, default 50) and `offset` (≥0, default 0) and return:
```json
{ "data": [...], "total": 42, "page": 2, "page_size": 10 }
```
where `page = offset // limit + 1`. Most endpoint errors are raised as
`HTTPException` and return FastAPI's default `{ "detail": "..." }` shape.
Unhandled `VMAPIError` subclasses use the registered app-level handler and
include both `detail` and `code`.

### Consistent Service Layer Contract
All list operations on `BaseOpenStackService` share the same signature shape:

```python
async def list_vms(self, ..., limit: int, offset: int) -> tuple[list[VMResponse], int]
async def list_flavors(self, limit: int, offset: int) -> tuple[list[FlavorResponse], int]
async def list_images(self, limit: int, offset: int) -> tuple[list[ImageResponse], int]
```

Mutating operations return the pending `TaskResponse` directly:

```python
async def create_vm(self, payload: VMCreate) -> tuple[str, TaskResponse]   # (vm_id, task)
async def delete_vm(self, vm_id: str) -> TaskResponse
async def resize_vm(self, vm_id: str, request: VMResizeRequest) -> TaskResponse
async def create_snapshot(self, vm_id: str, request: SnapshotCreateRequest) -> tuple[SnapshotResponse, TaskResponse]
```

The service owns slicing and counting; endpoints only pass parameters through and build the `PaginatedResponse`. Both `MockOpenStackService` and `OpenStackService` honour this contract, so swapping backends never requires endpoint changes.

> **Note**: OpenStack's native APIs (Nova, Glance) use cursor/marker-based pagination and do not return a total count. The current implementation fetches the full list from OpenStack and slices in memory. For the small, mostly-static flavor and image catalogs this is acceptable. For VMs at scale, consider switching to marker-based pagination or moving VM state to a database where `COUNT(*)` and `LIMIT/OFFSET` are cheap.

### Dependency Injection for Service Layer
The `BaseOpenStackService` is injected via FastAPI's `Depends()` system. Tests override this dependency with a `MockOpenStackService` — no patching or monkey-patching required.

---

## 5. Async Strategy

`openstacksdk` is a **synchronous** library. All blocking SDK calls are wrapped with `asyncio.to_thread()`, which runs them in the default thread-pool executor without blocking the event loop:

```python
result = await asyncio.to_thread(conn.compute.get_server, vm_id)
```

Long-running operations (create, delete, resize) enqueue jobs via arq:

```python
await arq_pool.enqueue_job("task_name", ...)
```

Jobs persist in Redis and are picked up by the arq worker process. This survives API restarts and scales across multiple uvicorn workers.

The arq worker runs as a separate process and is included in `docker-compose.yml`:

```bash
# Start the worker (requires REDIS_URL)
arq app.workers.main.WorkerSettings

# Or via Makefile
make worker
```

The mock service (`MockOpenStackService`) always uses `asyncio.create_task` — it is never connected to arq. The local dev stack (`docker-compose.local.yml`) uses real Redis but the mock service, so arq is not required locally.

---

## 6. Security

### Authentication

Two methods are supported; the first match wins on each request:

| Priority | Method | When active |
|---|---|---|
| 1 | `Authorization: Bearer <token>` | `KEYCLOAK_URL` is set |
| 2 | `X-API-Key: <key>` | `API_KEY` is set |

At least one must be configured — 401 is returned if neither is set.

**Bearer token flow (OIDC introspection):**
1. Client obtains a JWT from Keycloak (`/realms/{realm}/protocol/openid-connect/token`)
2. API `POST`s the token to Keycloak's introspection endpoint on every request
3. If `active: true`, the API extracts `realm_access.roles` to build the Principal
4. If Keycloak is unreachable, 503 is returned immediately

Introspection (rather than local JWT verification) means tokens are revoked
instantly — no waiting for expiry.

### Role-Based Access Control (RBAC)

| Role | GET endpoints | Mutating endpoints (create/delete/resize/snapshot/actions) |
|---|---|---|
| `vm-reader` | ✓ | ✗ (403) |
| `vm-operator` | ✓ | ✓ |
| API key holder | ✓ | ✓ (full access) |

Roles are configured via `KEYCLOAK_READER_ROLE` and `KEYCLOAK_OPERATOR_ROLE`.
The FastAPI dependency chain is:

```
endpoint → require_read / require_write → get_current_user → (Bearer introspect | API key check)
```

### Other Security Controls

| Layer | Measure |
|---|---|
| **Container** | Non-root `appuser` user; distroless-style slim image |
| **Secrets** | Credentials injected via environment variables, never in source |
| **Network** | OT and IT networks logically separated (see seed data in mock) |
| **Logging** | Passwords are never logged; structured JSON shipped to SIEM |
| **Input validation** | Pydantic enforces all request field constraints at the boundary |
| **CORS** | Restrict to known origins in production |

Energy sector (OT/IT convergence) additional hardening:
- mTLS between API and OpenStack Keystone endpoint
- Dedicated service account with minimum Nova/Glance permissions
- Audit log per operation (extend structlog events to ship to SIEM)
- Network policy: API pod only routes to OpenStack API network, not OT VLAN

---

## 7. Error Handling

Domain exceptions map deterministically to HTTP status codes:

| Exception | HTTP |
|---|---|
| `VMNotFoundError` | 404 |
| `FlavorNotFoundError` | 404 |
| `ImageNotFoundError` | 404 |
| `TaskNotFoundError` | 404 |
| `InvalidVMStateError` | 409 Conflict |
| `VMOperationError` | 502 Bad Gateway |
| `OpenStackConnectionError` | 503 Service Unavailable |
| `AuthenticationError` | 401 Unauthorized |

A generic `500` handler catches anything unhandled and logs the full traceback.

---

## 8. Manual Testing — Postman Collection

Two Postman collections live in `docs/`:

| Collection | File | Tests | Requires |
|---|---|---|---|
| Main | `postman_collection.json` | 43 | Local mock stack (`make local-up`) |
| OIDC | `postman_collection_oidc.json` | 3 | Live Keycloak instance |

The main collection covers all endpoints against the mock backend.
The OIDC collection tests Bearer token auth and RBAC (reader 403, operator 202) and requires `KEYCLOAK_URL` to be configured.

### Variables

| Variable | Set by | Used by |
|---|---|---|
| `base_url` | operator | all requests |
| `api_key` | operator | X-API-Key header (static auth) |
| `image_id` | List Images | Create VM body |
| `flavor_id` | List Flavors | Create VM body, Resize VM body |
| `seeded_active_vm_1` | List VMs (first `ACTIVE` VM) | Console URL, Reboot |
| `seeded_active_vm_2` | List VMs (second `ACTIVE` VM) | Stop, Snapshot |
| `seeded_shutoff_vm` | List VMs (first `SHUTOFF` VM) | Start, Resize |
| `vm_id` | Create VM | Get VM, Delete VM |
| `task_id` | Delete VM | Poll Task |

### State isolation strategy

VM action tests (`stop`, `start`, `reboot`, `resize`, `console`) each target a **different pre-seeded VM** in the correct initial state rather than the newly-created VM. The newly-created VM starts in `BUILDING` state and takes ~2 s to become `ACTIVE`; at 2 ms average response time, tests complete long before the transition. Using pre-seeded VMs eliminates the race condition entirely.

### Run order

```
Reset → System → Images → Flavors → VMs → VM Actions → Tasks → Auth
```

The first request (`POST /dev/reset`) resets the mock back to its three original seeded VMs, ensuring a clean slate on every collection run regardless of state left by previous runs. This endpoint only exists on the local mock stack and returns 404 against production — the test accepts both 200 and 404.

---

## 9. Roadmap / Backlog

### Immediate next steps (sprint 1)
- [ ] Structured audit log (every write operation logged with user + IP)
- [ ] Rate limiting middleware (slowapi or custom)

### Medium term (sprint 2–4)
- [ ] VM tag management (`GET/POST /vms/{id}/tags`)
- [ ] Bulk operations (`POST /api/v1/vms/bulk-action`)
- [ ] Metrics endpoint (`/metrics`) — Prometheus-compatible

### Long term
- [ ] Multi-region support (configurable per-request region header)
- [ ] Scheduled operations (cron-style VM start/stop for dev environments)
- [ ] GitOps VM declarations (desired-state reconciliation loop)

---

## 10. Performance Characteristics (PoC)

| Scenario | Latency |
|---|---|
| `GET /api/v1/vms` (mock) | < 5 ms |
| `POST /api/v1/vms` (mock, returns 202) | < 10 ms |
| `GET /api/v1/vms` (real OpenStack, cold) | 200–800 ms |
| `POST /api/v1/vms` (real OpenStack, 202) | 300–600 ms (returns before VM is ACTIVE) |
| VM ACTIVE (real) | 30–120 s (polled via task endpoint) |

The async model means the API can handle thousands of concurrent requests while a handful of VMs are building in the background.
