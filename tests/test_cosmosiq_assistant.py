"""PROD-LIVE-3 -- the ISOLATED AI Research Assistant (OFFLINE, mocked providers).

The most isolation-sensitive slice in the project. These tests prove, without ever touching the
real provider network:

* ISOLATION -- ``reality_mesh`` NEVER imports ``cosmosiq_assistant`` (AST + text scan over the whole
  engine package); the assistant output is NEVER written to any evidence / signal / finding /
  candidate / recommendation / data-quality store (only its OWN clearly-labelled assistant-notes).
* THE PROVIDER CHAIN -- free = NVIDIA -> Gemini failover; paid = Claude -> fallback key; a paid
  billing / 5xx / auth failure TRIPS a process-global circuit breaker that routes to the FREE chain
  for the window then PROBES for recovery (injected clock); an unconfigured provider is SKIPPED with
  an honest note.
* NO NETWORK ON IMPORT / NO SDK -- no top-level ``urllib`` / ``http`` / ``socket`` import in any
  ``cosmosiq_assistant`` module and no ``anthropic`` / ``openai`` / ``google`` / ``requests`` SDK
  import ANYWHERE (so ``dependencies_reviewed`` stays green); the real provider path is NEVER
  exercised (fakes injected; a module-wide socket kill-switch).
* THE MANDATORY LABEL + THE ACTION-DIRECTIVE POST-FILTER -- every result carries the verbatim
  AI-generated label; a mock provider that returns "Strong buy now, submit order" comes back with
  the "[action directive removed ...]" marker and NONE of the 020D forbidden phrases.
* KEYS PRESENCE-ONLY -- a planted key VALUE never appears in any result; a no-key run is an honest
  gap, not a crash / leak.
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
from cosmosiq_assistant.providers import (
    ProviderError,
    build_provider_chain,
)
from cosmosiq_assistant.router import (
    CircuitBreaker,
    GLOBAL_BREAKER,
    run_assistant,
)
from cosmosiq_assistant.tasks import draft_thesis_note, summarize_filing
from cosmosiq_assistant.notes_store import (
    ASSISTANT_NOTES_FILENAME,
    append_assistant_note,
    assistant_notes_path,
    read_assistant_notes,
)
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
_ASSISTANT_DIR = os.path.join(_SRC, "cosmosiq_assistant")
_REALITY_MESH_DIR = os.path.join(_SRC, "reality_mesh")

# A planted credential VALUE used ONLY to prove it never leaks into a result / render / note.
_PLANTED_KEY = "sk-PLANTED-hunter2-VALUE-should-never-appear-000"

_ALL_KEYS = ("NVIDIA_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FALLBACK")

# The socket kill-switch stays armed for the WHOLE module: the assistant must run fully offline on
# the injected fakes -- the real provider network is NEVER exercised.
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the AI Research Assistant must run fully offline on the injected "
            "mock providers -- the real provider network is never exercised in tests")

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
    """An injected offline provider: a uniform ``complete(prompt, *, system)`` fake.

    ``out`` is returned on success; ``err`` (a :class:`ProviderError`) is raised instead;
    ``configured`` toggles whether the chain builder keeps or skips it.
    """

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


def _billing(provider):
    return ProviderError("402 billing / credit ceiling", kind="billing", provider=provider)


def _clear_env():
    for key in _ALL_KEYS:
        os.environ.pop(key, None)


# --------------------------------------------------------------------------- #
# 1. Isolation: reality_mesh never imports cosmosiq_assistant                    #
# --------------------------------------------------------------------------- #
class EngineIsolationTests(unittest.TestCase):
    def test_reality_mesh_never_references_cosmosiq_assistant(self):
        for path in _py_files(_REALITY_MESH_DIR):
            source = open(path, encoding="utf-8").read()
            self.assertNotIn(
                "cosmosiq_assistant", source,
                "reality_mesh must NEVER reference cosmosiq_assistant: {0}".format(path))
            for node in ast.walk(ast.parse(source)):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertFalse(
                        name.split(".")[0] == "cosmosiq_assistant",
                        "reality_mesh imports cosmosiq_assistant in {0}".format(path))

    def test_assistant_output_never_written_to_any_evidence_store(self):
        from reality_mesh import (
            DataQualityStore, EventStore, FindingStore, RunStore, SignalStore, ThemePulseStore,
        )
        with tempfile.TemporaryDirectory() as store_dir:
            result = summarize_filing(
                "IREN 8-K: material agreement filed.", ticker="IREN",
                clients={"nvidia": FakeClient("nvidia", out="A neutral summary.")},
                env={"NVIDIA_API_KEY": "x"}, now=1000.0)
            note_id = append_assistant_note(store_dir, result, now="2026-07-05T00:00:00Z",
                                            subject="IREN")
            # the assistant note IS written to its OWN clearly-separate file...
            self.assertTrue(os.path.isfile(assistant_notes_path(store_dir)))
            self.assertEqual(assistant_notes_path(store_dir),
                             os.path.join(store_dir, ASSISTANT_NOTES_FILENAME))
            notes = read_assistant_notes(store_dir)
            self.assertEqual(len(notes), 1)
            self.assertTrue(notes[0]["ai_generated"])
            self.assertTrue(notes[0]["not_evidence"])
            self.assertEqual(notes[0]["note_id"], note_id)
            # ...and NOTHING was written to ANY evidence / signal / finding / DQ / run store.
            for store_cls in (EventStore, FindingStore, SignalStore, ThemePulseStore,
                              DataQualityStore, RunStore):
                self.assertEqual(
                    len(store_cls(store_dir).read_records()), 0,
                    "assistant output leaked into {0}".format(store_cls.__name__))
            # no candidate / recommendation store file exists either.
            for name in os.listdir(store_dir):
                self.assertEqual(name, ASSISTANT_NOTES_FILENAME,
                                 "only the assistant-notes file may exist: found {0}".format(name))


# --------------------------------------------------------------------------- #
# 2. The provider chain: precedence, failover, circuit breaker, honest skip      #
# --------------------------------------------------------------------------- #
class ProviderChainTests(unittest.TestCase):
    def tearDown(self):
        GLOBAL_BREAKER.reset()
        _clear_env()

    def test_free_chain_nvidia_to_gemini_failover(self):
        clients = {"nvidia": FakeClient("nvidia", err=ProviderError("boom", kind="http")),
                   "gemini": FakeClient("gemini", out="gemini did it")}
        r = run_assistant("summarize_filing", "p", mode="free",
                          env={"NVIDIA_API_KEY": "x", "GOOGLE_API_KEY": "y"},
                          clients=clients, now=100.0, breaker=CircuitBreaker())
        self.assertEqual(r.provider_used, "gemini")
        self.assertEqual(r.text, "gemini did it")
        self.assertEqual(clients["nvidia"].calls, 1)
        self.assertEqual(clients["gemini"].calls, 1)

    def test_free_chain_default_is_nvidia_first(self):
        clients = {"nvidia": FakeClient("nvidia", out="nvidia workhorse"),
                   "gemini": FakeClient("gemini", out="gemini")}
        r = run_assistant("t", "p", env={"NVIDIA_API_KEY": "x", "GOOGLE_API_KEY": "y"},
                          clients=clients, now=1.0, breaker=CircuitBreaker())
        self.assertEqual(r.provider_used, "nvidia")
        self.assertEqual(clients["gemini"].calls, 0)

    def test_paid_chain_claude_to_fallback_on_credit_ceiling(self):
        clients = {"anthropic": FakeClient("anthropic", err=_billing("anthropic")),
                   "anthropic_fallback": FakeClient("anthropic_fallback", out="claude fallback")}
        r = run_assistant("t", "p", mode="full_api",
                          env={"ANTHROPIC_API_KEY": "x", "ANTHROPIC_API_KEY_FALLBACK": "y"},
                          clients=clients, now=0.0, breaker=CircuitBreaker())
        self.assertEqual(r.provider_used, "anthropic_fallback")
        self.assertEqual(r.mode, "paid")
        self.assertEqual(r.circuit_state, "closed")   # fallback recovered -> breaker stays closed

    def test_circuit_breaker_trips_on_billing_and_routes_to_free_then_probes(self):
        breaker = CircuitBreaker(window_seconds=600)
        env = {"ANTHROPIC_API_KEY": "x", "ANTHROPIC_API_KEY_FALLBACK": "y",
               "NVIDIA_API_KEY": "n", "GOOGLE_API_KEY": "g"}
        clients = {
            "anthropic": FakeClient("anthropic", err=_billing("anthropic")),
            "anthropic_fallback": FakeClient("anthropic_fallback",
                                             err=_billing("anthropic_fallback")),
            "nvidia": FakeClient("nvidia", out="free workhorse"),
            "gemini": FakeClient("gemini", out="gemini"),
        }
        # both Claude keys fail billing -> breaker trips -> rerouted to the FREE chain (nvidia).
        r = run_assistant("t", "p", mode="full_api", env=env, clients=clients, now=1000.0,
                          breaker=breaker)
        self.assertEqual(r.provider_used, "nvidia")
        self.assertEqual(r.circuit_state, "open")
        self.assertEqual(breaker.trip_count, 1)

        # WITHIN the window: a paid request routes STRAIGHT to the free chain (no paid attempt).
        clients["anthropic"].calls = 0
        r2 = run_assistant("t", "p", mode="full_api", env=env, clients=clients, now=1300.0,
                           breaker=breaker)
        self.assertEqual(r2.provider_used, "nvidia")
        self.assertEqual(r2.circuit_state, "open")
        self.assertEqual(clients["anthropic"].calls, 0)   # paid chain suppressed while open

        # AFTER the window: half-open -> PROBE the paid chain; a recovered Claude closes it.
        clients["anthropic"] = FakeClient("anthropic", out="claude back")
        r3 = run_assistant("t", "p", mode="full_api", env=env, clients=clients, now=1000.0 + 601,
                           breaker=breaker)
        self.assertEqual(r3.provider_used, "anthropic")
        self.assertEqual(r3.circuit_state, "closed")

    def test_circuit_breaker_trips_on_5xx_and_auth(self):
        for kind in ("5xx", "auth"):
            breaker = CircuitBreaker()
            clients = {
                "anthropic": FakeClient("anthropic",
                                        err=ProviderError("x", kind=kind, provider="anthropic")),
                "anthropic_fallback": FakeClient(
                    "anthropic_fallback",
                    err=ProviderError("x", kind=kind, provider="anthropic_fallback")),
                "nvidia": FakeClient("nvidia", out="free"),
            }
            r = run_assistant("t", "p", mode="full_api",
                              env={"ANTHROPIC_API_KEY": "x", "ANTHROPIC_API_KEY_FALLBACK": "y",
                                   "NVIDIA_API_KEY": "n"},
                              clients=clients, now=0.0, breaker=breaker)
            self.assertEqual(breaker.trip_count, 1, "breaker must trip on {0}".format(kind))
            self.assertEqual(r.provider_used, "nvidia")

    def test_unconfigured_provider_is_skipped_with_honest_note(self):
        # NVIDIA key absent -> nvidia skipped; Gemini configured -> used, with an honest note.
        clients = {"gemini": FakeClient("gemini", out="gemini")}
        chain = build_provider_chain(mode="free", env={"GOOGLE_API_KEY": "y"}, clients=clients)
        self.assertEqual(chain.provider_order, ("gemini",))
        self.assertTrue(any("NVIDIA_API_KEY absent" in n for n in chain.notes))
        r = run_assistant("t", "p", mode="free", env={"GOOGLE_API_KEY": "y"},
                          clients=clients, now=0.0, breaker=CircuitBreaker())
        self.assertEqual(r.provider_used, "gemini")
        self.assertTrue(any("nvidia unconfigured" in n for n in r.notes))

    def test_no_provider_configured_is_an_honest_gap_not_a_crash(self):
        r = run_assistant("t", "p", mode="free", env={}, clients={}, now=0.0,
                          breaker=CircuitBreaker())
        self.assertEqual(r.provider_used, "")
        self.assertIn("no LLM provider is configured", " ".join(r.notes))
        self.assertEqual(r.label, A.AI_LABEL)          # still labelled, even on a gap


# --------------------------------------------------------------------------- #
# 3. No network on import; no SDK anywhere; real path never exercised            #
# --------------------------------------------------------------------------- #
class NoAmbientNetworkTests(unittest.TestCase):
    _NETWORK_ROOTS = ("socket", "urllib", "http", "ssl", "ftplib", "smtplib", "telnetlib")
    _SDK_ROOTS = ("anthropic", "openai", "google", "genai", "requests", "aiohttp", "httpx",
                  "langchain", "langchain_openai", "mistralai", "cohere", "ollama")

    def test_no_top_level_network_import_in_any_module(self):
        for path in _py_files(_ASSISTANT_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in tree.body:                     # MODULE TOP LEVEL only
                roots = []
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots = [node.module.split(".")[0]]
                for root in roots:
                    self.assertNotIn(
                        root, self._NETWORK_ROOTS,
                        "top-level network import {0!r} in {1}".format(root, path))

    def test_no_llm_sdk_import_anywhere(self):
        for path in _py_files(_ASSISTANT_DIR):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    root = name.split(".")[0]
                    self.assertNotIn(
                        root, self._SDK_ROOTS,
                        "banned LLM/HTTP SDK import {0!r} in {1} (stdlib-only; "
                        "dependencies_reviewed must stay green)".format(name, path))


# --------------------------------------------------------------------------- #
# 4. The mandatory label + the action-directive POST-FILTER                      #
# --------------------------------------------------------------------------- #
class LabelAndFilterTests(unittest.TestCase):
    def tearDown(self):
        _clear_env()

    def test_every_result_carries_the_verbatim_ai_label(self):
        self.assertEqual(
            A.AI_LABEL,
            "AI-generated — not evidence, not a recommendation. Verify against cited sources.")
        r = summarize_filing("some filing", ticker="IREN",
                             clients={"nvidia": FakeClient("nvidia", out="ok")},
                             env={"NVIDIA_API_KEY": "x"}, now=0.0)
        self.assertEqual(r.label, A.AI_LABEL)
        self.assertTrue(r.ai_generated)

    def test_action_directive_output_is_post_filtered(self):
        malicious = "Strong buy now, submit order -- guaranteed upside. Revenue grew 40%."
        r = draft_thesis_note("IREN", "context",
                             clients={"anthropic": FakeClient("anthropic", out=malicious)},
                             mode="full_api",
                             env={"ANTHROPIC_API_KEY": "x"}, now=0.0, )
        # the removal marker is present...
        self.assertIn("action directive removed", r.text)
        # ...and NONE of the 020D forbidden phrases survive...
        low = r.text.lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            self.assertNotIn(phrase, low,
                             "forbidden phrase {0!r} survived the post-filter".format(phrase))
        # ...and the benign content is untouched.
        self.assertIn("Revenue grew 40%", r.text)

    def test_bare_buy_sell_order_words_from_the_model_are_swept(self):
        # every buy/sell/order the MODEL wrote is replaced; the only such words remaining are the
        # inert redaction marker's own prose. Strip the markers -> nothing from the model survives.
        model_out = "You should buy and never sell; place a large order."
        r = summarize_filing(model_out,
                             clients={"nvidia": FakeClient("nvidia", out=model_out)},
                             env={"NVIDIA_API_KEY": "x"}, now=0.0)
        self.assertIn("action directive removed", r.text)
        without_markers = r.text.replace(A.ACTION_REMOVED, "")
        self.assertFalse(
            re.search(r"\b(buy|sell|order)\b", without_markers, re.IGNORECASE),
            "a model buy/sell/order instruction survived: {0!r}".format(without_markers))

    def test_marker_is_the_mandated_verbatim_string(self):
        self.assertEqual(
            A.ACTION_REMOVED,
            "[action directive removed — CosmosIQ issues no buy/sell instructions]")
        # a single pass over the malicious phrase yields exactly the marker in place.
        self.assertEqual(A.filter_action_directives("submit order"), A.ACTION_REMOVED)
        # benign text is untouched (the filter only ever redacts action directives).
        self.assertEqual(A.filter_action_directives("Revenue grew and margins expanded."),
                         "Revenue grew and margins expanded.")


# --------------------------------------------------------------------------- #
# 5. Keys presence-only: a planted VALUE never leaks; no-key is an honest gap     #
# --------------------------------------------------------------------------- #
class CredentialPresenceTests(unittest.TestCase):
    def tearDown(self):
        _clear_env()

    def test_planted_key_value_never_appears_in_a_result(self):
        os.environ["NVIDIA_API_KEY"] = _PLANTED_KEY
        r = summarize_filing("filing text", ticker="IREN",
                             clients={"nvidia": FakeClient("nvidia", out="clean summary")},
                             now=0.0)
        blob = " ".join([r.text, r.provider_used, r.mode, r.label, r.task] + list(r.notes))
        self.assertNotIn(_PLANTED_KEY, blob)
        self.assertNotIn("PLANTED", blob)
        self.assertNotIn("hunter2", blob)

    def test_no_key_is_honest_not_configured_not_a_crash(self):
        _clear_env()
        self.assertFalse(A.assistant_configured(env={}))
        r = summarize_filing("filing text", now=0.0)   # real clients, no key, no network
        self.assertEqual(r.provider_used, "")
        self.assertIn("no llm provider is configured",
                      " ".join(r.notes).lower() + r.text.lower())

    def test_presence_only_never_reads_the_value_in_chain_build(self):
        # build the chain from presence only; the value is never touched here.
        chain = build_provider_chain(mode="free", env={"NVIDIA_API_KEY": _PLANTED_KEY})
        self.assertEqual(chain.provider_order[0], "nvidia")   # configured from PRESENCE


# --------------------------------------------------------------------------- #
# 6. The engine stays untouched -- run_pulse is byte-identical run to run          #
# --------------------------------------------------------------------------- #
class EngineUntouchedTests(unittest.TestCase):
    def test_default_pulse_is_deterministic_after_importing_the_assistant(self):
        import cosmosiq_assistant  # noqa: F401  (importing the assistant must not perturb the engine)
        from reality_mesh.pulse import run_pulse
        now = "2026-07-05T00:00:00Z"
        a = run_pulse("IREN,AAOI", "physical-ai,robotics", now=now)
        b = run_pulse("IREN,AAOI", "physical-ai,robotics", now=now)
        self.assertEqual([f.finding_id for f in a.findings],
                         [f.finding_id for f in b.findings])
        self.assertEqual([s.signal_id for s in a.signals],
                         [s.signal_id for s in b.signals])


if __name__ == "__main__":
    unittest.main()
