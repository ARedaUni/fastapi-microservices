SHELL=bash

.PHONY: help
help: ## Show this help
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


.PHONY: lint
lint:  ## Linter code
	@echo "🚨 Linting code..."
	@docker compose exec -T api sh -c 'ruff check app tests load && ruff format --check app tests load && mypy app tests'
	@docker compose exec -T canvas-api sh -c 'ruff check app tests && ruff format --check app tests && mypy app tests'


.PHONY: format
format:  ## Format code
	@echo "🎨 Formatting code..."
	@docker compose exec -T api sh -c 'ruff check --fix app tests load && ruff format app tests load'
	@docker compose exec -T canvas-api sh -c 'ruff check --fix app tests && ruff format app tests'


.PHONY: tests
tests:  ## Run tests
	@echo "🍜 Running tests..."
	@docker compose exec -T api pytest -v tests --cov app --cov-report=term-missing:skip-covered --cov-fail-under 69
	@docker compose exec -T canvas-api pytest -v tests --cov app --cov-report=term-missing:skip-covered --cov-fail-under 90


.PHONY: migrations
migrations:  ## Generate a migration - `msg` needed, `svc` defaults to api
	@docker compose exec -T $(or $(svc),api) alembic revision --autogenerate -m "$(msg)"


.PHONY: up
up:  ## Start the local stack (postgres, redis, users, canvas)
	@docker compose up -d --build --wait


.PHONY: down
down:  ## Stop the local stack
	@docker compose down


.PHONY: logs
logs:  ## Tail the api logs
	@docker compose logs -f api


.PHONY: shell
shell:  ## Shell into the api container
	@docker compose exec api bash


.PHONY: load
load:  ## Load-test the api, web UI on http://localhost:8089
	@docker compose --profile load up locust


.PHONY: load-headless
load-headless:  ## Load-test and print a summary - `u`, `r`, `t`, `class` override
	@docker compose --profile load run --rm locust \
		-f /mnt/locust/locustfile.py --host http://api --headless \
		-u $(or $(u),50) -r $(or $(r),10) -t $(or $(t),30s) $(or $(class),ReadUser)
