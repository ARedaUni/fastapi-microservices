SHELL=bash

.PHONY: help
help: ## Show this help
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


USERS  = kubectl exec deploy/users-deployment --
CANVAS = kubectl exec deploy/canvas-deployment --
READY  = users-deployment canvas-deployment canvas-worker
# load/ and contract/ live outside users' build context, so they are copied
# into its pod on demand rather than synced. COPYFILE_DISABLE stops macOS tar
# adding ._ AppleDouble files, which ruff then tries to parse.
SHIP   = COPYFILE_DISABLE=1 tar c --no-xattrs load contract | kubectl exec -i deploy/users-deployment -- tar x -C /app


.PHONY: lint
lint:  ## Linter code
	@echo "🚨 Linting code..."
	@$(SHIP)
	@$(USERS) sh -c 'ruff check app tests load contract && ruff format --check app tests load contract && mypy app tests'
	@$(CANVAS) sh -c 'ruff check app tests && ruff format --check app tests && mypy app tests'


.PHONY: format
format:  ## Format code (in the pod, then copied back)
	@echo "🎨 Formatting code..."
	@$(SHIP)
	@$(USERS) sh -c 'ruff check --fix app tests load contract && ruff format app tests load contract'
	@$(USERS) tar c app tests | tar x -C users
	@$(USERS) tar c load contract | tar x
	@$(CANVAS) sh -c 'ruff check --fix app tests && ruff format app tests'
	@$(CANVAS) tar c app tests | tar x -C canvas


.PHONY: tests
tests:  ## Run tests
	@echo "🍜 Running tests..."
	@$(USERS) pytest -v tests --cov app --cov-report=term-missing:skip-covered --cov-fail-under 69
	@$(CANVAS) pytest -v tests --cov app --cov-report=term-missing:skip-covered --cov-fail-under 90
	@node --test canvas-model.test.js


.PHONY: e2e
e2e:  ## Run the browser journeys for canvas.html against the running stack
	@npx playwright test


.PHONY: contract
contract:  ## Run the cross-service contract tests against the running stack
	@echo "🤝 Checking the two services still agree..."
	@$(SHIP)
	@$(USERS) pytest -v contract


.PHONY: migrations
migrations:  ## Generate a migration - `msg` needed, `svc` defaults to users
	@kubectl exec deploy/$(or $(svc),users)-deployment -- alembic revision --autogenerate -m "$(msg)"
	@kubectl exec deploy/$(or $(svc),users)-deployment -- tar c migrations/versions | tar x -C $(or $(svc),users)


.PHONY: cluster
cluster:  ## Create the local minikube cluster, once
	@# docker, not minikube's containerd default: Tilt builds straight into a
	@# docker node and has to push to a registry otherwise.
	@minikube start --container-runtime=docker --cpus=$(or $(cpus),4) --memory=$(or $(memory),6g)
	@minikube addons enable ingress


.PHONY: up
up:  ## Start the stack on the current k8s context and wait for it; UI on :10350
	@tilt up > .tilt.log 2>&1 &
	@until tilt get session >/dev/null 2>&1; do sleep 1; done
	@tilt wait --for=condition=Ready uiresource $(READY) --timeout=600s


.PHONY: down
down:  ## Stop the stack and delete what it deployed
	@tilt down
	@pkill -f "tilt up" || true


.PHONY: logs
logs:  ## Tail the users logs
	@kubectl logs -f deploy/users-deployment


.PHONY: shell
shell:  ## Shell into the users pod
	@kubectl exec -it deploy/users-deployment -- bash


.PHONY: load
load:  ## Load-test users from inside the cluster, web UI on http://localhost:8089
	@tilt trigger locust
	@tilt wait --for=condition=Ready uiresource locust --timeout=120s


.PHONY: load-headless
load-headless:  ## Load-test and print a summary - `u`, `r`, `t`, `class` override
	@tilt trigger locust
	@tilt wait --for=condition=Ready uiresource locust --timeout=120s
	@kubectl exec deploy/locust -- locust -f /mnt/locust/locustfile.py \
		--host http://users-service --headless \
		-u $(or $(u),50) -r $(or $(r),10) -t $(or $(t),30s) $(or $(class),ReadUser)
