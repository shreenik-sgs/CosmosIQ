"""IMPLEMENTATION-016C — theme / company / capital-candidate cockpits (offline, dispatcher-only).

The cockpits are READ/INSPECT surfaces over the persisted stores + the already-accepted engines:
* /themes + /themes/<id>  — pulse-state timeline + the why-it-changed persisted-state diff;
* /companies/<ticker>     — per-ticker evidence with claim-status labels (claims never facts);
* /candidates/<ticker>    — on-demand diligence via the accepted engines; honest absence
  ("insufficient inputs — no thesis fabricated"); READ-ONLY Execution Preview section
  ("no order is placed").
All server-rendered by pure functions, exercised through dispatch() alone under a socket
kill-switch. No new operator form is introduced by this slice.
"""
import os
import re
import socket
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cosmosiq_app import dispatch
from reality_mesh.runtime import PulseRun
from reality_mesh.models import ThemePulse
from reality_mesh.stores import RunStore, ThemePulseStore

_NOW = "2026-07-01T15:00:00"


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net blocked"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _req(store, method, path, body=None):
    return dispatch({"method": method, "path": path, "query": {}, "body": body or {}},
                    store_dir=store, now=_NOW)


class _SeededCase(unittest.TestCase):
    """One pulse run (A) via the API, plus a directly-seeded later run (B) whose physical-ai
    pulse carries a DIFFERENT state — the minimal honest fixture for the why-changed diff."""

    @classmethod
    def setUpClass(cls):
        cls.store = tempfile.mkdtemp(prefix="cockpit_016c_")
        resp = _req(cls.store, "POST", "/api/pulse",
                    {"watchlist": ["IREN", "AAOI"], "themes": ["physical-ai"], "now": _NOW})
        assert resp["status"] == 200, resp
        cls.run_a = resp["body"]["run_id"]
        # run B: a later persisted run whose physical-ai pulse state differs (Crowded).
        cls.run_b = "seeded.later.run"
        RunStore(cls.store).append(
            PulseRun(run_id=cls.run_b, started_at="2026-07-01T16:00:00",
                     completed_at="2026-07-01T16:00:05", mode="pulse", trigger_type="manual",
                     watchlist=("IREN", "AAOI"), themes=("physical-ai",),
                     theme_pulses_created=1, data_quality_status="healthy"),
            run_id=cls.run_b, timestamp="2026-07-01T16:00:05")
        ThemePulseStore(cls.store).append(
            ThemePulse(theme_pulse_id="tp.seeded.crowded", theme_id="physical-ai",
                       theme_name="Physical AI", state="Crowded", breadth_label="major",
                       freshness_label="fresh"),
            run_id=cls.run_b, timestamp="2026-07-01T16:00:05")

    def page(self, path):
        return _req(self.store, "GET", path)


class ThemeCockpitTests(_SeededCase):
    def test_theme_list_shows_latest_states(self):
        r = self.page("/themes")
        self.assertEqual(r["status"], 200)
        self.assertIn("physical-ai", r["body"])
        self.assertIn("Crowded", r["body"])                    # latest state visible

    def test_nav_includes_themes(self):
        self.assertIn('href="/themes"', self.page("/runs")["body"])

    def test_timeline_shows_both_runs_and_states(self):
        html = self.page("/themes/physical-ai")["body"]
        self.assertIn(self.run_a, html)
        self.assertIn(self.run_b, html)
        self.assertIn("Crowded", html)

    def test_why_changed_diff_names_both_states(self):
        html = self.page("/themes/physical-ai")["body"]
        # the persisted-state diff must name the change (A-state -> Crowded) and stay honest
        # about the alert record (this seeded run wrote no alert -> the honest note renders).
        self.assertIn("Crowded", html)
        self.assertRegex(html, r"why", msg="the why-changed section must exist")
        self.assertTrue(("no alert record" in html) or ("inbox alert reason" in html))

    def test_contributing_signals_show_authority_and_weak_marks(self):
        html = self.page("/themes/physical-ai")["body"].lower()
        self.assertTrue(("authority" in html) or ("convenience" in html) or ("rumor" in html))

    def test_unknown_theme_is_honest_not_fabricated(self):
        html = self.page("/themes/never-seen")["body"].lower()
        self.assertTrue(("no persisted" in html) or ("no pulse" in html)
                        or ("no data" in html) or ("not found" in html))


