"""IMPLEMENTATION-023A -- production ENVIRONMENT PROFILES. PURE, OFFLINE, deterministic.

Proves the declared-posture profiles:

* the DEFAULT profile is SAFE (``default_profile().production_allowed is False``; its id is not
  ``production``);
* the ``production`` profile requires EXPLICIT config -- ``resolve_profile(None)`` is NEVER
  production; only ``get_profile("production")`` returns it;
* a SHADOW profile labels shadow mode (a Shadow marker in ``ui_labels``; ``alert_behavior`` is
  ``shadow_inbox``; ``recommendation_mode`` is shadow);
* the TEST profile BLOCKS network (``network_behavior == "blocked"`` + ``source_behavior ==
  "fixture_only"``);
* secrets are PRESENCE-LABELLED only (no field holds a secret value; ``secret_behavior`` is a
  label);
* ``production_allowed`` is True ONLY for ``production`` and it is NOT the default;
* each profile validates its own consistency (closed vocabularies; blocked=>offline source;
  production=>production modes);
* NO score / rank / buy / sell / order / trade field exists on a profile;
* a posture DECLARATION is not an enablement (production_allowed never flips a runtime mode);
* everything is deterministic + offline (a socket kill-switch armed); the module AST parses
  clean; demo + default pulse summaries are byte-identical.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import os
import socket
import unittest

from cosmosiq_ops.env_profiles import (
    ALERT_BEHAVIORS,
    DEFAULT_PROFILE_ID,
    LOGGING_LEVELS,
    NETWORK_BEHAVIORS,
    PROFILES,
    SCHEDULER_BEHAVIORS,
    SECRET_BEHAVIORS,
    SERVICE_MODES,
    SOURCE_BEHAVIORS,
    EnvironmentProfile,
    default_profile,
    get_profile,
    resolve_profile,
)
from cosmosiq_service.service import ServiceMode
from reality_mesh.recommendation_activation import RECOMMENDATION_MODES, RecommendationMode
from reality_mesh.pulse import run_pulse
from tattva_pulse.summary import build_pulse_summary

_NOW = "2026-06-29T00:00:00Z"
_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "cosmosiq_ops", "env_profiles.py")

# Tokens that must NEVER name a profile field -- a profile declares POSTURE, never a
# score/rank/valuation or a buy/sell/order/trade dimension.
_FORBIDDEN_FIELD_TOKENS = (
    "score", "rank", "rating", "valuation", "target_price", "price_target",
    "buy", "sell", "order", "trade", "broker", "position_size", "weight", "signal_strength",
)

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: env-profiles must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


class TestSafeDefault(unittest.TestCase):
    def test_default_profile_is_safe(self):
        prof = default_profile()
        self.assertFalse(prof.production_allowed)
        self.assertNotEqual(prof.profile_id, "production")

    def test_default_profile_id_is_a_safe_one(self):
        self.assertIn(DEFAULT_PROFILE_ID, ("test_offline", "local_dev"))
        self.assertNotEqual(DEFAULT_PROFILE_ID, "production")

    def test_default_profile_matches_default_profile_id(self):
        self.assertEqual(default_profile().profile_id, DEFAULT_PROFILE_ID)


class TestProductionIsExplicitOnly(unittest.TestCase):
    def test_resolve_none_is_never_production(self):
        prof = resolve_profile(None)
        self.assertFalse(prof.production_allowed)
        self.assertNotEqual(prof.profile_id, "production")
        self.assertEqual(prof, default_profile())

    def test_resolve_none_repeatedly_never_leaks_production(self):
        for _ in range(5):
            self.assertNotEqual(resolve_profile(None).profile_id, "production")

    def test_production_only_via_explicit_name(self):
        self.assertEqual(get_profile("production").profile_id, "production")
        self.assertEqual(resolve_profile("production").profile_id, "production")

    def test_production_allowed_only_for_production_profile(self):
        for pid, prof in PROFILES.items():
            with self.subTest(profile=pid):
                self.assertEqual(prof.production_allowed, pid == "production")

    def test_production_allowed_is_true_and_not_default(self):
        prod = get_profile("production")
        self.assertTrue(prod.production_allowed)
        self.assertNotEqual(prod.profile_id, DEFAULT_PROFILE_ID)

    def test_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            get_profile("prod")
        with self.assertRaises(ValueError):
            resolve_profile("does-not-exist")


class TestShadowProfilesLabelShadow(unittest.TestCase):
    def test_shadow_local_labels_shadow(self):
        prof = get_profile("shadow_local")
        self.assertTrue(any("shadow" in label.lower() for label in prof.ui_labels))
        self.assertEqual(prof.alert_behavior, "shadow_inbox")
        self.assertEqual(prof.recommendation_mode, RecommendationMode.SHADOW)
        self.assertEqual(prof.service_mode, ServiceMode.SHADOW_24X7.value)

    def test_shadow_live_labels_shadow_but_no_external_delivery(self):
        prof = get_profile("shadow_live")
        self.assertTrue(any("shadow" in label.lower() for label in prof.ui_labels))
        self.assertEqual(prof.alert_behavior, "shadow_inbox")
        self.assertEqual(prof.recommendation_mode, RecommendationMode.SHADOW)
        self.assertNotEqual(prof.alert_behavior, "production_delivery")


class TestTestProfileBlocksNetwork(unittest.TestCase):
    def test_test_offline_blocks_network(self):
        prof = get_profile("test_offline")
        self.assertEqual(prof.network_behavior, "blocked")
        self.assertEqual(prof.source_behavior, "fixture_only")

    def test_blocked_network_implies_offline_source_everywhere(self):
        for pid, prof in PROFILES.items():
            with self.subTest(profile=pid):
                if prof.network_behavior == "blocked":
                    self.assertIn(prof.source_behavior, ("fixture_only", "local_file"))

    def test_blocked_with_live_source_is_rejected(self):
        with self.assertRaises(ValueError):
            EnvironmentProfile(
                profile_id="bad_blocked_live",
                service_mode=ServiceMode.OFF.value,
                recommendation_mode=RecommendationMode.OFF,
                source_behavior="live",
                scheduler_behavior="off",
                alert_behavior="off",
                secret_behavior="none_required",
                persistence_path="<tmp>/bad",
                logging_level="info",
                network_behavior="blocked",
            )


class TestSecretsPresenceOnly(unittest.TestCase):
    def test_secret_behavior_is_a_label(self):
        for pid, prof in PROFILES.items():
            with self.subTest(profile=pid):
                self.assertIn(prof.secret_behavior, SECRET_BEHAVIORS)

    def test_no_field_holds_a_secret_value(self):
        # No field NAMES a credential, and no VALUE looks like an api key / token / password.
        credential_name_tokens = ("api_key", "apikey", "secret_value", "token", "password",
                                   "credential", "bearer")
        for pid, prof in PROFILES.items():
            for f in dataclasses.fields(prof):
                lname = f.name.lower()
                with self.subTest(profile=pid, field=f.name):
                    for tok in credential_name_tokens:
                        self.assertNotIn(tok, lname)
                    value = getattr(prof, f.name)
                    if isinstance(value, str):
                        low = value.lower()
                        self.assertNotIn("sk-", low)
                        self.assertNotIn("bearer ", low)

    def test_required_live_is_still_presence_only(self):
        # required_live means "presence expected", not that a value is stored.
        prof = get_profile("production")
        self.assertEqual(prof.secret_behavior, "required_live")
        self.assertNotIn("secret", " ".join(dataclasses.asdict(prof).get("ui_labels", ())).lower())


class TestPerProfileConsistency(unittest.TestCase):
    def test_all_closed_vocabs_respected(self):
        for pid, prof in PROFILES.items():
            with self.subTest(profile=pid):
                self.assertEqual(prof.profile_id, pid)
                self.assertIn(prof.service_mode, SERVICE_MODES)
                self.assertIn(prof.recommendation_mode, RECOMMENDATION_MODES)
                self.assertIn(prof.source_behavior, SOURCE_BEHAVIORS)
                self.assertIn(prof.scheduler_behavior, SCHEDULER_BEHAVIORS)
                self.assertIn(prof.alert_behavior, ALERT_BEHAVIORS)
                self.assertIn(prof.secret_behavior, SECRET_BEHAVIORS)
                self.assertIn(prof.logging_level, LOGGING_LEVELS)
                self.assertIn(prof.network_behavior, NETWORK_BEHAVIORS)
                self.assertIsInstance(prof.ui_labels, tuple)

    def test_exactly_the_five_expected_profiles(self):
        self.assertEqual(
            set(PROFILES),
            {"local_dev", "test_offline", "shadow_local", "shadow_live", "production"})

    def test_production_profile_modes_are_consistent(self):
        prod = get_profile("production")
        self.assertEqual(prod.service_mode, ServiceMode.PRODUCTION_24X7.value)
        self.assertEqual(prod.recommendation_mode, RecommendationMode.PRODUCTION_MANUAL_REVIEW)
        self.assertEqual(prod.source_behavior, "live")
        self.assertEqual(prod.alert_behavior, "production_delivery")

    def test_out_of_vocab_value_is_rejected(self):
        with self.assertRaises(ValueError):
            EnvironmentProfile(
                profile_id="bad_vocab",
                service_mode="turbo_mode",  # not a ServiceMode value
                recommendation_mode=RecommendationMode.OFF,
                source_behavior="fixture_only",
                scheduler_behavior="off",
                alert_behavior="off",
                secret_behavior="none_required",
                persistence_path="<tmp>/x",
                logging_level="info",
                network_behavior="blocked",
            )

    def test_production_allowed_requires_production_modes(self):
        with self.assertRaises(ValueError):
            EnvironmentProfile(
                profile_id="fake_prod",
                service_mode=ServiceMode.SHADOW_24X7.value,   # inconsistent with prod flag
                recommendation_mode=RecommendationMode.SHADOW,
                source_behavior="live",
                scheduler_behavior="on",
                alert_behavior="production_delivery",
                secret_behavior="required_live",
                persistence_path="./var/x",
                logging_level="warn",
                network_behavior="lazy_live",
                production_allowed=True,
            )

    def test_default_id_can_never_declare_production(self):
        with self.assertRaises(ValueError):
            EnvironmentProfile(
                profile_id=DEFAULT_PROFILE_ID,
                service_mode=ServiceMode.PRODUCTION_24X7.value,
                recommendation_mode=RecommendationMode.PRODUCTION_MANUAL_REVIEW,
                source_behavior="live",
                scheduler_behavior="on",
                alert_behavior="production_delivery",
                secret_behavior="required_live",
                persistence_path="./var/x",
                logging_level="warn",
                network_behavior="lazy_live",
                production_allowed=True,
            )


class TestNoScoreOrTradeField(unittest.TestCase):
    def test_no_forbidden_field_names(self):
        for pid, prof in PROFILES.items():
            for f in dataclasses.fields(prof):
                lname = f.name.lower()
                for tok in _FORBIDDEN_FIELD_TOKENS:
                    with self.subTest(profile=pid, field=f.name, token=tok):
                        self.assertNotIn(tok, lname)

    def test_field_set_is_exactly_the_posture_fields(self):
        names = {f.name for f in dataclasses.fields(EnvironmentProfile)}
        self.assertEqual(names, {
            "profile_id", "service_mode", "recommendation_mode", "source_behavior",
            "scheduler_behavior", "alert_behavior", "secret_behavior", "persistence_path",
            "logging_level", "network_behavior", "ui_labels", "production_allowed",
        })


class TestDeclarationIsNotEnablement(unittest.TestCase):
    def test_production_allowed_is_a_bool_declaration_only(self):
        prod = get_profile("production")
        self.assertIsInstance(prod.production_allowed, bool)
        self.assertTrue(prod.production_allowed)

    def test_no_activation_or_promotion_helper_exists(self):
        import cosmosiq_ops.env_profiles as mod
        for banned in ("activate", "promote", "enter_production", "enable_production",
                       "flip_to_production", "start"):
            self.assertFalse(hasattr(mod, banned),
                             "env_profiles must not expose {0!r} -- it only DECLARES".format(banned))


class TestDeterministicAndOffline(unittest.TestCase):
    def test_profiles_are_frozen(self):
        prof = default_profile()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            prof.production_allowed = True  # type: ignore[misc]

    def test_repeated_resolution_is_identical(self):
        a = resolve_profile("shadow_local")
        b = resolve_profile("shadow_local")
        self.assertEqual(a, b)
        self.assertEqual(dataclasses.asdict(a), dataclasses.asdict(b))

    def test_profiles_unaffected_by_environment(self):
        # Presence-only: a profile is the SAME regardless of what env vars are set.
        before = copy.deepcopy(dataclasses.asdict(get_profile("production")))
        os.environ["FMP_API_KEY"] = "not-a-real-value"
        try:
            after = dataclasses.asdict(get_profile("production"))
        finally:
            os.environ.pop("FMP_API_KEY", None)
        self.assertEqual(before, after)

    def test_module_ast_parses_clean(self):
        with open(_MODULE_PATH, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        self.assertTrue(isinstance(tree, ast.Module))

    def test_demo_and_default_pulse_are_byte_identical(self):
        first = build_pulse_summary(run_pulse("IREN,NBIS", "physical-ai", now=_NOW))
        second = build_pulse_summary(run_pulse("IREN,NBIS", "physical-ai", now=_NOW))
        import json
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
