.PHONY: install install-dev fmt lint typecheck test test-cov \
        run worker docker-build docker-up docker-down \
        local-up local-down local-run local-redis get-tokens seed-mock \
        check-go check-terraform tf-provider-build tf-provider-dev-override \
        tf-provider-testacc tf-example-init tf-example-plan tf-example-apply \
        tf-example-destroy tf-example-up-and-test clean help

# ── Variables ─────────────────────────────────────────────────────────────────
UV        := $(HOME)/.pyenv/versions/3.12.4/bin/uv
PYTHON    := $(UV) run python
APP       := app.main:app
API_PORT  ?= 8000
REDIS_URL ?= redis://localhost:6379
TF_PROVIDER_ADDRESS ?= phyllisnelson/vmapi
TF_PROVIDER_BIN_DIR ?= $(CURDIR)/terraform/provider-vmapi/bin
TF_CLI_CONFIG_FILE ?= $(HOME)/.terraformrc
TF_EXAMPLE_DIR ?= terraform/provider-vmapi/examples/basic

# ── Helpers ───────────────────────────────────────────────────────────────────
BANNER = @printf '\n\033[1;36m══ %s\033[0m\n' "$(1)"
OK = @printf '\033[1;32m✔ %s\033[0m\n' "$(1)"
FAIL = @printf '\033[1;31m✖ %s\033[0m\n' "$(1)"
define RUN
	@{ $(2); } && printf '\033[1;32m✔ %s\033[0m\n' "$(1)" || { \
		code=$$?; printf '\033[1;31m✖ %s\033[0m\n' "$(1)"; exit $$code; \
	}
endef

# ── Setup ─────────────────────────────────────────────────────────────────────
install:          ## Install production dependencies
	$(call BANNER,install)
	$(call RUN,Dependencies installed,$(UV) sync)

install-dev:      ## Install all dependencies including dev tools
	$(call BANNER,install-dev)
	$(call RUN,Dev dependencies installed,$(UV) sync --all-groups)

# ── Format ────────────────────────────────────────────────────────────────────
fmt:              ## Auto-format code with black + isort
	$(call BANNER,fmt — black)
	$(call RUN,Black formatting complete,$(UV) run black app tests)
	$(call BANNER,fmt — isort)
	$(call RUN,Import sorting complete,$(UV) run isort app tests)

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:             ## Run flake8 linter
	$(call BANNER,lint — flake8 app tests)
	$(call RUN,Lint passed,$(UV) run flake8 app tests)

# ── Type-check ────────────────────────────────────────────────────────────────
typecheck:        ## Run mypy static type checker
	$(call BANNER,typecheck — mypy app)
	$(call RUN,Typecheck passed,$(UV) run mypy app)

# ── Test ──────────────────────────────────────────────────────────────────────
test:             ## Run test suite
	$(call BANNER,test — pytest)
	$(call RUN,Tests passed,$(UV) run pytest -v)

test-cov:         ## Run tests with 100% coverage enforcement and HTML report
	$(call BANNER,test-cov — pytest --cov)
	$(call RUN,Coverage checks passed,$(UV) run pytest -v --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=100)
	@printf '\n\033[1;32m✔ Coverage report: htmlcov/index.html\033[0m\n'

# ── Dev server ────────────────────────────────────────────────────────────────
run:              ## Start dev server (real OpenStack, hot-reload)
	$(call BANNER,run — uvicorn :$(API_PORT) hot-reload)
	$(UV) run uvicorn $(APP) --reload --port $(API_PORT)

local-redis:      ## Start a standalone Redis container for local-run (detached)
	$(call BANNER,local-redis — redis on :6379)
	$(call RUN,Local Redis started,docker run -d --rm --name local-redis -p 6379:6379 redis:7-alpine)

local-run:        ## Start local dev server with mock backend (REDIS_URL=redis://localhost:6379)
	$(call BANNER,local-run — uvicorn mock backend :$(API_PORT))
	REDIS_URL=$(REDIS_URL) $(UV) run uvicorn tests.local.app:app --reload --port $(API_PORT)

