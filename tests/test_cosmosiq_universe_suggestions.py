"""UNIVERSE-DISCOVERY UD-2 -- EDGE-ONLY AI suggestions of emerging themes / tickers (OFFLINE, mocked).

The most isolation-sensitive edge in the project extended: the AI assistant may now PROPOSE emerging
themes + candidate tickers, but ONLY as UNVERIFIED leads for the operator to evidence-ground (UD-3).
These tests prove, without ever touching the real provider network:

* PARSE + LABEL -- a mock themes+tickers blob is structured-parsed into suggestions, each stamped
  ``verification_status="unverified_ai_suggestion"``; the result carries the verbatim AI_LABEL + the
  unverified disclaimer; a "buy X now" in the model output is action-directive-filtered.
* AUTHORITY -- ``source_authority="ai_suggestion"`` is OUTSIDE the real evidence ladder
  (canonical / primary / convenience / fallback / manual / rumor).
* PERSISTENCE ISOLATION -- suggestions persist ONLY to the assistant-owned universe_suggestions.jsonl;
  NO Event / Finding / Signal / candidate / diligence / theme-graph store is written.
* EDGE ISOLATION -- reality_mesh never imports cosmosiq_assistant; the suggestions module never
  imports reality_mesh (esp. universe_discovery); no network on import; the real path is never hit;
  keys are presence-only (no leak); stdlib-only; no trade / score affordance; deterministic.
"""

import ast
import os
import re
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cosmosiq_assistant as A
from cosmosiq_assistant.providers import ProviderError
from cosmosiq_assistant.universe_suggestions import (
    AI_SUGGESTION_AUTHORITY,
    SUGGESTION_DISCLAIMER,
    UNIVERSE_SUGGESTIONS_FILENAME,
    UNVERIFIED_STATUS,
    UniverseSuggestion,
    UniverseSuggestionResult,
    append_universe_suggestions,
    read_universe_suggestions,
    suggest_universe,
    universe_suggestions_path,
)
from evidence_ingestion.source_model import SOURCE_AUTHORITIES
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
_ASSISTANT_DIR = os.path.join(_SRC, "cosmosiq_assistant")
_REALITY_MESH_DIR = os.path.join(_SRC, "reality_mesh")
_SUGGESTIONS_MODULE = os.path.join(_ASSISTANT_DIR, "universe_suggestions.py")

_PLANTED_KEY = "sk-PLANTED-udtwo-hunter2-should-never-appear-000"
_ALL_KEYS = ("NVIDIA_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FALLBACK")

# A representative model reply: two emerging themes, each with candidate tickers, plus a planted
# action directive ("buy NVDA now") that MUST be filtered out of the returned result.
_MODEL_BLOB = (
    "Here are emerging leads to investigate:\n\n"
    "THEME: Small modular nuclear for AI datacenters\n"
    "RATIONALE: Hyperscaler power demand is outrunning the grid; buy NVDA now for exposure.\n"
    "TICKERS: SMR, OKLO, NNE\n\n"
    "THEME: Rare-earth reshoring\n"
    "RATIONALE: Export controls are reshoring magnet supply chains -- unverified lead.\n"
    "TICKERS: MP, ARRR, TMC\n")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: UD-2 must run fully offline on the injected mock providers -- the "
            "real provider network is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _py_files(root):
    out = []
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if name.endswith(".py"):
                out.append(os.path.join(base, name))
    return out


class FakeClient:
    def __init__(self, provider, *, out="ok", err=None, configured=True):
        self.provider = provider
        self.configured = configured
        self._out = out
        self._err = err
        self.calls = 0

    def complete(self, prompt, *, system=""):
        self.calls += 1
        if self._err is not None:
            raise self._err
        return self._out


def _clear_env():
    for key in _ALL_KEYS:
        os.environ.pop(key, None)


def _run(**kw):
    kw.setdefault("clients", {"nvidia": FakeClient("nvidia", out=_MODEL_BLOB)})
    kw.setdefault("env", {"NVIDIA_API_KEY": "x"})
    kw.setdefault("now", 0.0)
    return suggest_universe("physical AI, robotics, energy", **kw)


