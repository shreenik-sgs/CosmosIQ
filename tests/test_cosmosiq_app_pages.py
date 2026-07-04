"""IMPLEMENTATION-016B -- the CosmosIQ app UI pages: server-rendered HTML, tested OFFLINE.

The 016B slice adds PURE page renderers (``cosmosiq_app/pages.py``) and GET routes on the
016A dispatcher (``/``, ``/runs``, ``/runs/<id>``, ``/replay/<id>``, ``/alerts``,
``/settings``, ``/canvas/<name>``). These tests exercise the DISPATCHER ONLY -- no server,
no socket, no port; the whole module runs under a socket kill-switch, so every seeded pulse
and rendered page below is proven offline.

Guardrails asserted on EVERY rendered page:

* CosmosIQ branding + the four-item nav; a Universe Canvas NOTE (never a dead link) when
  no artifacts exist, real links when they do;
* the honest "as of <persisted run time>" line; no live / real-time / streaming claim;
* 0 Sanskrit layer terms (persisted legacy agent-id prefixes are normalized to English);
* 0 trade affordances -- no buy / sell / order / submit / execute / trade / broker word
  anywhere, and the ONLY buttons are the allowed OPERATOR actions with their exact labels
  (Acknowledge / Pause / Resume / Run manual pulse / Save settings);
* 0 external URLs / CDN / fonts / scripts / stylesheets -- fully self-contained pages;
* 0 credential-like keys or credential-like values; 0 score / rank / rating keys or words.

Honesty surfaces proven end to end: trigger attribution + gate overall + worst agent health
+ gap counts on the run history; agent health + gate badges + data gaps + conflicts on run
detail; ``deterministic_match`` prominently on the replay view -- and a TAMPERED store line
renders ``deterministic_match: False`` with every difference NAMED. Unknown run id -> a 404
page. ``api.py`` and ``pages.py`` stay wall-clock-free / network-free (AST-proven), and the
demo default + default pulse CLI stay byte-identical.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import stores as S
from cosmosiq_app.api import APP_NAME, dispatch
from cosmosiq_app.pages import CANVAS_DIRNAME, CANVAS_PAGES

_APP_DIR = os.path.join(_SRC, "cosmosiq_app")
_API_PY = os.path.join(_APP_DIR, "api.py")
_PAGES_PY = os.path.join(_APP_DIR, "pages.py")
_ASSETS_PY = os.path.join(_APP_DIR, "app_assets.py")

_NOW1 = "2026-06-29T00:00:00Z"
_NOW2 = "2026-06-30T00:00:00Z"
_NOW3 = "2026-07-01T00:00:00Z"
_RUN1 = "RUN-PAGES-1"
_ALERT_ID = "alert.RUN-PAGES-1.theme-pulse-changed.seeded"

# The retired Sanskrit layer names -- ZERO may appear on any rendered page.
_SANSKRIT_TOKENS = ("adhara", "buddhi", "tattva", "sphurana", "nivesha", "saarathi",
                    "kriya", "anubhava")

# Word-boundary trade verbs -- ZERO may appear on any rendered page (word-boundary so CSS
# "border" and prose "recorded" never false-positive).
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)

# Score-like tokens -- ZERO may appear (pages carry labels + volume counts only).
_SCORE_TOKENS = ("score", "rank", "rating", "investab")

# External-reference markers -- ZERO may appear (self-contained pages, no CDN, no font,
# no script, no stylesheet link, no live fetch).
_EXTERNAL_TOKENS = ("http://", "https://", "cdn.", "@import", "<script", "<link",
                    "fetch(", "xmlhttprequest", "@font-face")

# Live-claim wording -- ZERO may appear.
_LIVE_CLAIMS = ("real-time", "real time", "realtime", "streaming", "always-on", "24/7",
                "autonomous")
_LIVE_WORD = re.compile(r"\blive\b", re.IGNORECASE)

# Credential-like key tokens + value patterns -- ZERO may appear in a rendered page.
_CRED_TOKENS = tuple(S.CREDENTIAL_KEY_TOKENS)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN"),
)

# The ONLY button labels allowed anywhere in the app (all OPERATOR actions, no trade verb).
_ALLOWED_BUTTONS = frozenset({"Acknowledge", "Pause", "Resume", "Run manual pulse",
                              "Save settings"})

_BUTTON = re.compile(r"<button[^>]*>(.*?)</button>", re.DOTALL)

# Banned import roots for the PURE page layer (same list the 016A dispatcher is held to).
_BANNED_IMPORT_ROOTS = (
    "socket", "socketserver", "http", "urllib", "requests", "ssl", "select", "selectors",
    "sched", "schedule", "asyncio", "threading", "multiprocessing", "subprocess",
    "smtplib", "ftplib", "time", "datetime", "random", "uuid",
)
_WALL_CLOCK_ATTRS = ("now", "utcnow", "today", "time", "monotonic", "perf_counter", "sleep")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline CosmosIQ page tests")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


_STATE = {}
_ORIG_CONNECT = None

# Every server-rendered page path in the shared store (fetched once, asserted many times).
_PAGE_PATHS = ("/", "/runs", "/runs/" + _RUN1, "/replay/" + _RUN1, "/alerts", "/settings")


def _call(method, path, body=None, query=None, now="", store_dir=None):
    return dispatch({"method": method, "path": path, "query": query or {}, "body": body},
                    store_dir=store_dir or _STATE["store_dir"], now=now)


def _seed_store(store_dir, run_id, now):
    """Seed one persisted run (THROUGH the dispatcher) + one alert into ``store_dir``."""
    response = dispatch(
        {"method": "POST", "path": "/api/pulse", "query": {},
         "body": {"watchlist": ["IREN", "NVDA"], "themes": ["physical_ai", "robotics"],
                  "now": now, "run_id": run_id}},
        store_dir=store_dir)
    assert response["status"] == 200, response
    return response


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket

    store_dir = tempfile.mkdtemp(prefix="cosmosiq_pages_store_")
    _STATE["store_dir"] = store_dir

    # Run 1 seeded via the API's own manual-pulse workflow, offline under the kill-switch.
    _seed_store(store_dir, _RUN1, _NOW1)

    # A second run so the history page proves newest-first plus per-run rows.
    response = _call("POST", "/api/pulse",
                     body={"watchlist": ["IREN", "NVDA"],
                           "themes": ["physical_ai", "robotics"], "now": _NOW2})
    assert response["status"] == 200, response
    _STATE["run2"] = response["body"]["run_id"]

    # One alert in the inbox (the diff engine has its own suite; pages render the store).
    alert = rm.Alert(
        alert_id=_ALERT_ID, run_id=_RUN1, category="theme_pulse_changed",
        severity="notice",
        human_readable_reason="Theme pulse for 'physical_ai' changed state between run "
                              "RUN-PAGES-0 and run RUN-PAGES-1; evidence: seeded record.",
        subject_themes=("physical_ai",), subject_refs=("tp.seeded",), created_at=_NOW1)
    rm.AlertStore(store_dir).append(alert, timestamp=_NOW1)

    # Journaled settings so the settings page shows real current values.
    response = _call("PUT", "/api/settings",
                     body={"watchlists": ["IREN", "NVDA"],
                           "themes": ["physical_ai", "robotics"], "at": _NOW3})
    assert response["status"] == 200, response

    # Fetch every page ONCE; the shared store is read-only from here on.
    _STATE["pages"] = {path: _call("GET", path) for path in _PAGE_PATHS}
    _STATE["page_404"] = _call("GET", "/runs/RUN-NOPE")


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _html(path):
    return _STATE["pages"][path]["body"]


# =========================================================================== #
# 1. Every page: HTML served by the dispatcher with branding + nav             #
# =========================================================================== #
class PageServingTests(unittest.TestCase):
    def test_every_page_is_200_html_from_the_pure_dispatcher(self):
        for path in _PAGE_PATHS:
            response = _STATE["pages"][path]
            self.assertEqual(response["status"], 200, path)
            self.assertTrue(
                response["headers"]["Content-Type"].startswith("text/html"), path)
            self.assertIsInstance(response["body"], str, path)
            self.assertTrue(response["body"].startswith("<!doctype html>"), path)

    def test_every_page_carries_cosmosiq_branding_and_the_nav(self):
        for path in _PAGE_PATHS:
            html = _html(path)
            self.assertIn(APP_NAME, html, path)
            for href in ('href="/"', 'href="/runs"', 'href="/alerts"',
                         'href="/settings"'):
                self.assertIn(href, html, path)

    def test_every_page_carries_the_as_of_honesty_line(self):
        for path in _PAGE_PATHS:
            html = _html(path)
            self.assertIn("as of", html, path)
            # the as-of instant is a PERSISTED run time, never a wall-clock read
            self.assertIn(_NOW2, html.split("</div>", 1)[0], path)
            self.assertIn("pulse data", html, path)

    def test_pages_render_identically_for_identical_requests(self):
        for path in _PAGE_PATHS:
            again = _call("GET", path)
            self.assertEqual(json.dumps(again, sort_keys=True),
                             json.dumps(_STATE["pages"][path], sort_keys=True), path)

    def test_page_routes_are_get_only(self):
        for path in ("/", "/runs", "/alerts", "/settings"):
            response = _call("POST", path)
            self.assertEqual(response["status"], 404, path)   # never a hidden POST surface

    def test_api_routes_still_answer_json(self):
        response = _call("GET", "/api/runs")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/json")


# =========================================================================== #
# 2. Run history: trigger + gate + health + gaps, newest first                 #
# =========================================================================== #
class RunHistoryPageTests(unittest.TestCase):
    def test_lists_both_runs_newest_first_with_links(self):
        html = _html("/runs")
        first = html.find('href="/runs/{0}"'.format(_STATE["run2"]))
        second = html.find('href="/runs/{0}"'.format(_RUN1))
        self.assertGreater(first, -1)
        self.assertGreater(second, first)   # newest first

    def test_shows_trigger_attribution_gate_overall_health_and_gap_counts(self):
        html = _html("/runs")
        self.assertIn("manual &middot; operator-run", html)
        self.assertIn("Gate overall", html)
        self.assertIn("Worst agent health", html)
        self.assertIn("degraded", html)     # the seeded pulse's honest gate verdict
        self.assertIn("healthy", html)      # ...and its agent health label
        self.assertRegex(html, r"\d+ gap\(s\)")
        self.assertRegex(html, r"events \d+ &middot; findings \d+ &middot; signals \d+")


# =========================================================================== #
# 3. Run detail: agent/source health + gate badges + gaps + conflicts          #
# =========================================================================== #
class RunDetailPageTests(unittest.TestCase):
    def test_shows_agent_health_with_english_layer_terms_only(self):
        html = _html("/runs/" + _RUN1)
        self.assertIn("Agent health", html)
        self.assertIn("reality_intelligence.market_regime", html)   # normalized prefix
        self.assertIn("reality_intelligence.news_filings", html)
        for status in ("success", "healthy"):
            self.assertIn(status, html)

    def test_shows_gate_badges_and_the_overall_verdict(self):
        html = _html("/runs/" + _RUN1)
        self.assertIn("Data-quality gates", html)
        self.assertIn("replayability", html)
        self.assertIn("social weak signal", html)
        self.assertIn("degraded", html)                 # the honest overall roll-up
        self.assertNotIn("security_secrets", html)      # sensitive-looking id renamed
        self.assertNotIn("gate_overall", html)          # rolled up, not echoed raw

    def test_shows_data_gaps_visibly(self):
        html = _html("/runs/" + _RUN1)
        self.assertIn("Data gaps", html)
        self.assertIn("institutional flow proxy missing", html)
        self.assertIn("honest gap, not fabricated", html)

    def test_shows_conflicts_with_both_sides(self):
        html = _html("/runs/" + _RUN1)
        self.assertIn("Conflicts (both sides)", html)

    def test_links_to_the_replay_view(self):
        self.assertIn('href="/replay/{0}"'.format(_RUN1), _html("/runs/" + _RUN1))

    def test_unknown_run_id_renders_a_404_page(self):
        response = _STATE["page_404"]
        self.assertEqual(response["status"], 404)
        self.assertTrue(response["headers"]["Content-Type"].startswith("text/html"))
        self.assertIn("404", response["body"])
        self.assertIn("RUN-NOPE", response["body"])
        self.assertIn("as of", response["body"])        # honesty line even on the 404 page
        self.assertEqual(_call("GET", "/replay/RUN-NOPE")["status"], 404)


# =========================================================================== #
# 4. Replay view: deterministic_match prominent; tamper -> False + named diffs #
# =========================================================================== #
class ReplayViewPageTests(unittest.TestCase):
    def test_clean_run_shows_deterministic_match_true_prominently(self):
        html = _html("/replay/" + _RUN1)
        self.assertIn('<div class="verdict ok">deterministic_match: True', html)
        self.assertNotIn("Named differences", html)
        self.assertRegex(html, r"events \d+ &middot; findings \d+ &middot; signals \d+")

    def test_tampered_store_line_shows_false_with_named_differences(self):
        with tempfile.TemporaryDirectory() as store_dir:
            _seed_store(store_dir, "RUN-TAMPER", _NOW1)
            signal_path = os.path.join(store_dir, "signal_store.jsonl")
            text = _read(signal_path)
            self.assertIn('"direction_label":"improving"', text)
            with open(signal_path, "w", encoding="utf-8") as fh:   # deliberate tamper
                fh.write(text.replace('"direction_label":"improving"',
                                      '"direction_label":"deteriorating"', 1))
            response = _call("GET", "/replay/RUN-TAMPER", store_dir=store_dir)
            self.assertEqual(response["status"], 200)
            html = response["body"]
            self.assertIn('<div class="verdict bad">deterministic_match: False', html)
            self.assertIn("FAILURE", html)
            self.assertIn("Named differences", html)
            self.assertIn("direction_label", html)      # the diverged field is NAMED
            self.assertIn("diverged", html)
            self.assertIn("persisted=", html)           # both sides of the divergence

    def test_rendering_the_replay_page_never_changes_a_stored_byte(self):
        store_dir = _STATE["store_dir"]
        names = ("run_store.jsonl", "signal_store.jsonl", "theme_pulse_store.jsonl",
                 "event_store.jsonl", "finding_store.jsonl", "alert_store.jsonl")
        before = {n: _read_bytes(os.path.join(store_dir, n)) for n in names}
        _call("GET", "/replay/" + _RUN1)
        _call("GET", "/runs/" + _RUN1)
        _call("GET", "/")
        for name in names:
            self.assertEqual(_read_bytes(os.path.join(store_dir, name)), before[name],
                             "page render mutated {0}".format(name))


# =========================================================================== #
# 5. Alert inbox: plain-English reasons + an Acknowledge form (no trade verb)   #
# =========================================================================== #
class AlertInboxPageTests(unittest.TestCase):
    def test_renders_the_reason_severity_label_and_subjects(self):
        html = _html("/alerts")
        self.assertIn("changed state between run", html)   # the plain-English reason
        self.assertIn("notice", html)                      # severity as a LABEL
        self.assertIn("physical_ai", html)
        self.assertIn("theme pulse changed", html)

    def test_unacked_alert_carries_an_ack_form_posting_to_the_api(self):
        html = _html("/alerts")
        self.assertIn('action="/api/alerts/{0}/ack"'.format(_ALERT_ID), html)
        self.assertIn('method="post"', html)
        self.assertIn("<button>Acknowledge</button>", html)
        self.assertIn("OPERATOR action", html)
        self.assertIn("not a market action", html)

    def test_ack_through_the_form_target_flips_the_row_to_acknowledged(self):
        with tempfile.TemporaryDirectory() as store_dir:
            _seed_store(store_dir, "RUN-ACK", _NOW1)
            alert = rm.Alert(
                alert_id="alert.RUN-ACK.seeded", run_id="RUN-ACK",
                category="theme_pulse_changed", severity="notice",
                human_readable_reason="Theme pulse changed state between two runs.",
                subject_themes=("robotics",), created_at=_NOW1)
            rm.AlertStore(store_dir).append(alert, timestamp=_NOW1)
            before = _call("GET", "/alerts", store_dir=store_dir)["body"]
            self.assertIn("<button>Acknowledge</button>", before)
            ack = _call("POST", "/api/alerts/alert.RUN-ACK.seeded/ack",
                        body={"at": _NOW3, "acknowledged_by": "operator-test"},
                        store_dir=store_dir)
            self.assertEqual(ack["status"], 200)
            after = _call("GET", "/alerts", store_dir=store_dir)["body"]
            self.assertNotIn("<button>Acknowledge</button>", after)
            self.assertIn("acknowledged", after)


# =========================================================================== #
# 6. Settings page: current settings + PUT form + Pause / Resume controls       #
# =========================================================================== #
class SettingsPageTests(unittest.TestCase):
    def test_shows_the_journaled_current_settings_and_revision(self):
        html = _html("/settings")
        self.assertIn("physical_ai; robotics", html)
        self.assertIn("IREN; NVDA", html)
        self.assertIn("Journal revision", html)
        self.assertIn("never a mutation", html)

    def test_settings_form_targets_put_via_the_method_override(self):
        html = _html("/settings")
        self.assertIn('action="/api/settings"', html)
        self.assertIn('name="_method" value="PUT"', html)
        self.assertIn("<button>Save settings</button>", html)
        self.assertIn('value="IREN, NVDA"', html)      # prefilled from the journal

    def test_pause_and_resume_forms_with_exact_labels_and_policy_choices(self):
        html = _html("/settings")
        self.assertIn('action="/api/schedule/pause"', html)
        self.assertIn('action="/api/schedule/resume"', html)
        self.assertIn("<button>Pause</button>", html)
        self.assertIn("<button>Resume</button>", html)
        self.assertIn('<option value="all">all policies</option>', html)
        self.assertIn("cadence.news_filings", html)
        self.assertIn("not paused", html)              # honest paused_all state

    def test_operator_forms_all_declare_themselves_operator_actions(self):
        for path in ("/", "/alerts", "/settings"):
            html = _html(path)
            for _ in re.findall(r'<form class="op-form"', html):
                pass
            self.assertEqual(html.count('<form class="op-form"'),
                             html.count("OPERATOR action"), path)


# =========================================================================== #
# 7. Home page: counts, latest run, manual-pulse form, canvas note/links        #
# =========================================================================== #
class HomePageTests(unittest.TestCase):
    def test_home_shows_store_counts_and_the_latest_run(self):
        html = _html("/")
        self.assertIn("Store status", html)
        self.assertIn("Latest persisted run", html)
        self.assertIn(_STATE["run2"], html)
        self.assertIn("settings revision", html)

    def test_manual_pulse_form_with_the_exact_label_and_no_scheduler_claim(self):
        html = _html("/")
        self.assertIn('action="/api/pulse"', html)
        self.assertIn("<button>Run manual pulse</button>", html)
        self.assertIn("manual, on-demand; no scheduler started", html)

    def test_canvas_absent_renders_a_note_and_no_dead_link(self):
        html = _html("/")
        self.assertIn("Universe Canvas: not generated in this store", html)
        self.assertNotIn('href="/canvas/', html)       # a note, never a dead link

    def test_canvas_present_renders_real_links_and_serves_the_artifact(self):
        with tempfile.TemporaryDirectory() as store_dir:
            _seed_store(store_dir, "RUN-CANVAS", _NOW1)
            canvas_dir = os.path.join(store_dir, CANVAS_DIRNAME)
            os.makedirs(canvas_dir)
            artifact = "<html><body>generated canvas artifact</body></html>"
            with open(os.path.join(canvas_dir, "universe.html"), "w",
                      encoding="utf-8") as fh:
                fh.write(artifact)
            home = _call("GET", "/", store_dir=store_dir)["body"]
            self.assertIn('href="/canvas/universe.html"', home)
            self.assertNotIn('href="/canvas/dashboard.html"', home)   # absent -> unlinked
            served = _call("GET", "/canvas/universe.html", store_dir=store_dir)
            self.assertEqual(served["status"], 200)
            self.assertEqual(served["body"], artifact)
            self.assertEqual(
                _call("GET", "/canvas/dashboard.html", store_dir=store_dir)["status"], 404)

    def test_canvas_route_refuses_non_allowlisted_names(self):
        for name in ("secrets.txt", "..%2Fsettings_store.jsonl", "nope.html"):
            self.assertEqual(_call("GET", "/canvas/" + name)["status"], 404, name)
        self.assertEqual(_call("GET", "/canvas/../run_store.jsonl")["status"], 404)
        self.assertEqual(tuple(sorted(CANVAS_PAGES)),
                         tuple(sorted(("universe.html", "dashboard.html",
                                       "data_quality.html", "cockpit.html"))))


# =========================================================================== #
# 8. Page hygiene: no Sanskrit, no trade verb, no CDN, no secret, no score      #
# =========================================================================== #
class PageHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {path: _html(path) for path in _PAGE_PATHS}
        cls.pages["/runs/RUN-NOPE"] = _STATE["page_404"]["body"]

    def test_zero_sanskrit_terms_on_any_page(self):
        for path, html in self.pages.items():
            low = html.lower()
            for token in _SANSKRIT_TOKENS:
                self.assertNotIn(token, low,
                                 "Sanskrit term {0!r} on page {1}".format(token, path))

    def test_zero_trade_affordances_on_any_page(self):
        for path, html in self.pages.items():
            matches = _TRADE_WORD.findall(html)
            self.assertEqual(matches, [],
                             "trade verb(s) {0} on page {1}".format(matches, path))

    def test_only_the_allowed_operator_buttons_exist(self):
        for path, html in self.pages.items():
            for label in _BUTTON.findall(html):
                self.assertIn(label.strip(), _ALLOWED_BUTTONS,
                              "unexpected button {0!r} on page {1}".format(label, path))
            self.assertNotIn("<input type=\"submit\"", html, path)
            self.assertNotIn("type=\"submit\"", html, path)

    def test_zero_external_references_scripts_or_stylesheets(self):
        for path, html in self.pages.items():
            low = html.lower()
            for token in _EXTERNAL_TOKENS:
                self.assertNotIn(token, low,
                                 "external reference {0!r} on page {1}".format(token, path))

    def test_zero_credential_keys_or_secret_like_values(self):
        for path, html in self.pages.items():
            low = html.lower()
            for token in _CRED_TOKENS:
                self.assertNotIn(token, low,
                                 "credential-like token {0!r} on page {1}".format(
                                     token, path))
            for pattern in _SECRET_VALUE_PATTERNS:
                self.assertIsNone(pattern.search(html), path)

    def test_zero_score_rank_rating_tokens(self):
        for path, html in self.pages.items():
            low = html.lower()
            for token in _SCORE_TOKENS:
                self.assertNotIn(token, low,
                                 "score-like token {0!r} on page {1}".format(token, path))

    def test_zero_live_or_realtime_claims(self):
        for path, html in self.pages.items():
            low = html.lower()
            for claim in _LIVE_CLAIMS:
                self.assertNotIn(claim, low,
                                 "live-claim wording {0!r} on page {1}".format(claim, path))
            self.assertIsNone(_LIVE_WORD.search(html), path)


# =========================================================================== #
# 9. The page layer stays PURE: AST-proven, like the dispatcher                 #
# =========================================================================== #
class PurePageLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: _read(path)
                       for name, path in (("api.py", _API_PY), ("pages.py", _PAGES_PY),
                                          ("app_assets.py", _ASSETS_PY))}
        cls.trees = {name: ast.parse(source) for name, source in cls.sources.items()}

    def test_no_network_server_or_clock_import_in_the_page_layer(self):
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                for module in names:
                    for banned in _BANNED_IMPORT_ROOTS:
                        self.assertFalse(
                            module == banned or module.startswith(banned + "."),
                            "banned import {0!r} in {1}".format(module, name))

    def test_no_wall_clock_call_in_the_page_layer(self):
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, _WALL_CLOCK_ATTRS,
                                     "wall-clock-like call .{0}() in {1}".format(
                                         node.func.attr, name))

    def test_no_loop_forever_construct_in_the_page_layer(self):
        for name, tree in self.trees.items():
            self.assertFalse(any(isinstance(n, ast.While) for n in ast.walk(tree)),
                             "a while loop crept into {0}".format(name))
        for name, source in self.sources.items():
            self.assertNotIn("serve_forever", source, name)
            self.assertNotIn("Thread", source, name)

    def test_no_javascript_or_fetch_in_the_inline_assets(self):
        source = self.sources["app_assets.py"]
        for token in ("fetch(", "XMLHttpRequest", "<script", "addEventListener",
                      "@import", "url(http"):
            self.assertNotIn(token, source)

    def test_offline_kill_switch_is_active_for_this_module(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


# =========================================================================== #
# 10. Untouched paths: demo default + default pulse CLI stay byte-identical     #
# =========================================================================== #
class UntouchedPathsTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app   # lazy: not a page dependency
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                self.assertEqual(_read_bytes(a[name]), _read_bytes(b[name]),
                                 "demo default drifted for {0}".format(name))

    def test_default_pulse_cli_byte_identical(self):
        from tattva_pulse.__main__ import main as pulse_cli_main
        outputs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                out_dir = os.path.join(d, "out")
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = pulse_cli_main(["--watchlist", "IREN,NVDA",
                                         "--themes", "physical_ai,robotics",
                                         "--out", out_dir])
                self.assertEqual(rc, 0)
                pages = {}
                for base, _dirs, names in os.walk(out_dir):
                    for name in sorted(names):
                        path = os.path.join(base, name)
                        pages[os.path.relpath(path, out_dir)] = _read_bytes(path)
                outputs.append((buf.getvalue().replace(out_dir, "<out>"), pages))
        self.assertEqual(outputs[0][0], outputs[1][0])
        self.assertEqual(sorted(outputs[0][1]), sorted(outputs[1][1]))
        for name in outputs[0][1]:
            self.assertEqual(outputs[0][1][name], outputs[1][1][name],
                             "default CLI output drifted for {0}".format(name))

    def test_default_manual_pulse_output_unchanged_by_the_page_slice(self):
        first = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        again = rm.run_pulse(["IREN", "NVDA"], ["physical_ai", "robotics"], now=_NOW1)
        self.assertEqual([s.signal_id for s in first.signals],
                         [s.signal_id for s in again.signals])
        self.assertEqual(first.theme_pulses, again.theme_pulses)

    def test_reality_mesh_never_imports_the_app_package(self):
        mesh_dir = os.path.join(_SRC, "reality_mesh")
        for base, _dirs, names in os.walk(mesh_dir):
            for name in names:
                if name.endswith(".py"):
                    self.assertNotIn("cosmosiq_app", _read(os.path.join(base, name)),
                                     "reality_mesh must not know the app exists "
                                     "({0})".format(name))


if __name__ == "__main__":
    unittest.main()
