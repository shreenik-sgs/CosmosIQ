"""Layer-system migration + compatibility layer (retired Sanskrit -> approved English).

Verifies the INTERNAL layer vocabulary now serializes the eight approved English identifiers,
that the retired Sanskrit names still validate via the compatibility layer, and that the
migrated ``cosmosiq_pulse`` CLI runs offline (delegating to ``tattva_pulse``). Deterministic,
offline, stdlib-only.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import reality_mesh as rm
from reality_mesh import labels as L
from reality_mesh.agents import AgentDescriptor
from reality_mesh.models import HandoffEnvelope
from reality_mesh.registry import build_default_registry


_APPROVED = {
    "foundation",
    "intelligence_governance",
    "reality_intelligence",
    "opportunity_discovery",
    "investment_diligence",
    "portfolio_intelligence",
    "execution_preview",
    "learning_feedback",
}


class LayersVocabularyTests(unittest.TestCase):
    def test_english_layers_present(self):
        self.assertTrue(_APPROVED.issubset(L.LAYERS))

    def test_no_sanskrit_layer_values_remain(self):
        retired = {"Adhara", "Buddhi", "Tattva", "Sphurana",
                   "Nivesha", "Saarathi", "Kriya", "Anubhava"}
        self.assertEqual(retired & L.LAYERS, set())

    def test_diagnostic_surfaces_unchanged(self):
        self.assertIn("DataQuality", L.LAYERS)
        self.assertIn("RedTeam", L.LAYERS)

    def test_display_map_covers_every_layer(self):
        for value in L.LAYERS:
            self.assertIn(value, L.LAYER_DISPLAY)
            self.assertTrue(L.LAYER_DISPLAY[value].endswith("Layer"))
        self.assertEqual(L.LAYER_DISPLAY["reality_intelligence"], "Reality Intelligence Layer")
        self.assertEqual(L.LAYER_DISPLAY["learning_feedback"], "Learning & Feedback Layer")


class LegacyAliasTests(unittest.TestCase):
    def test_legacy_map_covers_all_eight(self):
        self.assertEqual(
            set(L.LEGACY_LAYER_ALIASES),
            {"adhara", "buddhi", "tattva", "sphurana",
             "nivesha", "saarathi", "kriya", "anubhava"})
        # every legacy name maps to an approved English value
        self.assertEqual(set(L.LEGACY_LAYER_ALIASES.values()), _APPROVED)

    def test_normalize_layer_from_legacy(self):
        self.assertEqual(L.normalize_layer("tattva"), "reality_intelligence")
        self.assertEqual(L.normalize_layer("Tattva"), "reality_intelligence")   # case-insensitive
        self.assertEqual(L.normalize_layer("adhara"), "foundation")
        self.assertEqual(L.normalize_layer("Nivesha"), "investment_diligence")

    def test_normalize_layer_passthrough(self):
        self.assertEqual(L.normalize_layer("reality_intelligence"), "reality_intelligence")
        self.assertEqual(L.normalize_layer(""), "")                              # explicit gap
        self.assertEqual(L.normalize_layer("DataQuality"), "DataQuality")
        # a display label also normalizes back to the serialized value
        self.assertEqual(L.normalize_layer("Reality Intelligence Layer"), "reality_intelligence")

    def test_legacy_layer_still_validates_and_canonicalises(self):
        # Backward compatibility: an old Sanskrit layer value still constructs, canonicalised.
        d = AgentDescriptor(
            agent_id="tattva.macro_regime", layer="Tattva", discipline="macro_regime",
            agent_type="sensor", emits=("AgentFinding", "MacroRegimeFinding"),
            allowed_downstream_layers=("Tattva",))
        self.assertEqual(d.layer, "reality_intelligence")
        self.assertEqual(d.allowed_downstream_layers, ("reality_intelligence",))

        env = HandoffEnvelope(envelope_id="H", from_layer="Tattva", to_layer="Sphurana")
        self.assertEqual(env.from_layer, "reality_intelligence")
        self.assertEqual(env.to_layer, "opportunity_discovery")


class RegistryUsesEnglishTests(unittest.TestCase):
    def test_registry_layers_are_english(self):
        reg = build_default_registry()
        self.assertEqual(len(reg.list_by_layer("foundation")), 6)
        self.assertEqual(len(reg.list_by_layer("intelligence_governance")), 6)
        self.assertEqual(len(reg.list_by_layer("reality_intelligence")), 14)
        # a legacy query still resolves through normalization
        self.assertEqual(len(reg.list_by_layer("Tattva")), 14)


class ClassAliasTests(unittest.TestCase):
    def test_english_class_aliases_are_the_legacy_classes(self):
        self.assertIs(rm.RealityIntelligenceSignalFusion, rm.TattvaSignalFusionSynthesizer)
        self.assertIs(rm.IntelligenceGovernanceRouter, rm.BuddhiRouter)
        self.assertIs(rm.OpportunityDiscoveryResult, rm.SphuranaResult)


class CosmosIQPulseCliTests(unittest.TestCase):
    def test_cosmosiq_pulse_runs_offline(self):
        import cosmosiq_pulse
        with tempfile.TemporaryDirectory() as out:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cosmosiq_pulse.main(
                    ["--watchlist", "IREN,AAOI", "--themes", "physical-ai,robotics",
                     "--out", out])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(out, "pulse_summary.json")))
        self.assertTrue(hasattr(cosmosiq_pulse, "main"))
        self.assertTrue(hasattr(cosmosiq_pulse, "build_pulse_summary"))


if __name__ == "__main__":
    unittest.main()
