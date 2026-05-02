
**Python package manager (uv):**

https://docs.astral.sh/uv/getting-started/installation/

**Deps:**

FastAPI: High-performance Python API framework (handles routing, validation, OpenAPI/docs)

asyncpg: Async PostgreSQL driver (low-level DB communication)

SQLAlchemy: ORM + query builder (maps Python objects to DB tables)

Alembic: Database migration tool for SQLAlchemy

pydantic-settings: Environment/config management (.env → typed settings)

uvicorn[standard]: Production ASGI server (includes uvloop, httptools for performance)

ruff: Linter + formatter (dev tool)

**Package / Environment (uv)**

uv init                  # initialize project
uv add <pkg>             # add dependency
uv remove <pkg>          # remove dependency
uv sync                  # install deps from lockfile
uv sync --dev            # include dev deps
uv lock                  # generate/update lockfile
uv tree                  # view dependency tree
uv run <cmd>             # run inside env

**Run Server**

uvicorn app.main:app --reload          # dev
uvicorn app.main:app --host 0.0.0.0 --port 8000   # prod

**Alembic (Database Migrations)**

alembic init alembic                          # first-time setup
alembic revision --autogenerate -m "msg"     # create migration
alembic upgrade head                         # apply migrations
alembic downgrade -1                         # rollback last migration
alembic history                              # view migration history
alembic current                              # current DB version

**Linting / Formatting**

ruff check .           # lint
ruff format .          # format

