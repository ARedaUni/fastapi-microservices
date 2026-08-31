SHELL=bash

.PHONY: help
help: ## Show this help
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


.PHONY: lint
lint:  ## Linter code
	@echo "🚨 Linting code..."
	@docker compose exec -T api sh -c 'ruff check app tests && ruff format --check app tests && mypy app tests'


.PHONY: format
format:  ## Format code
	@echo "🎨 Formatting code..."
	@docker compose exec -T api sh -c 'ruff check --fix app tests && ruff format app tests'


.PHONY: tests
tests:  ## Run tests
	@echo "🍜 Running tests..."
	@docker compose exec -T api pytest -v tests --cov app --cov-report=term-missing:skip-covered --cov-fail-under 69


.PHONY: migrations
migrations:  ## Generate a migration - `msg` parameter is needed
	@docker compose exec -T api alembic revision --autogenerate -m "$(msg)"


.PHONY: up
up:  ## Start the local stack (postgres, redis, api, worker)
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
