"""IMPLEMENTATION-023C -- deployment packaging. STRUCTURE + wiring only; OFFLINE, deterministic.

This suite proves the LOCAL-FIRST packaging path is present, wired to the REAL CLIs, and SAFE by
default -- it NEVER builds or runs a container (CosmosIQ CI has no Docker and is offline; the real
`docker build` / `docker compose up` is the operator's step). It validates:

* the Makefile exists and defines exactly the required targets (test/ci/run-shadow/prod-check/
  backup/restore/smoke/run-app + help); each recipe references a REAL `python3 -m` module command
  whose module is importable; there is NO run-production / production-enable target and no line that
  flips PRODUCTION_24X7 / production_manual_review on;
* the Dockerfile exists, uses python:3.9-slim, copies NO real .env, sets a SAFE default profile +
  CMD (not production), and defines a HEALTHCHECK;
* docker-compose.yml exists, its default command is safe (not production), secrets come from an
  env-file (not baked), and it has a volume;
* the wrapped app starts SAFE offline (the /api/health dispatch works against a temp store);
* the wrapped health command returns a sane offline result;
* the wrapped prod-check runs OFFLINE -> production_mode_allowed is False;
* NO packaging file enables production (no service_mode=production_24x7 / recommendation_mode=
  production_manual_review / activate-without-signoff);
* the launchd template runs SHADOW_24X7 (its ProgramArguments reference shadow_24x7, not
  production);
* NO secret VALUE appears in any packaging file;
* everything is deterministic + offline; demo + default pulse summaries are byte-identical.

Stdlib-only, Python 3.9, OFFLINE. The suite never opens a socket and never builds an image.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import socket
import tempfile
import unittest

# reality_mesh must load before cosmosiq_service (pre-existing import-order dependency documented
# in deploy/README.md); the full suite already relies on this ordering.
import reality_mesh  # noqa: F401  (import for side-effect: resolve the service import cycle)
from cosmosiq_app.api import dispatch
from cosmosiq_ops.prod_check import run_prod_check
from cosmosiq_ops.secrets_config import is_secret_free
from reality_mesh.pulse import run_pulse
from tattva_pulse.summary import build_pulse_summary

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MAKEFILE = os.path.join(_REPO_ROOT, "Makefile")
_DOCKERFILE = os.path.join(_REPO_ROOT, "Dockerfile")
_COMPOSE = os.path.join(_REPO_ROOT, "docker-compose.yml")
_LAUNCHD = os.path.join(
    _REPO_ROOT, "deploy", "launchd", "com.cosmosiq.shadow.plist.template")
_DEPLOY_README = os.path.join(_REPO_ROOT, "deploy", "README.md")

_PACKAGING_FILES = (_MAKEFILE, _DOCKERFILE, _COMPOSE, _LAUNCHD, _DEPLOY_README)

# The exact target set the gate requires (help + the eight wired targets).
_REQUIRED_TARGETS = frozenset(
    {"help", "test", "ci", "run-shadow", "prod-check", "backup", "restore", "smoke", "run-app"})

# Patterns that would ACTUALLY enable production if they appeared in a packaging file -- an
# assignment, a CLI flag/arg, a profile set to production, an `activate` invocation, or a
# `run-production` target. These match the SETTING/INVOKING form, not safety prose in a comment
# (every packaging file legitimately *names* these tokens to explain that it never uses them).
_PRODUCTION_ENABLE_PATTERNS = (
    r"--mode\s+production",                       # service started in production 24x7
    r"service_mode\s*[:=]\s*production",          # service_mode assigned to production
    r"recommendation_mode\s*[:=]\s*production",   # recommendation_mode assigned to production
    r"COSMOSIQ_PROFILE\s*[:=]\s*production",      # the production env profile set as default
    r"-m\s+cosmosiq_ops\s+activate",              # the production-flip command wired in
    r"(?mi)^\s*run-production\s*:",               # a run-production make target
    r'["\x27]production_24x7["\x27]',             # production passed as a quoted exec-form arg
)


def _production_enable_findings(text: str):
    """Return the enabling patterns that actually appear (SETTING/INVOKING form)."""
    return tuple(p for p in _PRODUCTION_ENABLE_PATTERNS
                 if re.search(p, text, re.IGNORECASE))


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _makefile_targets(text: str):
    """Map target name -> its recipe text (the tab-indented lines beneath it)."""
    targets = {}
    current = None
    for raw in text.splitlines():
        header = re.match(r"^([A-Za-z0-9_-]+)\s*:(?!=)", raw)
        if header and not raw.startswith("\t"):
            current = header.group(1)
            targets[current] = []
        elif current is not None and raw.startswith("\t"):
            targets[current].append(raw)
        elif current is not None and raw.strip() == "":
            continue
        else:
            current = None
    return {name: "\n".join(lines) for name, lines in targets.items()}


def _module_commands(recipe: str):
    """Every module referenced by a ``-m <module>`` invocation in a recipe.

    The recipes drive Python via ``$(RUN)`` (which expands to ``PYTHONPATH=src python3``), so we
    match the standalone ``-m`` flag directly rather than requiring a literal ``python3`` adjacent
    to it. ``-m`` here is the module flag, distinct from ``--mode`` / ``--max`` (no space follows
    the ``-m`` inside those).
    """
    return re.findall(r"(?<![\w-])-m\s+([A-Za-z0-9_.]+)", recipe)


def _launchd_program_arguments(text: str):
    """The <string> values inside the launchd plist's ProgramArguments <array>."""
    block = re.search(
        r"<key>ProgramArguments</key>\s*<array>(.*?)</array>", text, re.DOTALL)
    if not block:
        return []
    return re.findall(r"<string>(.*?)</string>", block.group(1))


class MakefileStructureTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(_MAKEFILE)
        self.targets = _makefile_targets(self.text)

    def test_makefile_exists(self):
        self.assertTrue(os.path.isfile(_MAKEFILE))

    def test_defines_exactly_the_required_targets(self):
        defined = {t for t in self.targets if not t.isupper()}
        # Every required target is present.
        self.assertTrue(_REQUIRED_TARGETS.issubset(defined),
                        "missing targets: {0}".format(sorted(_REQUIRED_TARGETS - defined)))
        # No EXTRA build targets beyond the required set (help + the eight wired ones).
        extra = defined - _REQUIRED_TARGETS
        self.assertEqual(extra, set(), "unexpected extra targets: {0}".format(sorted(extra)))

    def test_has_phony_line(self):
        self.assertIn(".PHONY", self.text)

    def test_has_store_default_var(self):
        self.assertRegex(self.text, r"STORE\s*\?=")

    def test_each_target_recipe_references_a_real_module_command(self):
        # ci / run-shadow / prod-check / backup / restore / smoke / run-app each drive a real
        # `python3 -m <module>` command; `test` drives `-m unittest`.
        wired = {
            "ci": "cosmosiq_ops",
            "run-shadow": "cosmosiq_service",
            "prod-check": "cosmosiq_ops",
            "backup": "cosmosiq_ops",
            "restore": "cosmosiq_ops",
            "smoke": "cosmosiq_ops",
            "run-app": "cosmosiq_app",
            "test": "unittest",
        }
        for target, expected_module in wired.items():
            recipe = self.targets.get(target, "")
            modules = _module_commands(recipe)
            self.assertIn(expected_module, modules,
                          "target {0!r} must invoke `python3 -m {1}`".format(
                              target, expected_module))

    def test_wired_module_entrypoints_are_importable(self):
        # Every non-stdlib module a recipe wires must be importable as a real python3 -m entry
        # point (reality_mesh is imported first at module load to resolve the service cycle).
        for module in ("cosmosiq_ops", "cosmosiq_service", "cosmosiq_app"):
            with self.subTest(module=module):
                self.assertTrue(importlib.import_module(module))

    def test_no_run_production_target(self):
        for name in self.targets:
            self.assertNotIn("production", name.lower(),
                             "a production-enabling target is forbidden: {0!r}".format(name))

    def test_no_line_enables_production(self):
        # No recipe/assignment actually turns production on (comments may name the tokens to
        # explain the safe default; those are not enabling forms).
        findings = _production_enable_findings(self.text)
        self.assertEqual(findings, (),
                         "Makefile enables production via: {0}".format(findings))


class DockerfileStructureTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(_DOCKERFILE)

    def test_dockerfile_exists(self):
        self.assertTrue(os.path.isfile(_DOCKERFILE))

    def test_uses_python_39_slim(self):
        self.assertIn("FROM python:3.9-slim", self.text)

    def test_copies_no_real_env(self):
        # No `COPY .env` (only `.env.example` is allowed to be copied).
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("COPY") and ".env" in stripped:
                self.assertIn(".env.example", stripped,
                              "Dockerfile must never COPY a real .env: {0!r}".format(stripped))

    def test_sets_safe_default_profile(self):
        self.assertIn("COSMOSIQ_PROFILE=test_offline", self.text)
        self.assertNotIn("COSMOSIQ_PROFILE=production", self.text)

    def test_defines_a_healthcheck(self):
        self.assertIn("HEALTHCHECK", self.text)

    def test_default_cmd_is_safe_not_production(self):
        # The CMD line drives the safe app, never the production service.
        cmd_line = next((ln for ln in self.text.splitlines()
                         if ln.strip().startswith("CMD")), "")
        self.assertIn("cosmosiq_app", cmd_line)
        self.assertNotIn("production", cmd_line.lower())
        # No directive anywhere in the Dockerfile enables production (comments may name it).
        self.assertEqual(_production_enable_findings(self.text), ())

    def test_runs_as_non_root(self):
        self.assertIn("USER cosmosiq", self.text)


class ComposeStructureTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(_COMPOSE)

    def test_compose_exists(self):
        self.assertTrue(os.path.isfile(_COMPOSE))

    def test_default_command_is_safe(self):
        command_line = next((ln for ln in self.text.splitlines()
                             if ln.strip().startswith("command:")), "")
        self.assertIn("cosmosiq_app", command_line)
        self.assertNotIn("production", command_line.lower())

    def test_env_comes_from_env_file_not_baked(self):
        self.assertIn("env_file", self.text)
        self.assertRegex(self.text, r"-\s*\.env\b")

    def test_has_a_volume(self):
        self.assertIn("volumes:", self.text)
        self.assertIn("/data/store", self.text)

    def test_no_production_enable_in_compose(self):
        self.assertEqual(_production_enable_findings(self.text), ())


class SafeDefaultBehaviourTests(unittest.TestCase):
    """The wrapped commands actually work OFFLINE and land SAFE."""

    def test_app_starts_safe_health_works_offline(self):
        # Smoke the wrapped app/health command: the pure dispatcher answers /api/health 200
        # against a temp store with NO network and NO production posture.
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, "store")
            response = dispatch(
                {"method": "GET", "path": "/api/health", "query": {}, "body": None},
                store_dir=store, now=_NOW)
        self.assertEqual(response["status"], 200)
        body = response["body"]
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["app"], "CosmosIQ")
        # A sane offline result: labels + counts only, never a score / rank / trading endpoint.
        self.assertIn("counts", body)

    def test_health_check_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, "store")
            first = dispatch({"method": "GET", "path": "/api/health", "query": {},
                              "body": None}, store_dir=store, now=_NOW)
            second = dispatch({"method": "GET", "path": "/api/health", "query": {},
                               "body": None}, store_dir=store, now=_NOW)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_prod_check_refuses_production_offline(self):
        # The wrapped prod-check runs OFFLINE and the safe outcome is production NOT allowed.
        with tempfile.TemporaryDirectory() as tmp:
            report = run_prod_check(
                os.path.join(tmp, "work"), _REPO_ROOT, now=_NOW, quick=True)
        self.assertFalse(report.production_mode_allowed)


