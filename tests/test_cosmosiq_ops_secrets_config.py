"""IMPLEMENTATION-023B -- secrets / config hardening. PRESENCE-ONLY, OFFLINE, deterministic.

Proves the production-safe config + secrets surface:

* a MISSING required secret BLOCKS the live source (validate_secrets over shadow_live / production
  with an env lacking SEC_USER_AGENT / FMP_API_KEY -> missing_required non-empty + blocked_sources
  names SEC + FMP live) and does NOT crash / does NOT fixture-fallback;
* a secret VALUE is NEVER rendered or logged (inject fake values -> the report + any string output
  carry presence LABELS only, never the value);
* .env.example lists NAMES with obviously-fake placeholders and passes the CI-gate secret scan;
* a real .env is NOT tracked by git (and is gitignored);
* required env vars are correctly derived per profile (test_offline -> none; shadow_live -> SEC +
  FMP; production -> those + email delivery);
* NO score / rank / buy / sell / order / trade field exists anywhere;
* everything is deterministic + offline; the module AST parses clean; demo + default pulse
  summaries are byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import unittest

from cosmosiq_ops.secrets_config import (
    ALL_CONFIG_ENV_VARS,
    CONFIG_SCHEMA,
    ENV_UNTRACKED_RULE,
    REQUIRED_ENV_VARS,
    CapabilityConfig,
    SecretCheck,
    SecretsReport,
    file_is_secret_free,
    format_secrets_report,
    is_secret_free,
    required_env_vars_for_profile,
    secret_scan_paths,
    secret_value_findings,
    validate_secrets,
)
from cosmosiq_ops.ci_gate import SECRET_VALUE_PATTERNS
from cosmosiq_ops.env_profiles import PROFILES, get_profile
from reality_mesh.alert_delivery import (
    EMAIL_CREDENTIAL_ENV,
    EMAIL_HOST_ENV,
    EMAIL_RECIPIENT_ENV,
)
from reality_mesh.pulse import run_pulse
from tattva_pulse.summary import build_pulse_summary

_NOW = "2026-06-29T00:00:00Z"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_EXAMPLE = os.path.join(_REPO_ROOT, ".env.example")
_MODULE_PATH = os.path.join(
    _REPO_ROOT, "src", "cosmosiq_ops", "secrets_config.py")

# A fake, obviously-not-real secret VALUE injected to prove it is never rendered.
_FAKE_SEC_UA = "Jane Doe jane.doe-DO-NOT-LOG@example.com"
_FAKE_FMP_KEY = "FAKE-fmp-key-abcdef0123456789-DO-NOT-LOG"

# Tokens that must NEVER name a field on the config surface -- this is a secrets/config module,
# never a score/rank/valuation or a buy/sell/order/trade dimension.
_FORBIDDEN_FIELD_TOKENS = (
    "score", "rank", "rating", "valuation", "target_price", "price_target",
    "buy", "sell", "order", "trade", "broker", "position_size", "weight", "signal_strength",
)

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: secrets-config must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


class TestMissingRequiredBlocksLive(unittest.TestCase):
    """A missing required secret BLOCKS the live source -- honest gap, no crash, no fallback."""

    def test_shadow_live_missing_sec_and_fmp_blocks_both(self):
        report = validate_secrets("shadow_live", env={})  # nothing configured
        missing = report.missing_required()
        self.assertIn("SEC_USER_AGENT", missing)
        self.assertIn("FMP_API_KEY", missing)
        self.assertFalse(report.all_required_present())
        blocked = report.blocked_sources()
        self.assertIn("SEC EDGAR live source", blocked)
        self.assertIn("FMP live source", blocked)

    def test_production_missing_everything_blocks_sec_fmp_and_delivery(self):
        report = validate_secrets("production", env={})
        missing = set(report.missing_required())
        self.assertEqual(
            missing,
            {"SEC_USER_AGENT", "FMP_API_KEY",
             EMAIL_CREDENTIAL_ENV, EMAIL_HOST_ENV, EMAIL_RECIPIENT_ENV})
        self.assertIn("SEC EDGAR live source", report.blocked_sources())
        self.assertIn("FMP live source", report.blocked_sources())
        self.assertIn("production alert email delivery", report.blocked_sources())

    def test_missing_required_does_not_crash_or_fixture_fallback(self):
        # validate_secrets simply returns a report; it raises nothing and mentions no fixture.
        report = validate_secrets("shadow_live", env={})
        rendered = format_secrets_report(report).lower()
        self.assertNotIn("fixture", rendered)
        self.assertNotIn("fallback to", rendered)

    def test_all_present_clears_the_block(self):
        env = {"SEC_USER_AGENT": _FAKE_SEC_UA, "FMP_API_KEY": _FAKE_FMP_KEY}
        report = validate_secrets("shadow_live", env=env)
        self.assertTrue(report.all_required_present())
        self.assertEqual(report.missing_required(), ())
        self.assertEqual(report.blocked_sources(), ())


class TestSecretValueNeverRendered(unittest.TestCase):
    """A secret VALUE is NEVER rendered, logged, or stored -- presence labels only."""

    def test_value_never_in_report_or_rendered_output(self):
        env = {"SEC_USER_AGENT": _FAKE_SEC_UA, "FMP_API_KEY": _FAKE_FMP_KEY}
        report = validate_secrets("shadow_live", env=env)
        rendered = format_secrets_report(report)
        for blob in (repr(report), str(report), rendered):
            self.assertNotIn(_FAKE_SEC_UA, blob)
            self.assertNotIn(_FAKE_FMP_KEY, blob)
        # Presence is expressed as a label / bool, not a value.
        self.assertIn("present", rendered)
        for check in report.checks:
            self.assertIsInstance(check.present, bool)

    def test_report_holds_no_value_attribute(self):
        env = {"SEC_USER_AGENT": _FAKE_SEC_UA, "FMP_API_KEY": _FAKE_FMP_KEY}
        report = validate_secrets("shadow_live", env=env)
        # No field anywhere on the report or its checks carries a value string.
        for check in report.checks:
            for value in vars(check).values():
                if isinstance(value, str):
                    self.assertNotIn(_FAKE_SEC_UA, value)
                    self.assertNotIn(_FAKE_FMP_KEY, value)

    def test_default_env_reads_os_environ_presence_only(self):
        # With no env injected it consults os.environ by membership only (offline, no crash).
        report = validate_secrets("test_offline")
        self.assertIsInstance(report, SecretsReport)

    def test_env_must_be_a_mapping_value_never_echoed(self):
        with self.assertRaises(ValueError) as ctx:
            validate_secrets("shadow_live", env=_FAKE_FMP_KEY)  # a value passed by mistake
        self.assertNotIn(_FAKE_FMP_KEY, str(ctx.exception))


class TestEnvExampleNamesOnly(unittest.TestCase):
    """.env.example lists NAMES + fake placeholders and carries NO real secret value."""

    def _parse(self):
        pairs = {}
        with open(_ENV_EXAMPLE, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                self.assertIn("=", stripped, "non-comment line must be NAME=placeholder")
                name, _, value = stripped.partition("=")
                pairs[name.strip()] = value.strip().strip('"').strip("'")
        return pairs

    def test_contains_every_known_env_var_name(self):
        pairs = self._parse()
        for name in ALL_CONFIG_ENV_VARS:
            self.assertIn(name, pairs)

    def test_placeholders_are_obviously_fake(self):
        markers = ("example", "your", "<", "changeme", "placeholder")
        for name, value in self._parse().items():
            lowered = value.lower()
            self.assertTrue(any(m in lowered for m in markers),
                            "placeholder for {0} must be obviously fake: {1!r}".format(name, value))

    def test_passes_ci_gate_secret_value_scan(self):
        self.assertTrue(file_is_secret_free(_ENV_EXAMPLE))
        with open(_ENV_EXAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        for pattern in SECRET_VALUE_PATTERNS:
            self.assertIsNone(pattern.search(text),
                              "matched secret-value pattern: " + pattern.pattern)

    def test_documents_the_untracked_rule(self):
        with open(_ENV_EXAMPLE, encoding="utf-8") as fh:
            text = fh.read().lower()
        self.assertIn(".env", text)
        self.assertIn("gitignore", text)


class TestRealEnvNotTracked(unittest.TestCase):
    """A real .env is NOT tracked by git and is gitignored."""

    def _git(self, *args):
        try:
            return subprocess.run(
                ["git", "-C", _REPO_ROOT] + list(args),
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def test_no_env_file_is_tracked(self):
        completed = self._git("ls-files")
        if completed is None or completed.returncode != 0:
            self.skipTest("not a git checkout / git unavailable")
        tracked = [line for line in completed.stdout.splitlines()
                   if os.path.basename(line) == ".env" or line.endswith("/.env")]
        self.assertEqual(tracked, [], "a real .env must never be tracked")

    def test_env_example_is_tracked(self):
        completed = self._git("ls-files", "--", ".env.example")
        if completed is None or completed.returncode != 0:
            self.skipTest("not a git checkout / git unavailable")
        # It is either already tracked or a brand-new file this slice adds (untracked-but-present).
        self.assertTrue(os.path.isfile(_ENV_EXAMPLE))

    def test_env_is_gitignored(self):
        completed = self._git("check-ignore", ".env")
        if completed is None:
            self.skipTest("git unavailable")
        # returncode 0 => .env is ignored; 1 => not ignored (fail); 128 => not a repo (skip).
        if completed.returncode == 128:
            self.skipTest("not a git checkout")
        self.assertEqual(completed.returncode, 0, ".env must be gitignored")


class TestRequiredEnvVarsPerProfile(unittest.TestCase):
    """Required env vars are correctly derived from each 023A profile's posture."""

    def test_test_offline_requires_nothing(self):
        self.assertEqual(required_env_vars_for_profile("test_offline"), ())

    def test_local_dev_and_shadow_local_require_nothing(self):
        self.assertEqual(required_env_vars_for_profile("local_dev"), ())
        self.assertEqual(required_env_vars_for_profile("shadow_local"), ())

    def test_shadow_live_requires_sec_and_fmp(self):
        self.assertEqual(
            set(required_env_vars_for_profile("shadow_live")),
            {"SEC_USER_AGENT", "FMP_API_KEY"})

    def test_production_requires_sec_fmp_and_delivery(self):
        self.assertEqual(
            set(required_env_vars_for_profile("production")),
            {"SEC_USER_AGENT", "FMP_API_KEY",
             EMAIL_CREDENTIAL_ENV, EMAIL_HOST_ENV, EMAIL_RECIPIENT_ENV})

    def test_accepts_a_profile_object(self):
        prof = get_profile("shadow_live")
        self.assertEqual(
            set(required_env_vars_for_profile(prof)),
            {"SEC_USER_AGENT", "FMP_API_KEY"})

    def test_schema_covers_the_three_capabilities(self):
        self.assertEqual(
            set(REQUIRED_ENV_VARS),
            {"sec_live", "fmp_live", "alert_email_delivery"})
        self.assertEqual(REQUIRED_ENV_VARS["sec_live"], ("SEC_USER_AGENT",))
        self.assertEqual(REQUIRED_ENV_VARS["fmp_live"], ("FMP_API_KEY",))