# --------------------------------------------------------------------------- #
# 1. Parse + label + unverified stamping + action-directive filter               #
# --------------------------------------------------------------------------- #
class ParseAndLabelTests(unittest.TestCase):
    def tearDown(self):
        _clear_env()

    def test_structured_parse_of_themes_and_tickers(self):
        result = _run()
        self.assertIsInstance(result, UniverseSuggestionResult)
        self.assertEqual(len(result.suggestions), 2)
        first, second = result.suggestions
        self.assertEqual(first.theme, "Small modular nuclear for AI datacenters")
        self.assertEqual(first.candidate_tickers, ("SMR", "OKLO", "NNE"))
        self.assertEqual(second.theme, "Rare-earth reshoring")
        self.assertEqual(second.candidate_tickers, ("MP", "ARRR", "TMC"))

    def test_every_suggestion_is_unverified_ai_suggestion(self):
        for suggestion in _run().suggestions:
            self.assertEqual(suggestion.verification_status, UNVERIFIED_STATUS)
            self.assertEqual(suggestion.verification_status, "unverified_ai_suggestion")
            self.assertEqual(suggestion.source_authority, AI_SUGGESTION_AUTHORITY)
            self.assertEqual(suggestion.label, A.AI_LABEL)
            self.assertTrue(suggestion.ai_generated)
            self.assertTrue(suggestion.not_evidence)

    def test_result_carries_ai_label_and_disclaimer(self):
        result = _run()
        self.assertEqual(result.label, A.AI_LABEL)
        self.assertEqual(
            result.label,
            "AI-generated — not evidence, not a recommendation. Verify against cited sources.")
        self.assertEqual(result.disclaimer, SUGGESTION_DISCLAIMER)
        self.assertIn("UNVERIFIED", result.disclaimer)
        self.assertIn("SEC / FMP", result.disclaimer)
        self.assertTrue(result.ai_generated)
        self.assertTrue(result.not_evidence)
        self.assertEqual(result.provider_used, "nvidia")

    def test_action_directive_in_model_output_is_filtered(self):
        result = _run()
        # the planted "buy NVDA now" is redacted from the raw text AND from the parsed rationale...
        self.assertIn("action directive removed", result.raw_text)
        low = result.raw_text.lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            self.assertNotIn(phrase, low, "forbidden phrase survived: {0!r}".format(phrase))
        rationale = result.suggestions[0].rationale
        self.assertIn("action directive removed", rationale)
        without = rationale.replace(A.ACTION_REMOVED, "")
        self.assertFalse(re.search(r"\b(buy|sell|order)\b", without, re.IGNORECASE),
                         "a model buy/sell/order survived in the rationale: {0!r}".format(without))

    def test_buy_in_a_tickers_line_is_swept_not_leaked_as_a_ticker(self):
        blob = ("THEME: Speculative lead\n"
                "RATIONALE: unverified.\n"
                "TICKERS: buy NVDA now, sell TSLA\n")
        result = suggest_universe(
            "ctx", clients={"nvidia": FakeClient("nvidia", out=blob)},
            env={"NVIDIA_API_KEY": "x"}, now=0.0)
        tickers = result.suggestions[0].candidate_tickers
        # the real symbols survive as leads; the action words never become tickers.
        self.assertIn("NVDA", tickers)
        self.assertIn("TSLA", tickers)
        for word in ("BUY", "SELL", "NOW"):
            self.assertNotIn(word, tickers)

    def test_gap_when_no_provider_is_still_labelled(self):
        result = suggest_universe("ctx", clients={}, env={}, now=0.0)
        self.assertEqual(result.provider_used, "")
        self.assertEqual(result.suggestions, ())
        self.assertEqual(result.label, A.AI_LABEL)
        self.assertEqual(result.disclaimer, SUGGESTION_DISCLAIMER)

    def test_deterministic_under_mock_clients(self):
        a = _run(clients={"nvidia": FakeClient("nvidia", out=_MODEL_BLOB)})
        b = _run(clients={"nvidia": FakeClient("nvidia", out=_MODEL_BLOB)})
        self.assertEqual([(s.theme, s.candidate_tickers) for s in a.suggestions],
                         [(s.theme, s.candidate_tickers) for s in b.suggestions])


