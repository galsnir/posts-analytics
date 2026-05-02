# Posts Analytics

A small FastAPI service that exposes a single endpoint, `GET /stats`, returning
per-topic aggregates over a `posts` table. The data is versioned: a "post" is
identified by `(post_id, topic)` and may exist with multiple `version` rows;
only the latest version (highest `version`, ties broken by `timestamp`) is
counted. The sentinel value `-1` in `likes` / `shares` / `comments` is treated
as a missing value and contributes `0` to the sums.

## Stack

- Python 3.11+
- FastAPI + SQLAlchemy 2.0 (ORM)
- PostgreSQL 16 (real instance, never SQLite/in-memory)
- pytest + [`testcontainers`](https://testcontainers-python.readthedocs.io/) for tests
  (each test session boots a real Postgres container automatically)

## Project layout

```
app/
  main.py        # FastAPI app + /stats route
  database.py    # Engine / session management
  models.py      # SQLAlchemy ORM model
  schemas.py     # Pydantic response models
  stats.py       # Aggregation query
  loader.py      # CSV -> DB loader
tests/
  conftest.py    # Postgres container + DB fixtures
  test_stats.py  # End-to-end tests against the real DB
  data/mock_posts.csv
scripts/
  load_csv.py    # Manual CSV -> DB loader (used for the manual smoke run)
Makefile         # `make test`, `make run`, `make db-up`, etc.
docker-compose.yml
pyproject.toml
```

## Setup

You need Python 3.11+ and Docker running locally (Docker Desktop, Colima,
OrbStack, etc.). The tests will start a Postgres container on demand; the
docker-compose file is only needed if you want to run the API yourself.

```bash
python -m venv .venv
source .venv/bin/activate
make install              # equivalent to: pip install -e ".[dev]"
```

## Running the tests

A single command:

```bash
make test
```

That's it. The Makefile transparently handles the small differences between
Docker setups (Docker Desktop, OrbStack, Colima, Linux Docker) so `make test`
works on all of them with no shell setup.

If you prefer running pytest directly, that also works on Docker Desktop /
OrbStack / Linux Docker:

```bash
pytest
```

On **Colima** specifically (a common macOS alternative to Docker Desktop), if
you skip the Makefile and want to call `pytest` directly, set these once —
ideally in your `~/.zshrc`:

```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export TESTCONTAINERS_RYUK_DISABLED=true   # ryuk can't mount the Colima socket
```

If you also previously had Docker Desktop installed and now see
`docker-credential-desktop not installed`, your `~/.docker/config.json` still
references a credential helper that's no longer on `PATH`:

```bash
mkdir -p /tmp/docker-empty && echo '{}' > /tmp/docker-empty/config.json
export DOCKER_CONFIG=/tmp/docker-empty
```

### What the test suite does

1. Pulls `postgres:16-alpine` (first run only) and starts it in a container.
2. Creates the schema.
3. Loads `tests/data/mock_posts.csv` through the same loader the app uses.
4. Hits `GET /stats` via FastAPI's `TestClient` and asserts the response, both
   against hardcoded expected aggregates and against several focused
   correctness invariants (latest-version-wins, `-1` handling, same `post_id`
   reused across topics, empty DB).

No mocks of the database are used.

## Running the API manually (end-to-end smoke)

```bash
make db-up      # starts Postgres in a container
make load       # loads tests/data/mock_posts.csv
make run        # starts uvicorn on http://localhost:8000

# In another shell:
curl -s localhost:8000/health
curl -s localhost:8000/stats | python -m json.tool

make db-down    # tears down when you're done
```

Each Make target is a thin wrapper; the underlying commands are
`docker-compose up -d`, `python scripts/load_csv.py`, and
`uvicorn app.main:app --reload`. Run `cat Makefile` to see them all.

Example response:

```json
{
  "topics": [
    {"topic": "finance", "num_posts": 8,  "total_likes": 259, "total_shares": 96,  "total_comments": 21},
    {"topic": "health",  "num_posts": 10, "total_likes": 159, "total_shares": 181, "total_comments": 68},
    {"topic": "news",    "num_posts": 11, "total_likes": 295, "total_shares": 127, "total_comments": 62},
    {"topic": "sports",  "num_posts": 6,  "total_likes": 55,  "total_shares": 77,  "total_comments": 66},
    {"topic": "tech",    "num_posts": 6,  "total_likes": 182, "total_shares": 107, "total_comments": 55}
  ]
}
```

## Design notes

- **Latest version per post**: the SQL uses a window function
  (`ROW_NUMBER() OVER (PARTITION BY post_id, topic ORDER BY version DESC,
  timestamp DESC)`) and keeps the top row of each partition. Ties on
  `version` are broken by `timestamp` so the data set behaves deterministically
  even when the source has duplicate `(post_id, topic, version)` rows.
- **Missing values**: rather than null-coalescing in the loader, the `-1`
  sentinel is preserved as-is in the DB (matching the source's convention) and
  converted to `0` only inside the aggregation `SUM(CASE WHEN col = -1 THEN 0
  ELSE col END)`. The post still counts toward `num_posts`.
- **All topics returned**: `GROUP BY topic` after picking the latest row per
  post yields every topic that has at least one post; topics with all-`-1`
  values still appear (with `0` totals).
