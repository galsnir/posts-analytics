.DEFAULT_GOAL := test

# `make test` is the single command for running the test suite.
#
# On Docker Desktop / OrbStack / stock Linux Docker, this is just `pytest`.
# On Colima (a common macOS alternative), the recipe transparently sets
# DOCKER_HOST and disables the testcontainers ryuk reaper (which can't mount
# the Colima socket into another container). Anything the user has already
# set in the environment is preserved.
.PHONY: test
test:
	@if [ -z "$$DOCKER_HOST" ] && [ -S "$$HOME/.colima/default/docker.sock" ]; then \
		echo "Colima detected: using $$HOME/.colima/default/docker.sock"; \
		export DOCKER_HOST="unix://$$HOME/.colima/default/docker.sock"; \
		export TESTCONTAINERS_RYUK_DISABLED=true; \
	fi; \
	pytest $(ARGS)

.PHONY: install
install:
	pip install -e ".[dev]"

.PHONY: run
run:
	@if [ -z "$$DATABASE_URL" ]; then \
		export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/posts"; \
	fi; \
	uvicorn app.main:app --reload

.PHONY: load
load:
	@if [ -z "$$DATABASE_URL" ]; then \
		export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/posts"; \
	fi; \
	python scripts/load_csv.py

.PHONY: db-up
db-up:
	docker-compose up -d

.PHONY: db-down
db-down:
	docker-compose down -v