worker:           ## Start arq worker (requires REDIS_URL)
	$(call BANNER,worker — arq WorkerSettings)
	$(UV) run arq app.workers.main.WorkerSettings

# ── Docker (production) ───────────────────────────────────────────────────────
docker-build:     ## Build the production Docker image
	$(call BANNER,docker-build — vm-lifecycle-api:latest)
	$(call RUN,Docker image built,docker build --target runtime -t vm-lifecycle-api:latest .)

docker-up:        ## Start production stack (requires .env with OpenStack creds)
	$(call BANNER,docker-up — production stack)
	$(call RUN,Production stack is up,docker compose up -d --build)

docker-down:      ## Stop production stack
	$(call BANNER,docker-down)
	$(call RUN,Production stack is down,docker compose down)

# ── Docker (local / mock) ─────────────────────────────────────────────────────
local-up:         ## Start local stack (mock backend + Keycloak on :8085)
	$(call BANNER,local-up — mock backend + Keycloak)
	docker compose -f docker-compose.yml -f docker-compose.local.yml up --build redis api keycloak

local-down:       ## Stop local stack
	$(call BANNER,local-down)
	$(call RUN,Local stack is down,docker compose -f docker-compose.yml -f docker-compose.local.yml down redis api keycloak)

# ── Keycloak token helper ─────────────────────────────────────────────────────
get-tokens:       ## Fetch Keycloak Bearer tokens (runs inside the local api container)
	$(call RUN,Token retrieval complete,docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T api python scripts/get_tokens.py)

seed-mock:        ## Re-seed the mock with factory_boy data (local server must be running)
	$(call RUN,Mock data reseeded,docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T api python scripts/seed_mock.py)

check-go:         ## Verify Go is installed (required for Terraform provider build)
	$(call BANNER,check-go)
	@command -v go >/dev/null 2>&1 || { \
		printf '\033[1;31m✖ %s\033[0m\n' "Go not found. Install Go 1.22+ first."; \
		exit 1; \
	}
	@printf '\033[1;32m✔ %s\033[0m\n' "Go found: $$(go version)"

check-terraform:  ## Verify Terraform CLI is installed (required for acceptance tests)
	$(call BANNER,check-terraform)
	@command -v terraform >/dev/null 2>&1 || { \
		printf '\033[1;31m✖ %s\033[0m\n' "Terraform CLI not found. Install Terraform first."; \
		exit 1; \
	}
	@printf '\033[1;32m✔ %s\033[0m\n' "Terraform found: $$(terraform version | head -n1)"

tf-provider-build: ## Build local Terraform provider binary (requires Go)
	$(call BANNER,tf-provider-build — terraform/provider-vmapi/bin)
	@$(MAKE) --no-print-directory check-go
	$(call RUN,Terraform provider built,cd terraform/provider-vmapi && mkdir -p bin && go mod tidy && go build -o bin/terraform-provider-vmapi)

tf-provider-dev-override: ## Configure Terraform CLI dev override for local vmapi provider
	$(call BANNER,tf-provider-dev-override)
	@mkdir -p "$$(dirname "$(TF_CLI_CONFIG_FILE)")"
	@tmp_file="$$(mktemp)"; \
	if [ -f "$(TF_CLI_CONFIG_FILE)" ]; then \
		awk 'BEGIN{skip=0} /^# BEGIN vmapi dev override$$/{skip=1; next} /^# END vmapi dev override$$/{skip=0; next} skip==0 {print}' "$(TF_CLI_CONFIG_FILE)" > "$$tmp_file"; \
	fi; \
	{ \
		echo "# BEGIN vmapi dev override"; \
		echo 'provider_installation {'; \
		echo '  dev_overrides {'; \
		echo '    "$(TF_PROVIDER_ADDRESS)" = "$(TF_PROVIDER_BIN_DIR)"'; \
		echo '  }'; \
		echo '  direct {}'; \
		echo '}'; \
		echo "# END vmapi dev override"; \
	} >> "$$tmp_file"; \
	mv "$$tmp_file" "$(TF_CLI_CONFIG_FILE)"
	@printf '\033[1;32m✔ %s\033[0m\n' "Terraform dev override written to $(TF_CLI_CONFIG_FILE)"

