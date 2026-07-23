# ---- Stage 1: deps ----
# Real (non-editable) install into an isolated prefix, so stage 2 ships
# only the installed package + its dependencies — no pip, no build
# tooling, no wheel cache.
FROM python:3.11-slim AS deps

WORKDIR /build

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --prefix=/install ".[api]"

# ---- Stage 2: app ----
FROM python:3.11-slim AS app

WORKDIR /app

COPY --from=deps /install /usr/local

# Alembic migration scripts + config: applied automatically on container
# start (see docker-entrypoint.sh) so a fresh `docker-compose up --build`
# against an empty Postgres just works, with no manual migration step.
COPY alembic.ini ./
COPY alembic ./alembic

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "migration_factory.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
