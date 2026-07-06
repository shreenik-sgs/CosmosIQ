"""IMPLEMENTATION-023I -- a DOC-LINT for the 4 consolidated operator docs. OFFLINE + deterministic.

This test makes CosmosIQ's operator documentation trustworthy the same way the code is: it PROVES
every command the docs tell an operator to run is REAL, that no secret VALUE leaks into a doc, that
the honest production-gating is stated (never "production in one command"), and that every required
topic + the seven incident playbooks + the rollback ladder are actually covered.

How the command check is REAL (not a rubber stamp): it parses every fenced code block in the docs,
joins backslash-continued lines, and for each ``python3 -m <module> ...`` invocation it:

* imports ``<module>.__main__`` (a genuine import -- an invented module fails here);
* introspects the module's ACTUAL argparse subparsers / options (never a hand-maintained list);
* asserts the cited SUBCOMMAND is a real subcommand of that module, and every cited ``--flag`` is a
  real option of that subcommand (so a fabricated command OR a fabricated flag -- e.g. ``--live-sec``
  as a runnable flag -- fails the suite).

Offline: imports + file reads only; no network, no subprocess, no wall clock.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import unittest

from cosmosiq_service.activation import MODE_LADDER, ROLLBACK_TRIGGERS

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS_DIR = os.path.join(_REPO_ROOT, "docs")

RUNBOOK = "OPERATOR_RUNBOOK.md"
DEPLOYMENT = "DEPLOYMENT_GUIDE.md"
INCIDENTS = "INCIDENT_PLAYBOOKS.md"
ROLLBACK = "ROLLBACK_GUIDE.md"
ALL_DOCS = (RUNBOOK, DEPLOYMENT, INCIDENTS, ROLLBACK)

# cosmosiq_app builds its parser inline in main(); mirror its frozen option set from
# src/cosmosiq_app/__main__.py so an invented app flag is still caught.
_APP_OPTIONS = {"--store-dir", "--host", "--port", "--allow-remote", "-h", "--help"}


def _read(name):
    with open(os.path.join(_DOCS_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _all_text():
    return "\n".join(_read(name) for name in ALL_DOCS)


# --------------------------------------------------------------------------- #
# Real argparse introspection (never a hand-maintained command list)            #
# --------------------------------------------------------------------------- #
def _subcommands_of(parser):
    """{subcommand: set(option_strings)} for a parser's subparsers, or None if it has none."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            out = {}
            for name, subparser in action.choices.items():
                opts = set()
                for sub_action in subparser._actions:
                    opts.update(sub_action.option_strings)
                out[name] = opts
            return out
    return None


def _module_spec(module):
    """(is_real, {subcmd: opts} or None, top_options).

    Imports ``<module>.__main__`` for real; introspects its actual argparse surface.
    """
    try:
        main_mod = importlib.import_module(module + ".__main__")
    except ImportError:
        return False, None, set()
    if hasattr(main_mod, "_build_parser"):
        parser = main_mod._build_parser()
        top = set()
        for action in parser._actions:
            top.update(action.option_strings)
        return True, _subcommands_of(parser), top
    # No _build_parser: parser built inline in main() (cosmosiq_app).
    if module == "cosmosiq_app":
        return True, None, set(_APP_OPTIONS)
    return True, None, set()


# --------------------------------------------------------------------------- #
# Parse the docs' fenced code blocks into cited ``python3 -m`` commands          #
# --------------------------------------------------------------------------- #
def _fenced_blocks(text):
    blocks = []
    current = None
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
            continue
        if current is not None:
            current.append(line)
    return blocks


def _logical_lines(block):
    """Join backslash-continued physical lines into one logical command line each."""
    out = []
    buffer = ""
    for line in block.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
        else:
            buffer += stripped
            out.append(buffer)
            buffer = ""
    if buffer:
        out.append(buffer)
    return out


def _cited_commands(text):
    """[(module, subcommand_or_None, [flags], raw_line)] for every fenced python3 -m invocation."""
    cited = []
    for block in _fenced_blocks(text):
        for line in _logical_lines(block):
            if "python3 -m " not in line:
                continue
            tokens = [t.strip("[]") for t in line.split()]
            if "-m" not in tokens:
                continue
            idx = tokens.index("-m")
            if idx + 1 >= len(tokens):
                continue
            module = tokens[idx + 1]
            rest = tokens[idx + 2:]
            subcommand = None
            for tok in rest:
                if not tok.startswith("-"):
                    subcommand = tok
                    break
            flags = [tok.split("=", 1)[0] for tok in rest if tok.startswith("--")]
            if "-h" in rest:
                flags.append("-h")
            cited.append((module, subcommand, flags, line))
    return cited


class OperatorDocsExistTest(unittest.TestCase):
    def test_all_four_docs_exist_and_are_nontrivial(self):
        for name in ALL_DOCS:
            path = os.path.join(_DOCS_DIR, name)
            self.assertTrue(os.path.isfile(path), "missing doc: {0}".format(name))
            body = _read(name)
            self.assertGreater(len(body), 1500, "doc too thin: {0}".format(name))
            self.assertIn("#", body, "doc has no headings: {0}".format(name))
            self.assertIn("python3 -m", body, "doc cites no commands: {0}".format(name))