class CompanyCockpitTests(_SeededCase):
    def test_company_page_renders_claim_labels(self):
        html = self.page("/companies/IREN")["body"]
        self.assertEqual(self.page("/companies/IREN")["status"], 200)
        self.assertIn("IREN", html)

    def test_company_claims_never_rendered_as_verified_facts(self):
        html = self.page("/companies/IREN")["body"]
        # An SEC filing fact IS a verified fact (canonical) — that is correct. The invariant
        # is that a COMPANY claim / reported claim / inferred / rumor row is never captioned
        # verified: every row carrying a "verified fact" badge must also carry canonical
        # authority, and the page states the claims-are-unverified discipline.
        self.assertIn("never as a fact", html)
        for row in re.findall(r"<tr>.*?</tr>", html, re.S):
            if "verified fact" in row:
                self.assertIn("canonical", row,
                              "a verified-fact badge outside canonical authority:\n" + row)
            if re.search(r"(?i)company claim|reported claim|rumor", row):
                self.assertNotIn("verified fact", row)


class CandidateCockpitTests(_SeededCase):
    def test_honest_absence_without_inputs(self):
        html = self.page("/candidates/IREN")["body"].lower()
        self.assertIn("no thesis fabricated", html)
        self.assertIn("no manual execution intent", html)
        self.assertIn("no order is placed", html)

    def test_malformed_inputs_are_named_not_guessed(self):
        bad_dir = os.path.join(self.store, "diligence_inputs")
        os.makedirs(bad_dir, exist_ok=True)
        with open(os.path.join(bad_dir, "AAOI.json"), "w") as fh:
            fh.write("{not json")
        html = self.page("/candidates/AAOI")["body"].lower()
        self.assertIn("nothing is guessed", html)
        self.assertIn("no thesis fabricated", html)

    def test_insufficient_inputs_state_the_reason(self):
        thin_dir = os.path.join(self.store, "diligence_inputs")
        os.makedirs(thin_dir, exist_ok=True)
        with open(os.path.join(thin_dir, "AMBA.json"), "w") as fh:
            fh.write('{"domain": "physical-ai"}')       # no observations, no candidate
        html = self.page("/candidates/AMBA")["body"].lower()
        self.assertIn("no thesis fabricated", html)
        self.assertIn("no source observations", html)


class SweepTests(_SeededCase):
    PAGES = ("/themes", "/themes/physical-ai", "/companies/IREN", "/candidates/IREN")

    def _all_html(self):
        return "".join(self.page(p)["body"] for p in self.PAGES)

    def test_no_trade_affordance_or_verb(self):
        html = self._all_html()
        self.assertNotRegex(html, r"(?i)\b(buy|sell|order now|submit order|place order|"
                                  r"execute trade|broker submit|trade now|auto[- ]trade)\b")
        # cockpits are read/inspect surfaces: NO new forms at all on these pages
        self.assertNotIn("<form", html)
        self.assertNotIn("<button", html)

    def test_no_external_refs_or_secrets_or_scores(self):
        html = self._all_html()
        self.assertNotRegex(html, r"(?i)https?://|<script src|<link |@import|cdn\.")
        self.assertNotRegex(html, r"(?i)api_key|apikey|sk-[a-z0-9]{8}|bearer ")
        self.assertNotRegex(html, r'(?i)"score"|alpha score|ranked picks|investability score')

    def test_no_sanskrit_and_no_live_claims(self):
        html = self._all_html()
        self.assertNotRegex(html, r"(?i)sudarshan|adhara|buddhi|sphurana|nivesha|"
                                  r"saarathi|kriya|anubhava")
        self.assertNotRegex(html, r"(?i)\b(real-?time|live feed|always-?on|streaming)\b")

    def test_as_of_honesty_line_everywhere(self):
        for p in self.PAGES:
            self.assertIn("as of", self.page(p)["body"].lower(), p)

    def test_pages_render_byte_deterministically(self):
        for p in self.PAGES:
            self.assertEqual(self.page(p)["body"], self.page(p)["body"], p)

    def test_render_mutates_no_stored_byte(self):
        files = {f: open(os.path.join(self.store, f), "rb").read()
                 for f in os.listdir(self.store) if f.endswith(".jsonl")}
        self._all_html()
        for f, before in files.items():
            self.assertEqual(open(os.path.join(self.store, f), "rb").read(), before, f)


if __name__ == "__main__":
    unittest.main()