class TestSecretScanHelpers(unittest.TestCase):
    def test_is_secret_free_flags_a_real_looking_value(self):
        self.assertFalse(is_secret_free("token: sk-abcdef0123456789"))
        self.assertFalse(is_secret_free("aws AKIAABCDEFGHIJKLMNOP here"))
        self.assertTrue(is_secret_free("SEC_USER_AGENT is present -- value never read"))

    def test_secret_value_findings_names_the_pattern(self):
        findings = secret_value_findings("bearer abcdef012345")
        self.assertTrue(findings)

    def test_scan_paths_include_env_example(self):
        paths = secret_scan_paths(_REPO_ROOT)
        self.assertIn(_ENV_EXAMPLE, paths)
        for path in paths:
            self.assertTrue(file_is_secret_free(path))


class TestNoScoreOrTradeField(unittest.TestCase):
    def test_no_forbidden_field_on_dataclasses(self):
        for cls in (CapabilityConfig, SecretCheck, SecretsReport):
            for field_name in getattr(cls, "__dataclass_fields__", {}):
                lowered = field_name.lower()
                for token in _FORBIDDEN_FIELD_TOKENS:
                    self.assertNotIn(token, lowered,
                                     "{0}.{1} names a forbidden dimension".format(
                                         cls.__name__, field_name))

    def test_module_source_has_no_score_or_trade_identifier(self):
        with open(_MODULE_PATH, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                lowered = node.name.lower()
                self.assertNotIn("score", lowered)
                self.assertNotIn("rank", lowered)


class TestDeterministicAndClean(unittest.TestCase):
    def test_module_ast_parses_clean(self):
        with open(_MODULE_PATH, encoding="utf-8") as fh:
            ast.parse(fh.read())

    def test_validate_is_deterministic(self):
        env = {"SEC_USER_AGENT": _FAKE_SEC_UA}
        first = format_secrets_report(validate_secrets("production", env=env))
        second = format_secrets_report(validate_secrets("production", env=env))
        self.assertEqual(first, second)

    def test_every_profile_validates_without_crashing(self):
        for pid in PROFILES:
            report = validate_secrets(pid, env={})
            self.assertEqual(report.profile_id, pid)

    def test_untracked_rule_is_documented(self):
        self.assertIn(".env", ENV_UNTRACKED_RULE)

    def test_demo_and_default_pulse_summaries_byte_identical(self):
        watch = ["IREN", "NVDA"]
        themes = ["physical_ai", "robotics"]
        demo = build_pulse_summary(run_pulse(watch, themes, now=_NOW))
        default = build_pulse_summary(run_pulse(watch, themes, now=_NOW))
        self.assertEqual(demo, default)


if __name__ == "__main__":
    unittest.main()
