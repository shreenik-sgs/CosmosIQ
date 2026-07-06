# CosmosIQ — local-first container image (IMPLEMENTATION-023C).
#
# SAFE BY DEFAULT. This image starts CosmosIQ in a SAFE posture — the localhost-only
# operator app against a mounted store, with COSMOSIQ_PROFILE=test_offline (the 023A safe
# default profile: network blocked, fixtures only, everything off). It NEVER enables
# production. Turning on PRODUCTION_24X7 / production_manual_review is the explicit
# `cosmosiq_ops activate` + operator sign-off path (021C/022H) — never a container default.
#
# HONEST NOTE: running `docker build` / `docker compose up` is the OPERATOR's step. The
# repo's OFFLINE test suite validates the packaging STRUCTURE and that every wrapped command
# works offline; it does NOT build or run a container. No container was built by CosmosIQ CI.
#
# SECRETS are injected at RUNTIME (env / --env-file), never baked into the image: this
# Dockerfile copies NO real .env. Only .env.example (env var NAMES + obviously-fake
# placeholders) travels with the source tree, and CosmosIQ reads only the PRESENCE of a var.

FROM python:3.9-slim

# stdlib-only: there is no pip install and no build step. A non-root user owns the app and
# the mounted store.
RUN useradd --create-home --uid 10001 cosmosiq
WORKDIR /app

# Copy ONLY the source, tests, config, and the deployment docs the operator needs.
# Deliberately NO real .env is ever copied — only the committed .env.example template.
COPY src/ ./src/
COPY tests/ ./tests/
COPY config/ ./config/
COPY .env.example ./.env.example
COPY deploy/ ./deploy/
COPY docs/DEPLOYMENT_019.md docs/OPERATOR_RUNBOOK_020C.md ./docs/

# The append-only store lives on a mounted volume, owned by the non-root user.
RUN mkdir -p /data/store /data/logs && chown -R cosmosiq:cosmosiq /app /data
USER cosmosiq

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    COSMOSIQ_PROFILE=test_offline \
    COSMOSIQ_STORE_DIR=/data/store

EXPOSE 8016

# OFFLINE health probe: exercises the PURE app dispatcher's /api/health route in-process.
# No network egress, no curl dependency, no production path — a sane offline liveness check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python3", "-c", "import sys; from cosmosiq_app.api import dispatch; r=dispatch({'method':'GET','path':'/api/health','query':{},'body':None}, store_dir='/data/store', now='1970-01-01T00:00:00Z'); sys.exit(0 if r.get('status')==200 and r.get('body',{}).get('status')=='ok' else 1)"]

# SAFE DEFAULT: the localhost-only operator app against the mounted store. NOT production.
# The app binds 127.0.0.1 and refuses a non-local host without an explicit --allow-remote.
CMD ["python3", "-m", "cosmosiq_app", "--store-dir", "/data/store", "--host", "127.0.0.1", "--port", "8016"]