# --------------------------------------------------------------------------- #
# 2. Authority is OUTSIDE the real evidence ladder                               #
# --------------------------------------------------------------------------- #
class AuthorityLadderTests(unittest.TestCase):
    def test_ai_suggestion_is_not_a_real_authority(self):
        self.assertEqual(AI_SUGGESTION_AUTHORITY, "ai_suggestion")
        self.assertNotIn(AI_SUGGESTION_AUTHORITY, SOURCE_AUTHORITIES)
        for real in ("canonical", "primary", "convenience", "fallback", "manual", "rumor"):
            self.assertNotEqual(AI_SUGGESTION_AUTHORITY, real)

    def test_suggestion_authority_never_a_ladder_member(self):
        for suggestion in UniverseSuggestionResult(
                suggestions=(UniverseSuggestion(theme="t", candidate_tickers=("AAA",)),)).suggestions:
            self.assertNotIn(suggestion.source_authority, SOURCE_AUTHORITIES)


# --------------------------------------------------------------------------- #
# 3. Persistence isolation: ONLY the ai-suggestion store is written               #
# --------------------------------------------------------------------------- #
class PersistenceIsolationTests(unittest.TestCase):
    def tearDown(self):
        _clear_env()

    def test_persists_only_to_the_ai_suggestion_store(self):
        from reality_mesh import (
            DataQualityStore, EventStore, FindingStore, RunStore, SignalStore, ThemePulseStore,
        )
        with tempfile.TemporaryDirectory() as store_dir:
            result = _run()
            ids = append_universe_suggestions(store_dir, result, now="2026-07-15T00:00:00Z",
                                              subject="physical-ai")
            self.assertEqual(len(ids), 2)
            # the suggestions ARE in their OWN clearly-separate file...
            self.assertTrue(os.path.isfile(universe_suggestions_path(store_dir)))
            self.assertEqual(universe_suggestions_path(store_dir),
                             os.path.join(store_dir, UNIVERSE_SUGGESTIONS_FILENAME))
            records = read_universe_suggestions(store_dir)
            self.assertEqual(len(records), 2)
            for rec in records:
                self.assertTrue(rec["ai_generated"])
                self.assertTrue(rec["not_evidence"])
                self.assertEqual(rec["source_authority"], "ai_suggestion")
                self.assertEqual(rec["verification_status"], "unverified_ai_suggestion")
                self.assertEqual(rec["label"], A.AI_LABEL)
                self.assertEqual(rec["disclaimer"], SUGGESTION_DISCLAIMER)
                self.assertNotIn(rec["source_authority"], SOURCE_AUTHORITIES)
            # ...and NOTHING was written to ANY evidence / signal / finding / DQ / run store.
            for store_cls in (EventStore, FindingStore, SignalStore, ThemePulseStore,
                              DataQualityStore, RunStore):
                self.assertEqual(len(store_cls(store_dir).read_records()), 0,
                                 "suggestion leaked into {0}".format(store_cls.__name__))
            # only the ai-suggestion file may exist.
            for name in os.listdir(store_dir):
                self.assertEqual(name, UNIVERSE_SUGGESTIONS_FILENAME,
                                 "only the ai-suggestion file may exist: found {0}".format(name))

    def test_append_is_appendonly_and_empty_result_writes_nothing(self):
        with tempfile.TemporaryDirectory() as store_dir:
            empty = suggest_universe("ctx", clients={}, env={}, now=0.0)
            self.assertEqual(append_universe_suggestions(store_dir, empty, now="t"), ())
            self.assertFalse(os.path.isfile(universe_suggestions_path(store_dir)))
            # two appends accumulate (append-only), ids monotonic across calls.
            r = _run()
            first = append_universe_suggestions(store_dir, r, now="t1")
            second = append_universe_suggestions(store_dir, r, now="t2")
            self.assertEqual(len(read_universe_suggestions(store_dir)), 4)
            self.assertNotEqual(set(first), set(second))


