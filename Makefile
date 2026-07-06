# CosmosIQ — local-first deployment Makefile (IMPLEMENTATION-023C).
#
# Thin wiring over the EXISTING CLIs (cosmosiq_ops / cosmosiq_service / cosmosiq_app),
# using the repo convention `PYTHONPATH=src python3 -m <module> ...`. Nothing here is new
# behaviour; every target dispatches to a real, already-shipped command.
#
# SAFE BY DEFAULT. There is deliberately NO `run-production` target and NO line that flips
# PRODUCTION_24X7 or production_manual_review on. Production activation stays the explicit
# `cosmosiq_ops activate` + operator sign-off path (021C/022H) — never a Makefile shortcut.
# `run-shadow` is the strongest posture this file offers, and it is SHADOW_24X7 only.

PYTHON ?= python3
STORE  ?= ./_cosmosiq_store
BACKUP ?= ./_cosmosiq_backup
RUN    := PYTHONPATH=src $(PYTHON)

.PHONY: help test ci run-shadow prod-check backup restore smoke run-app

help: ## Show the available targets (SAFE by default; no production target exists)
	@echo "CosmosIQ — local-first make targets (SAFE by default; production is never a target here)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

test: ## Run the OFFLINE unittest suite
	$(RUN) -m unittest discover -s tests

ci: ## Run the operator CI gate (guardrail sweeps + offline suite)
	$(RUN) -m cosmosiq_ops ci-gate

run-shadow: ## Start the supervised service in SHADOW_24X7 (never production) against $(STORE)
	$(RUN) -m cosmosiq_service start --mode shadow_24x7 --store-dir $(STORE)

prod-check: ## Run the OFFLINE production-activation gate (refuses production by default)
	$(RUN) -m cosmosiq_ops prod-check --work-dir $(STORE)

backup: ## Snapshot $(STORE) into $(BACKUP) and verify the roundtrip
	$(RUN) -m cosmosiq_ops backup --store-dir $(STORE) --backup-dir $(BACKUP)

restore: ## Dry-run a restore check from $(BACKUP) (never writes; refuses a non-empty target)
	$(RUN) -m cosmosiq_ops restore-check --backup-path $(BACKUP) --target-dir $(STORE)_restored

smoke: ## Run the full operator chain OFFLINE against a fresh scratch dir
	$(RUN) -m cosmosiq_ops smoke --work-dir $(STORE)

run-app: ## Start the localhost-only operator app against $(STORE)
	$(RUN) -m cosmosiq_app --store-dir $(STORE)