class CommandsAreRealTest(unittest.TestCase):
    """Every cited ``python3 -m`` command references a REAL module + subcommand + flags."""

    def setUp(self):
        self.cited = _cited_commands(_all_text())

    def test_at_least_a_dozen_commands_are_checked(self):
        # A guard so the lint cannot silently pass by finding nothing to validate.
        self.assertGreaterEqual(len(self.cited), 15,
                                "expected the docs to cite many real commands")

    def test_every_cited_command_is_real(self):
        for module, subcommand, flags, line in self.cited:
            is_real, subcommands, top_options = _module_spec(module)
            self.assertTrue(is_real, "invented / unimportable module in: {0}".format(line))
            if subcommands is not None:
                self.assertIsNotNone(
                    subcommand, "module {0} needs a subcommand: {1}".format(module, line))
                self.assertIn(
                    subcommand, subcommands,
                    "invented subcommand {0!r} in: {1}".format(subcommand, line))
                valid = set(subcommands[subcommand]) | top_options | {"-h", "--help"}
            else:
                valid = set(top_options) | {"-h", "--help"}
            for flag in flags:
                self.assertIn(
                    flag, valid,
                    "invented flag {0!r} for {1} in: {2}".format(flag, module, line))

    def test_key_real_subcommands_are_actually_cited(self):
        used = {(m, s) for (m, s, _f, _l) in self.cited}
        expected = {
            ("cosmosiq_service", "start"), ("cosmosiq_service", "stop"),
            ("cosmosiq_service", "status"), ("cosmosiq_service", "pause"),
            ("cosmosiq_service", "resume"), ("cosmosiq_service", "run-once"),
            ("cosmosiq_ops", "prod-check"), ("cosmosiq_ops", "activate"),
            ("cosmosiq_ops", "rollback"), ("cosmosiq_ops", "backup"),
            ("cosmosiq_ops", "restore"), ("cosmosiq_ops", "verify"),
            ("cosmosiq_ops", "backup-health"), ("cosmosiq_ops", "security-audit"),
            ("cosmosiq_ops", "shadow-validate"), ("cosmosiq_ops", "env"),
        }
        missing = expected - used
        self.assertEqual(set(), missing, "these real commands should be documented: {0}".format(
            sorted(missing)))


class NoSecretValueTest(unittest.TestCase):
    """Docs carry env var NAMES + presence only -- never a secret VALUE."""

    _SECRET_ASSIGN = re.compile(r"\b(FMP_API_KEY|COSMOSIQ_ALERT_EMAIL_[A-Z]+)\s*=\s*\S")
    _FORBIDDEN_SUBSTRINGS = ("<your-fmp-api-key>",)

    def test_no_secret_value_assigned(self):
        for name in ALL_DOCS:
            body = _read(name)
            self.assertIsNone(self._SECRET_ASSIGN.search(body),
                              "a secret-bearing var is assigned a value in {0}".format(name))
            for bad in self._FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(bad, body,
                                 "placeholder secret {0!r} leaked into {1}".format(bad, name))

    def test_env_var_names_are_present(self):
        runbook = _read(RUNBOOK)
        for name in ("SEC_USER_AGENT", "FMP_API_KEY", "COSMOSIQ_ALERT_EMAIL_SENDER"):
            self.assertIn(name, runbook, "env NAME {0} should be documented".format(name))


class HonestProductionGatingTest(unittest.TestCase):
    def test_gating_is_stated(self):
        text = _all_text().lower()
        self.assertIn("production_mode_allowed=false", text.replace(" ", ""),
                      "docs must show prod-check refusing production")
        self.assertTrue("sign-off" in text or "signoff" in text,
                        "docs must state an operator sign-off is required")
        self.assertTrue("manual_review" in text or "manual review" in text,
                        "docs must state the manual review items")
        self.assertIn("--live-sec", _read(RUNBOOK),
                      "the honest no-live-sec-flag limitation must be carried forward")

    def test_no_one_command_production_claim(self):
        text = _all_text()
        forbidden = (
            re.compile(r"production\s+in\s+one\s+command", re.I),
            re.compile(r"production\s+is\s+one\s+command", re.I),
            re.compile(r"just run this[^.\n]*production", re.I),
        )
        for pattern in forbidden:
            self.assertIsNone(pattern.search(text),
                              "docs imply production is one command: {0}".format(pattern.pattern))


class TopicCoverageTest(unittest.TestCase):
    def test_runbook_topics(self):
        body = _read(RUNBOOK).lower()
        for topic in ("setup", "environment variable", "shadow_24x7", "production",
                      "prod-check", "/alerts", "/runs", "/replay", "/api/observability",
                      "pause", "resume", "backup", "restore", "rollback"):
            self.assertIn(topic, body, "runbook missing topic: {0}".format(topic))

    def test_deployment_topics(self):
        body = _read(DEPLOYMENT).lower()
        for topic in ("docker", "compose", "makefile", "launchd", "profile", "secret",
                      "observability", "prod-check", "backup", "restore"):
            self.assertIn(topic, body, "deployment guide missing topic: {0}".format(topic))

    def test_seven_incident_playbooks(self):
        body = _read(INCIDENTS).lower()
        for playbook in ("source failure", "agent failure", "dq", "false-positive",
                         "fixture leakage", "secret leak", "storage corruption"):
            self.assertIn(playbook, body, "incident playbooks missing: {0}".format(playbook))

    def test_rollback_ladder_and_all_triggers(self):
        body = _read(ROLLBACK)
        lowered = body.lower()
        # the full mode ladder, from the real MODE_LADDER (case-insensitive)
        for mode in MODE_LADDER:
            self.assertIn(mode.value.lower(), lowered,
                          "rollback guide missing ladder mode: {0}".format(mode.value))
        self.assertTrue("never upgrade" in lowered,
                        "rollback guide must state rollback never upgrades")
        # every REAL rollback trigger name must be documented
        for trigger in ROLLBACK_TRIGGERS:
            self.assertIn(trigger, body,
                          "rollback guide missing trigger: {0}".format(trigger))


if __name__ == "__main__":
    unittest.main()