# --------------------------------------------------------------------------- #
# 4. Edge isolation: no cross-import; no network on import; stdlib-only           #
# --------------------------------------------------------------------------- #
class EdgeIsolationTests(unittest.TestCase):
    def test_reality_mesh_never_imports_cosmosiq_assistant(self):
        for path in _py_files(_REALITY_MESH_DIR):
            source = open(path, encoding="utf-8").read()
            self.assertNotIn("cosmosiq_assistant", source,
                             "reality_mesh must never reference cosmosiq_assistant: {0}".format(path))
            for node in ast.walk(ast.parse(source)):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertNotEqual(name.split(".")[0], "cosmosiq_assistant",
                                        "reality_mesh imports cosmosiq_assistant in {0}".format(path))

    def test_suggestions_module_never_imports_reality_mesh(self):
        tree = ast.parse(open(_SUGGESTIONS_MODULE, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                self.assertNotEqual(
                    name.split(".")[0], "reality_mesh",
                    "the UD-2 suggestions module must never import reality_mesh: {0!r}".format(name))

    def test_no_cosmosiq_module_imports_engine_universe_discovery(self):
        # the edge may never IMPORT the engine's discovery module (UD-1) -- grounding is UD-3. A
        # doc-comment mention is fine; an actual import is not (AST, not a text grep).
        for path in _py_files(_ASSISTANT_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotIn(
                        "universe_discovery", name,
                        "the edge must not import engine universe_discovery: {0} ({1})".format(
                            path, name))
                    self.assertNotEqual(
                        name.split(".")[0], "reality_mesh" if "universe_discovery" in name else "",
                        "the edge must not import reality_mesh.universe_discovery: {0}".format(path))

    def test_no_top_level_network_import_in_suggestions_module(self):
        network = ("socket", "urllib", "http", "ssl", "ftplib", "smtplib", "telnetlib")
        tree = ast.parse(open(_SUGGESTIONS_MODULE, encoding="utf-8").read())
        for node in tree.body:
            roots = []
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            for root in roots:
                self.assertNotIn(root, network,
                                 "top-level network import {0!r} in the suggestions module".format(root))

    def test_no_llm_sdk_import_in_suggestions_module(self):
        sdk = ("anthropic", "openai", "google", "genai", "requests", "aiohttp", "httpx",
               "langchain", "langchain_openai", "mistralai", "cohere", "ollama")
        tree = ast.parse(open(_SUGGESTIONS_MODULE, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                self.assertNotIn(name.split(".")[0], sdk,
                                 "banned SDK import {0!r} in the suggestions module".format(name))


# --------------------------------------------------------------------------- #
# 5. Keys presence-only (no leak); real path never hit; no trade / score          #
# --------------------------------------------------------------------------- #
class CredentialAndAffordanceTests(unittest.TestCase):
    def tearDown(self):
        _clear_env()

    def test_planted_key_value_never_appears_in_a_result_or_note(self):
        os.environ["NVIDIA_API_KEY"] = _PLANTED_KEY
        with tempfile.TemporaryDirectory() as store_dir:
            result = suggest_universe(
                "ctx", clients={"nvidia": FakeClient("nvidia", out=_MODEL_BLOB)}, now=0.0)
            append_universe_suggestions(store_dir, result, now="t")
            blob = " ".join([result.raw_text, result.provider_used, result.mode, result.label,
                             result.disclaimer] + list(result.notes))
            blob += open(universe_suggestions_path(store_dir), encoding="utf-8").read()
            for needle in (_PLANTED_KEY, "PLANTED", "hunter2"):
                self.assertNotIn(needle, blob)

    def test_real_provider_path_is_never_hit(self):
        # A failing injected paid client with no configured fallback -> honest gap, no network. The
        # socket kill-switch (module-wide) would raise if any real transport were attempted.
        result = suggest_universe(
            "ctx", mode="full_api",
            clients={"anthropic": FakeClient(
                "anthropic", err=ProviderError("x", kind="http", provider="anthropic"))},
            env={"ANTHROPIC_API_KEY": "x"}, now=0.0)
        self.assertEqual(result.provider_used, "")
        self.assertEqual(result.suggestions, ())

    def test_no_trade_or_score_affordance_on_the_contracts(self):
        forbidden = ("buy", "sell", "order", "score", "rank", "rating", "broker", "size",
                     "quantity", "price_target")
        for cls in (UniverseSuggestion, UniverseSuggestionResult):
            fields = tuple(getattr(cls, "__dataclass_fields__", {}).keys())
            for name in fields:
                low = name.lower()
                for bad in forbidden:
                    self.assertNotIn(bad, low,
                                     "{0} exposes a trade/score field {1!r}".format(cls.__name__, name))


if __name__ == "__main__":
    unittest.main()