tf-provider-testacc: ## Run Terraform provider acceptance tests (requires API + Terraform)
	$(call BANNER,tf-provider-testacc)
	@$(MAKE) --no-print-directory check-go
	@$(MAKE) --no-print-directory check-terraform
	@printf '\033[1;36mINFO %s\033[0m\n' "Using TF_ACC_VMAPI_BASE_URL=$${TF_ACC_VMAPI_BASE_URL:-http://localhost:8000}"
	@printf '\033[1;36mINFO %s\033[0m\n' "Using TF_ACC_VMAPI_API_KEY=$${TF_ACC_VMAPI_API_KEY:-changeme}"
	$(call RUN,Acceptance tests passed,cd terraform/provider-vmapi && TF_ACC=1 go test -v ./internal/provider -run '^TestAcc')

tf-example-init: ## No-op for dev override workflow (Terraform init is intentionally skipped)
	$(call BANNER,tf-example-init)
	@$(MAKE) --no-print-directory check-terraform
	@printf '\033[1;36mINFO %s\033[0m\n' "Skipping 'terraform init' for provider dev overrides."
	@printf '\033[1;36mINFO %s\033[0m\n' "Run 'make tf-example-plan' or 'make tf-example-apply' directly."
	@printf '\033[1;32m✔ %s\033[0m\n' "Init skipped by design"

tf-example-plan: ## Terraform plan for provider example (runs from repo root)
	$(call BANNER,tf-example-plan)
	@$(MAKE) --no-print-directory check-terraform
	$(call RUN,Terraform example plan complete,terraform -chdir=$(TF_EXAMPLE_DIR) plan)

tf-example-apply: ## Terraform apply for provider example (runs from repo root)
	$(call BANNER,tf-example-apply)
	@$(MAKE) --no-print-directory check-terraform
	$(call RUN,Terraform example apply complete,terraform -chdir=$(TF_EXAMPLE_DIR) apply)

tf-example-destroy: ## Terraform destroy for provider example (runs from repo root)
	$(call BANNER,tf-example-destroy)
	@$(MAKE) --no-print-directory check-terraform
	$(call RUN,Terraform example destroy complete,terraform -chdir=$(TF_EXAMPLE_DIR) destroy)

tf-example-up-and-test: ## Convenience flow: build provider, override, plan, apply, then run acceptance tests (no destroy)
	$(call BANNER,tf-example-up-and-test)
	@$(MAKE) --no-print-directory tf-provider-build
	@$(MAKE) --no-print-directory tf-provider-dev-override
	@$(MAKE) --no-print-directory tf-example-plan
	@$(MAKE) --no-print-directory tf-example-apply
	@$(MAKE) --no-print-directory tf-provider-testacc
	@printf '\033[1;32m✔ %s\033[0m\n' "Full pre-destroy flow complete (resources left running)"

# ── CI pipeline (fmt + lint + typecheck + test) ───────────────────────────────
ci: fmt lint typecheck test  ## Run all checks (mirrors CI pipeline)

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:            ## Remove build artifacts and caches
	$(call BANNER,clean)
	$(call RUN,Removed Python cache directories,find . -type d -name __pycache__ -exec rm -rf {} +)
	$(call RUN,Removed pytest cache,find . -type d -name .pytest_cache -exec rm -rf {} +)
	$(call RUN,Removed mypy cache,find . -type d -name .mypy_cache -exec rm -rf {} +)
	$(call RUN,Removed coverage artifacts,find . -type d -name htmlcov -exec rm -rf {} + && find . -name ".coverage" -delete)
	$(call RUN,Removed .pyc files,find . -name "*.pyc" -delete)

# ── Help ──────────────────────────────────────────────────────────────────────
help:             ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