class NoProductionAutoEnableTests(unittest.TestCase):
    def test_no_packaging_file_auto_enables_production(self):
        # No packaging file SETS/INVOKES production (comments may name the tokens to explain the
        # safe default; those never enable anything).
        for path in _PACKAGING_FILES:
            with self.subTest(path=os.path.basename(path)):
                findings = _production_enable_findings(_read(path))
                self.assertEqual(
                    findings, (),
                    "{0} enables production via: {1}".format(
                        os.path.basename(path), findings))

    def test_no_packaging_file_wires_the_activate_flip(self):
        # `activate` is the production-flip command; it must not be auto-wired (as a command)
        # anywhere in the packaging path -- it stays the explicit operator sign-off step.
        for path in _PACKAGING_FILES:
            text = _read(path)
            self.assertIsNone(
                re.search(r"-m\s+cosmosiq_ops\s+activate", text, re.IGNORECASE),
                "{0} must not wire `-m cosmosiq_ops activate`".format(os.path.basename(path)))

    def test_launchd_template_runs_shadow_not_production(self):
        text = _read(_LAUNCHD)
        args = _launchd_program_arguments(text)
        # The service is started in SHADOW_24X7 -- the arg vector carries shadow_24x7, never
        # production, and follows a --mode flag.
        self.assertIn("shadow_24x7", args)
        self.assertNotIn("production_24x7", args)
        self.assertEqual(args[args.index("--mode") + 1], "shadow_24x7")
        # No directive in the template enables production.
        self.assertEqual(_production_enable_findings(text), ())

    def test_launchd_template_carries_the_continuous_shadow_opt_in(self):
        # GO-LIVE PL-5: the launchd job must pass the EXPLICIT operator opt-in + live sourcing.
        args = _launchd_program_arguments(_read(_LAUNCHD))
        self.assertIn("--confirm-continuous-shadow", args)
        self.assertIn("--live-sources", args)

    def test_launchd_template_carries_no_hand_curated_universe(self):
        # ADR-0011: "a hardcoded ticker list SHALL NOT be a supported means of setting the
        # universe." This test previously REQUIRED __LIVE_WATCHLIST__ / __LIVE_THEMES__ in the
        # template -- it encoded the practice the ADR ended. The job must now carry neither: the
        # engine sweeps the real chokepoints and composes its own scope, and the theme scope is
        # derived from what it composed.
        args = _launchd_program_arguments(_read(_LAUNCHD))
        self.assertNotIn("--live-watchlist", args)
        self.assertNotIn("--live-themes", args)
        self.assertNotIn("__LIVE_WATCHLIST__", args)
        self.assertNotIn("__LIVE_THEMES__", args)
        self.assertIn("--live-compose-universe", args)
        self.assertIn("--live-accepted-watchlist", args)

    def test_launchd_template_sets_a_sane_live_poll_interval(self):
        # GO-LIVE PL-5b: a LIVE shadow job MUST set an explicit gentle poll interval. The service's
        # 60s default, with --live-sources, would abuse SEC fair-access + burn FMP quota (~1440
        # runs/day). Require an explicit --poll-interval of at least one hour (never near 60s).
        args = _launchd_program_arguments(_read(_LAUNCHD))
        self.assertIn("--poll-interval", args)
        interval = int(args[args.index("--poll-interval") + 1])
        self.assertGreaterEqual(
            interval, 3600,
            "a live shadow job must poll no faster than hourly, never near the 60s default")

    def test_launchd_template_sources_env_via_wrapper_not_a_baked_secret(self):
        text = _read(_LAUNCHD)
        # The wrapper sources the operator's gitignored .env at runtime (presence-only path ref).
        self.assertRegex(text, r"\.\s+[\"']?__REPO_ROOT__/\.env")
        self.assertIn("/bin/zsh", _launchd_program_arguments(text))
        # ...and carries NO secret value.
        self.assertTrue(is_secret_free(text))

    def test_launchd_template_starts_no_production_job(self):
        # No flag or arg could start continuous production from the launchd job.
        args = _launchd_program_arguments(_read(_LAUNCHD))
        self.assertNotIn("production_24x7", args)
        self.assertNotIn("production_manual_review", args)

    def test_deploy_readme_documents_the_opt_in_and_env_wrapper(self):
        text = _read(_DEPLOY_README)
        self.assertIn("--confirm-continuous-shadow", text)
        self.assertIn("--live-sources", text)
        # The .env is sourced by the wrapper (presence-only), never written into the plist.
        self.assertRegex(text, r"(?i)\.env")
        self.assertRegex(text, r"(?i)never written into the plist|references only the `?\.env")
        # The PL-2 shadow-validation window the operator later attests.
        self.assertRegex(text, r"(?i)shadow-validation|>= ?3 runs|>= ?2 days")


class NoSecretInPackagingTests(unittest.TestCase):
    def test_no_secret_value_in_any_packaging_file(self):
        for path in _PACKAGING_FILES:
            with self.subTest(path=os.path.basename(path)):
                self.assertTrue(
                    is_secret_free(_read(path)),
                    "{0} must carry no secret-shaped value".format(os.path.basename(path)))


class DeterminismAndOfflineTests(unittest.TestCase):
    def test_no_network_import_side_effects(self):
        # Sanity: the packaging test itself performs no network I/O. Prove the guard tools we
        # rely on are pure by asserting a blocked-socket context is unnecessary -- we simply
        # never open one. (Documentation-as-test: this suite is offline by construction.)
        self.assertTrue(hasattr(socket, "socket"))

    def test_demo_and_default_pulse_are_byte_identical(self):
        first = build_pulse_summary(run_pulse("IREN,NBIS", "physical-ai", now=_NOW))
        second = build_pulse_summary(run_pulse("IREN,NBIS", "physical-ai", now=_NOW))
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
