"""IMPLEMENTATION-014F — the Macro Regime sensor (#11) + the four company-evidence sensors
(Customer #13 / Supplier #14 / Bottleneck #15 / Leadership #16) + the local macro-data adapter.

Five descriptor-only Reality-Intelligence agents become IMPLEMENTED: each reuses its
built-in ``tattva.*`` descriptor and emits AgentFinding ONLY, in-discipline, labels only --
no trade / score token anywhere (regex-swept below). The evidence sensors consume the
company-document events 014C ALREADY emits: a company-sourced claim STAYS ``company_claim``
in the finding summary (the 012G ``claim_status_of`` stamping pattern) -- an evidence
sensor NEVER upgrades a company claim to a fact; company-stated capacity carries the
explicit "not independently verified" gap (the 014C TAM technique); concentration /
dependency / credibility reads are LABELS. The macro adapter is LOCAL-FILE only at
``convenience`` authority; missing / malformed / stale input is a VISIBLE gap, never a
fabricated value. The whole suite is offline; the DEFAULT run_pulse path stays
byte-identical (each new sensor runs only when its events exist -- the 014D pattern).
"""
import ast
import os
import re
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import labels as _labels
from reality_mesh.adapters import (
    DESCRIPTOR_ONLY_CONSUMER_GAPS,
    LOCAL_MACRO_DATA_DESCRIPTOR,
    LOCAL_MACRO_DATA_DISCIPLINES,
    MACRO_READINGS_FILENAME,
    CompanyDocumentsAdapter,
    LocalMacroDataAdapter,
    SourceAdapterResult,
    source_health_from_result,
)
from reality_mesh.agents import TATTVA_FINDING_SUBTYPES
from reality_mesh.models import AgentFinding, RealityEvent
from reality_mesh.pulse import PulseResult, run_pulse
from reality_mesh.registry import build_default_registry
from reality_mesh.sensors import (
    BOTTLENECK_EVIDENCE_FINDING_TYPES,
    BottleneckEvidenceAgent,
    COMPANY_STATED_CAPACITY_GAP,
    CUSTOMER_EVIDENCE_FINDING_TYPES,
    CustomerEvidenceAgent,
    LEADERSHIP_EVIDENCE_FINDING_TYPES,
    LeadershipEvidenceAgent,
    MACRO_REGIME_FINDING_TYPES,
    MACRO_REGIME_SUBAGENTS,
    MACRO_SUBAGENT_REQUIRED_KEYS,
    MacroRegimeAgent,
    SUPPLIER_EVIDENCE_FINDING_TYPES,
    SupplierEvidenceAgent,
    claim_status_of,
    has_bottleneck_evidence_events,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src", "reality_mesh")
_MACRO_BASE = os.path.join(_HERE, "fixtures", "reality_mesh", "local_macro_data")
_TIGHTENING_DIR = os.path.join(_MACRO_BASE, "tightening")
_RISK_ON_DIR = os.path.join(_MACRO_BASE, "risk_on")
_STALE_DIR = os.path.join(_MACRO_BASE, "stale")
_MALFORMED_DIR = os.path.join(_MACRO_BASE, "malformed")
_UNITLESS_DIR = os.path.join(_MACRO_BASE, "unitless")
_EVIDENCE_DIR = os.path.join(
    _HERE, "fixtures", "reality_mesh", "company_documents", "evidence")

_WATCHLIST = "IREN"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-01T14:00:00Z"

# Trade-language tokens that may NEVER appear in ANY finding field of the five agents: a
# macro / evidence state is a LABEL, never a trade instruction (same sweep as 014D).
_TRADE_TOKEN_RE = re.compile(
    r"\b(buy|buys|buying|sell|sells|selling|entry|entries|exit|exits|target|targets|"
    r"stop|stops|stop-loss|order|orders|position|accumulate|trim|hold)\b",
    re.IGNORECASE)

_FIVE_AGENTS = (
    ("tattva.macro_regime", MacroRegimeAgent, "macro_regime",
     "MacroRegimeFinding"),
    ("tattva.customer_evidence", CustomerEvidenceAgent, "customer_evidence",
     "CustomerEvidenceFinding"),
    ("tattva.supplier_evidence", SupplierEvidenceAgent, "supplier_evidence",
     "SupplierEvidenceFinding"),
    ("tattva.bottleneck_evidence", BottleneckEvidenceAgent, "bottleneck_evidence",
     "BottleneckEvidenceFinding"),
    ("tattva.leadership_evidence", LeadershipEvidenceAgent, "leadership_evidence",
     "LeadershipEvidenceFinding"),
)


def _macro_findings(data_dir):
    events, _ = LocalMacroDataAdapter(data_dir).fetch_checked(
        watchlist=(), themes=(), now=_NOW)
    return MacroRegimeAgent().run_checked(None, events)


def _evidence_events():
    events, _ = CompanyDocumentsAdapter(_EVIDENCE_DIR).fetch_checked(
        watchlist=("IREN",), themes=("physical-ai",), now=_NOW)
    return events


def _by_type(findings, finding_type):
    return [f for f in findings if f.finding_type == finding_type]


def _all_strings_of(finding):
    """Every string value carried by a finding (scalar fields + tuple elements)."""
    values = []
    for name in finding.__dataclass_fields__:
        value = getattr(finding, name)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, tuple):
            values.extend(str(v) for v in value)
    return values


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _macro_event(**readings):
    """A hand-built macro event carrying only the given named readings (unit 'x')."""
    return RealityEvent(
        event_id="local.macro_regime.handbuilt.{0}".format(
            "_".join(sorted(readings)) or "empty"),
        timestamp=_NOW, source_id="local_file.macro_regime",
        source_type="local_macro_data_file", source_authority="convenience",
        claim_status="inferred", raw_payload_ref="localfile:x#sha256=0",
        discipline="macro_regime", event_type="macro_reading",
        numeric_values=tuple((k, float(v), "x") for k, v in sorted(readings.items())),
        source_refs=("localfile:x#sha256=0",))


# --------------------------------------------------------------------------- #
# 1. Identity: all five agents reuse their built-in descriptors                 #
# --------------------------------------------------------------------------- #
class AgentIdentityTests(unittest.TestCase):
    def test_agents_reuse_the_builtin_descriptors(self):
        registry = build_default_registry()
        for agent_id, factory, discipline, subtype in _FIVE_AGENTS:
            agent = factory()
            self.assertIs(agent.descriptor, registry.get(agent_id))
            self.assertEqual(agent.descriptor.discipline, discipline)
            self.assertEqual(agent.descriptor.layer, "reality_intelligence")
            self.assertEqual(set(agent.descriptor.emits), {"AgentFinding", subtype})
            self.assertIn(subtype, TATTVA_FINDING_SUBTYPES)

    def test_registry_subagent_rosters_are_the_accepted_ones(self):
        registry = build_default_registry()
        self.assertEqual(registry.get("tattva.macro_regime").subagents,
                         MACRO_REGIME_SUBAGENTS)
        self.assertEqual(len(MACRO_REGIME_SUBAGENTS), 7)
        self.assertEqual(set(MACRO_SUBAGENT_REQUIRED_KEYS), set(MACRO_REGIME_SUBAGENTS))
        self.assertEqual(len(registry.get("tattva.customer_evidence").subagents), 4)
        self.assertEqual(len(registry.get("tattva.supplier_evidence").subagents), 4)
        self.assertEqual(len(registry.get("tattva.bottleneck_evidence").subagents), 6)
        self.assertEqual(len(registry.get("tattva.leadership_evidence").subagents), 5)

    def test_finding_type_vocabularies_carry_no_trade_token(self):
        for finding_type in (MACRO_REGIME_FINDING_TYPES
                             + CUSTOMER_EVIDENCE_FINDING_TYPES
                             + SUPPLIER_EVIDENCE_FINDING_TYPES
                             + BOTTLENECK_EVIDENCE_FINDING_TYPES
                             + LEADERSHIP_EVIDENCE_FINDING_TYPES):
            self.assertIsNone(_TRADE_TOKEN_RE.search(finding_type), finding_type)


# --------------------------------------------------------------------------- #
# 2. The Macro Regime agent: labels from market-wide readings                   #
# --------------------------------------------------------------------------- #
class MacroRegimeAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tightening = _macro_findings(_TIGHTENING_DIR)
        cls.risk_on = _macro_findings(_RISK_ON_DIR)

    def test_emits_agent_findings_only_in_discipline(self):
        self.assertTrue(self.tightening and self.risk_on)
        for f in self.tightening + self.risk_on:
            self.assertIsInstance(f, AgentFinding)
            self.assertEqual(f.discipline, "macro_regime")
            self.assertEqual(f.agent_id, "tattva.macro_regime")
            self.assertIn(f.finding_type, MACRO_REGIME_FINDING_TYPES)

    def test_tightening_fixture_reads_deteriorating_risk_off(self):
        types = {f.finding_type for f in self.tightening}
        for expected in ("duration_pressure", "curve_inversion", "liquidity_tightening",
                         "macro_shock", "risk_off_macro"):
            self.assertIn(expected, types)
        for f in self.tightening:
            self.assertEqual(f.direction_label, "deteriorating", f.finding_id)
        overall = _by_type(self.tightening, "risk_off_macro")[0]
        self.assertEqual(overall.corroboration_status, "corroborated")
        self.assertEqual(overall.magnitude_label, "major")
        self.assertEqual(overall.urgency_label, "elevated")

    def test_risk_on_fixture_reads_improving_risk_on(self):
        types = {f.finding_type for f in self.risk_on}
        for expected in ("liquidity_easing", "curve_steepening", "risk_on_macro"):
            self.assertIn(expected, types)
        for f in self.risk_on:
            self.assertEqual(f.direction_label, "improving", f.finding_id)
        overall = _by_type(self.risk_on, "risk_on_macro")[0]
        self.assertEqual(overall.corroboration_status, "corroborated")

    def test_reading_themes_are_honoured_where_present(self):
        # the risk_on liquidity reading carries themes: ["physical-ai"]
        overall = _by_type(self.risk_on, "risk_on_macro")[0]
        self.assertIn("physical-ai", overall.affected_themes)

    def test_every_label_is_closed_vocabulary_at_convenience_authority(self):
        for f in self.tightening + self.risk_on:
            self.assertIn(f.direction_label, _labels.DIRECTION_LABELS)
            self.assertIn(f.magnitude_label, _labels.MAGNITUDE_LABELS)
            self.assertIn(f.urgency_label, _labels.URGENCY_LABELS)
            self.assertIn(f.confidence_label, _labels.CONFIDENCE_LABELS)
            self.assertIn(f.freshness_label, _labels.FRESHNESS_LABELS)
            self.assertEqual(f.source_authority_summary, "convenience")
            self.assertEqual(f.half_life, "days")
            self.assertEqual(f.routing_targets, ("TattvaSignalFusion",))
            self.assertTrue(f.input_events)

    def test_missing_reading_is_a_gap_never_computed(self):
        findings = MacroRegimeAgent().run_checked(None, (_macro_event(vix_level=28),))
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.finding_type, "risk_off_macro")   # the VIX tilt alone
        gaps = " | ".join(f.data_gaps)
        for subagent in ("Rates", "Yield Curve", "Dollar", "Credit Spread",
                         "Inflation/Jobs Surprise", "Liquidity"):
            self.assertIn("{0} subagent has no reading".format(subagent), gaps)
        self.assertIn("never computed from nothing", gaps)
        types = {x.finding_type for x in findings}
        for absent in ("duration_pressure", "curve_inversion", "liquidity_tightening",
                       "liquidity_easing", "macro_shock", "curve_steepening"):
            self.assertNotIn(absent, types)                  # never computed from nothing

    def test_no_verdict_at_all_yields_explicit_incomplete_finding(self):
        findings = MacroRegimeAgent().run_checked(None, (_macro_event(vix_level=20),))
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.finding_type, "macro_read_incomplete")
        self.assertEqual(f.direction_label, "neutral")
        self.assertTrue(any("subagent has no reading" in g for g in f.data_gaps))

    def test_stale_input_yields_stale_findings_plus_gap(self):
        findings = _macro_findings(_STALE_DIR)
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.freshness_label, "stale")     # preserved, never dropped
            self.assertTrue(any(
                "stale macro data preserved (not dropped)" in g for g in f.data_gaps),
                f.data_gaps)

    def test_out_of_discipline_events_are_ignored(self):
        event = RealityEvent(
            event_id="ev.other", timestamp=_NOW, source_id="s", source_type="t",
            source_authority="convenience", claim_status="inferred",
            raw_payload_ref="localfile:y#sha256=1", discipline="market_regime",
            event_type="index_breadth_reading", source_refs=("localfile:y#sha256=1",),
            numeric_values=(("vix_level", 30, "index"),))
        self.assertEqual(MacroRegimeAgent().run_checked(None, (event,)), ())

    def test_run_is_deterministic(self):
        self.assertEqual(self.tightening, _macro_findings(_TIGHTENING_DIR))


# --------------------------------------------------------------------------- #
# 3. The macro adapter: LOCAL file -> RealityEvents ONLY at convenience          #
# --------------------------------------------------------------------------- #
class LocalMacroDataAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = LocalMacroDataAdapter(_TIGHTENING_DIR)
        cls.events, cls.result = cls.adapter.fetch_checked(
            watchlist=(), themes=(), now=_NOW)

    def test_descriptor_declares_the_contract(self):
        d = self.adapter.descriptor
        self.assertIs(d, LOCAL_MACRO_DATA_DESCRIPTOR)
        self.assertFalse(d.network_required)                 # LOCAL FILES ONLY
        self.assertEqual(d.source_authority, "convenience")  # operator-downloaded macro
        self.assertEqual(d.credential_requirements, ())      # no credential exists to need
        self.assertEqual(d.outputs, ("macro_reading",))
        self.assertEqual(set(d.failure_modes), {"source_unavailable", "parse_error"})
        self.assertEqual(self.adapter.covered_disciplines, ("macro_regime",))
        self.assertEqual(LOCAL_MACRO_DATA_DISCIPLINES, ("macro_regime",))
        rules = " ".join(d.claim_status_rules).lower()
        self.assertIn("market-wide", rules)
        self.assertIn("never verified_fact", rules)

    def test_emits_reality_events_only_with_authority_and_provenance(self):
        self.assertEqual(self.result.status, "success")
        self.assertEqual(self.result.source_health, "healthy")
        self.assertEqual(self.result.credentials_status, "not_required")
        self.assertEqual(self.result.rate_limit_status, "ok")
        self.assertEqual(len(self.events), 9)                # one event per named reading
        for ev in self.events:
            self.assertIsInstance(ev, RealityEvent)
            self.assertNotIsInstance(ev, AgentFinding)
            self.assertEqual(ev.discipline, "macro_regime")
            self.assertEqual(ev.event_type, "macro_reading")
            self.assertEqual(ev.source_authority, "convenience")
            self.assertEqual(ev.claim_status, "inferred")    # derived, never verified_fact
            self.assertTrue(ev.raw_payload_ref.startswith("localfile:"))
            self.assertIn("#sha256=", ev.raw_payload_ref)
            self.assertTrue(ev.source_refs)
            self.assertEqual(ev.affected_companies, ())      # macro is MARKET-WIDE
            self.assertEqual(len(ev.numeric_values), 1)
            name, value, unit = ev.numeric_values[0]
            self.assertTrue(name and unit)                   # named readings carry units
            self.assertIsInstance(value, float)

    def test_watchlist_scoping_not_applicable_is_a_visible_warning(self):
        _events, result = LocalMacroDataAdapter(_TIGHTENING_DIR).fetch_checked(
            watchlist=("IREN",), themes=(), now=_NOW)
        self.assertTrue(any("market-wide" in w and "not applicable" in w
                            for w in result.warnings))

    def test_reading_level_themes_flow_onto_the_event(self):
        events, _ = LocalMacroDataAdapter(_RISK_ON_DIR).fetch_checked(now=_NOW)
        themed = [e for e in events if e.affected_themes]
        self.assertEqual(len(themed), 1)
        self.assertEqual(themed[0].affected_themes, ("physical-ai",))

    def test_ids_are_deterministic_from_content(self):
        events2, result2 = LocalMacroDataAdapter(_TIGHTENING_DIR).fetch_checked(now=_NOW)
        self.assertEqual([e.event_id for e in self.events],
                         [e.event_id for e in events2])
        self.assertEqual(self.result.run_id, result2.run_id)
        for ev in self.events:
            self.assertRegex(ev.event_id,
                             r"^local\.macro_regime\.[a-z0-9_]+\.[0-9a-f]{12}$")

    def test_missing_file_is_failed_with_gap_naming_it(self):
        events, result = LocalMacroDataAdapter(
            os.path.join(_MACRO_BASE, "does_not_exist")).fetch_checked(now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertTrue(any("source_unavailable" in e for e in result.errors))
        gaps = " ".join(result.data_gaps)
        self.assertIn(MACRO_READINGS_FILENAME, gaps)
        self.assertIn("never fabricated", gaps)
        self.assertIn("no silent demo fallback", gaps)

    def test_malformed_file_is_failed_with_parse_error(self):
        events, result = LocalMacroDataAdapter(_MALFORMED_DIR).fetch_checked(now=_NOW)
        self.assertEqual(events, ())
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.source_health, "failed")
        self.assertTrue(any(e.startswith("parse_error: " + MACRO_READINGS_FILENAME)
                            for e in result.errors))
        self.assertTrue(any("malformed" in g and "nothing fabricated" in g
                            for g in result.data_gaps))

    def test_unitless_reading_is_rejected_never_a_fabricated_unit(self):
        events, result = LocalMacroDataAdapter(_UNITLESS_DIR).fetch_checked(now=_NOW)
        self.assertEqual(len(events), 1)                     # only the reading WITH a unit
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("has no unit" in e for e in result.errors))
        self.assertTrue(any("never a fabricated value" in g for g in result.data_gaps))

    def test_stale_as_of_marks_events_stale_preserved_not_dropped(self):
        events, result = LocalMacroDataAdapter(_STALE_DIR).fetch_checked(now=_NOW)
        self.assertTrue(events)
        for ev in events:
            self.assertEqual(ev.freshness_label, "stale")
        self.assertTrue(any("stale as_of" in w and "never dropped" in w
                            for w in result.warnings))

    def test_result_feeds_a_real_source_health_record(self):
        record = source_health_from_result(self.result, now=_NOW)
        self.assertEqual(record.source_id, "local_macro_data")
        self.assertEqual(record.last_status, "healthy")
        self.assertFalse(record.is_failed)
        _, failed = LocalMacroDataAdapter(_MALFORMED_DIR).fetch_checked(now=_NOW)
        self.assertTrue(source_health_from_result(failed, now=_NOW).is_failed)

    def test_empty_data_dir_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            LocalMacroDataAdapter("")


# --------------------------------------------------------------------------- #
# 4. The evidence agents: company claims STAY claims; labels only                #
# --------------------------------------------------------------------------- #
class EvidenceAgentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = _evidence_events()
        cls.by_event_id = {e.event_id: e for e in cls.events}
        cls.customer = CustomerEvidenceAgent().run_checked(None, cls.events)
        cls.supplier = SupplierEvidenceAgent().run_checked(None, cls.events)
        cls.bottleneck = BottleneckEvidenceAgent().run_checked(None, cls.events)
        cls.leadership = LeadershipEvidenceAgent().run_checked(None, cls.events)
        cls.all_findings = (cls.customer + cls.supplier + cls.bottleneck
                            + cls.leadership)

    def test_each_agent_emits_agent_findings_only_in_its_discipline(self):
        for findings, discipline, agent_id, types in (
                (self.customer, "customer_evidence", "tattva.customer_evidence",
                 CUSTOMER_EVIDENCE_FINDING_TYPES),
                (self.supplier, "supplier_evidence", "tattva.supplier_evidence",
                 SUPPLIER_EVIDENCE_FINDING_TYPES),
                (self.bottleneck, "bottleneck_evidence", "tattva.bottleneck_evidence",
                 BOTTLENECK_EVIDENCE_FINDING_TYPES),
                (self.leadership, "leadership_evidence", "tattva.leadership_evidence",
                 LEADERSHIP_EVIDENCE_FINDING_TYPES)):
            self.assertTrue(findings, discipline)
            for f in findings:
                self.assertIsInstance(f, AgentFinding)
                self.assertEqual(f.discipline, discipline)
                self.assertEqual(f.agent_id, agent_id)
                self.assertIn(f.finding_type, types)
                self.assertIn(f.direction_label, _labels.DIRECTION_LABELS)
                self.assertIn(f.magnitude_label, _labels.MAGNITUDE_LABELS)
                self.assertIn(f.urgency_label, _labels.URGENCY_LABELS)
                self.assertEqual(f.routing_targets, ("TattvaSignalFusion",))

    def test_customer_reads_win_adoption_and_concentration(self):
        wins = _by_type(self.customer, "customer_win_claim")
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].direction_label, "improving")
        conc = _by_type(self.customer, "concentration_note")
        self.assertEqual(len(conc), 1)
        # concentration is a dependency LABEL: neutral direction, elevated attention.
        self.assertEqual(conc[0].direction_label, "neutral")
        self.assertEqual(conc[0].urgency_label, "elevated")
        self.assertIn("dependency label", conc[0].finding_summary)
        adoption = _by_type(self.customer, "adoption_signal")
        self.assertEqual(len(adoption), 2)                   # strong + bare mention

    def test_supplier_reads_dependency_and_substitution_as_labels(self):
        dependency = _by_type(self.supplier, "supplier_dependency")
        self.assertEqual(len(dependency), 2)                 # sole-supplier + bare mention
        sole = [f for f in dependency if f.magnitude_label == "moderate"]
        self.assertEqual(len(sole), 1)
        self.assertEqual(sole[0].direction_label, "neutral")
        self.assertIn("dependency label", sole[0].finding_summary)
        substitution = _by_type(self.supplier, "substitution_risk")
        self.assertEqual(len(substitution), 1)
        self.assertEqual(substitution[0].direction_label, "deteriorating")

    def test_bottleneck_reads_capacity_lead_time_and_shortage(self):
        capacity = _by_type(self.bottleneck, "capacity_expansion_claim")
        self.assertEqual(len(capacity), 3)   # deck claim + CEO remark + analyst question
        lead = _by_type(self.bottleneck, "lead_time_note")
        self.assertEqual(len(lead), 1)
        self.assertEqual(lead[0].direction_label, "neutral")
        shortage = _by_type(self.bottleneck, "shortage_evidence")
        self.assertEqual(len(shortage), 1)
        self.assertEqual(shortage[0].direction_label, "deteriorating")

    def test_company_stated_capacity_carries_the_not_verified_gap(self):
        # the 014C TAM technique: a company's own capacity figure is never adopted.
        for f in self.bottleneck:
            if claim_status_of(f) == "company_claim":
                self.assertIn(COMPANY_STATED_CAPACITY_GAP, f.data_gaps, f.finding_id)
        gap_text = COMPANY_STATED_CAPACITY_GAP
        self.assertIn("not independently verified", gap_text)
        self.assertIn("never adopted as a fact", gap_text)

    def test_analyst_capacity_content_stays_reported_claim_without_the_gap(self):
        analyst = [f for f in self.bottleneck
                   if claim_status_of(f) == "reported_claim"]
        self.assertEqual(len(analyst), 1)                    # the analyst's Q&A question
        self.assertNotIn(COMPANY_STATED_CAPACITY_GAP, analyst[0].data_gaps)
        source = self.by_event_id[analyst[0].input_events[0]]
        self.assertEqual(source.claim_status, "reported_claim")
        self.assertEqual(source.event_type, "transcript_qa")

    def test_leadership_reads_all_four_evidence_types(self):
        for finding_type in LEADERSHIP_EVIDENCE_FINDING_TYPES:
            self.assertTrue(_by_type(self.leadership, finding_type), finding_type)
        flags = _by_type(self.leadership, "credibility_flag")
        self.assertEqual(flags[0].direction_label, "deteriorating")
        self.assertIn("credibility label", flags[0].finding_summary)
        dilution = _by_type(self.leadership, "dilution_history_note")
        # the dilution read came from an ir_deck_claim (news_filings-stamped) event,
        # consumed by event type + content and emitted in the agent's OWN discipline.
        source = self.by_event_id[dilution[0].input_events[0]]
        self.assertEqual(source.event_type, "ir_deck_claim")
        self.assertEqual(source.discipline, "news_filings")
        self.assertEqual(dilution[0].discipline, "leadership_evidence")

    def test_company_claims_are_never_upgraded_across_all_findings(self):
        # THE gate: a company-sourced statement STAYS company_claim on the finding; no
        # evidence finding anywhere stamps verified_fact or reads canonical authority.
        checked = 0
        for f in self.all_findings:
            stamped = claim_status_of(f)
            self.assertNotEqual(stamped, "verified_fact", f.finding_id)
            self.assertNotEqual(f.source_authority_summary, "canonical", f.finding_id)
            self.assertEqual(f.corroboration_status, "uncorroborated")
            for event_id in f.input_events:
                if self.by_event_id[event_id].claim_status == "company_claim":
                    self.assertEqual(stamped, "company_claim", f.finding_id)
                    self.assertEqual(f.source_authority_summary, "primary")
                    checked += 1
        self.assertGreater(checked, 10)     # the invariant was exercised broadly

    def test_findings_trace_to_the_014c_adapter_events(self):
        for f in self.all_findings:
            self.assertTrue(f.input_events)
            for event_id in f.input_events:
                self.assertTrue(event_id.startswith("companydocs.iren."), event_id)
            self.assertTrue(f.source_refs or f.evidence_refs)

    def test_no_trade_language_in_any_field_of_the_five_agents_findings(self):
        # The regex sweep across ALL FIVE agents' findings (macro both fixtures +
        # all four evidence agents).
        swept = list(self.all_findings)
        swept.extend(_macro_findings(_TIGHTENING_DIR))
        swept.extend(_macro_findings(_RISK_ON_DIR))
        self.assertTrue(swept)
        for f in swept:
            for text in _all_strings_of(f):
                match = _TRADE_TOKEN_RE.search(text)
                self.assertIsNone(
                    match, "trade token {0!r} leaked into finding field: {1!r}".format(
                        match.group(0) if match else "", text))

    def test_bottleneck_gate_helper_sees_company_documents(self):
        self.assertTrue(has_bottleneck_evidence_events(self.events))
        other = RealityEvent(
            event_id="ev.press", timestamp=_NOW, source_id="s", source_type="t",
            source_authority="convenience", claim_status="reported_claim",
            raw_payload_ref="localfile:z#sha256=2", discipline="news_filings",
            event_type="press_release", observed_fact="a routine announcement",
            source_refs=("localfile:z#sha256=2",))
        self.assertFalse(has_bottleneck_evidence_events((other,)))

    def test_runs_are_deterministic(self):
        events = _evidence_events()
        self.assertEqual(self.customer,
                         CustomerEvidenceAgent().run_checked(None, events))
        self.assertEqual(self.bottleneck,
                         BottleneckEvidenceAgent().run_checked(None, events))


# --------------------------------------------------------------------------- #
# 5. End to end: both adapters -> pulse -> five disciplines -> fusion -> signals #
# --------------------------------------------------------------------------- #
class PulseEndToEndTests(unittest.TestCase):
    _NEW_DISCIPLINES = ("macro_regime", "customer_evidence", "supplier_evidence",
                        "bottleneck_evidence", "leadership_evidence")

    @classmethod
    def setUpClass(cls):
        cls.r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_EVIDENCE_DIR),
                                    LocalMacroDataAdapter(_TIGHTENING_DIR)))

    def test_all_five_new_agents_ran_and_produced_findings(self):
        runs = {a.agent_id: a for a in self.r.agent_runs}
        for agent_id, _factory, discipline, _subtype in _FIVE_AGENTS:
            self.assertIn(agent_id, runs)
            self.assertEqual(runs[agent_id].status, "ok", agent_id)
            self.assertTrue(any(f.discipline == discipline for f in self.r.findings),
                            discipline)

    def test_findings_fused_into_signals_in_all_five_disciplines(self):
        signal_disciplines = {s.discipline for s in self.r.signals}
        for discipline in self._NEW_DISCIPLINES:
            self.assertIn(discipline, signal_disciplines)

    def test_signal_authority_summaries_stay_honest(self):
        for s in self.r.signals:
            if s.discipline == "macro_regime":
                self.assertEqual(self.r.authority_by_signal.get(s.signal_id),
                                 "convenience")
            elif s.discipline in self._NEW_DISCIPLINES:
                # evidence signals come from company IR: primary-but-claim, NEVER canonical
                self.assertNotEqual(self.r.authority_by_signal.get(s.signal_id),
                                    "canonical")

    def test_descriptor_only_consumer_gaps_became_findings(self):
        # the 014C-era honest gap ("no sensor implementation") is no longer true for a
        # discipline whose sensor RAN: the delivery was interpreted, so the satisfied gap
        # is dropped from the pulse roll-up and findings stand in its place.
        for discipline in ("customer_evidence", "supplier_evidence",
                           "leadership_evidence"):
            self.assertTrue(any(f.discipline == discipline for f in self.r.findings),
                            discipline)
            self.assertNotIn(DESCRIPTOR_ONLY_CONSUMER_GAPS[discipline], self.r.data_gaps)

    def test_adapter_results_surface_on_the_pulse(self):
        self.assertEqual(len(self.r.adapter_results), 2)
        by_id = {res.adapter_id: res for res in self.r.adapter_results}
        self.assertEqual(by_id["evidence.company_documents"].status, "success")
        self.assertEqual(by_id["local_macro_data"].status, "success")
        for res in self.r.adapter_results:
            self.assertIsInstance(res, SourceAdapterResult)
            self.assertEqual(res.credentials_status, "not_required")

    def test_uncovered_disciplines_still_come_from_fixtures(self):
        for discipline in ("market_regime", "sector_rotation", "theme_rotation",
                           "narrative"):
            self.assertTrue(any(f.discipline == discipline for f in self.r.findings),
                            discipline)

    def test_failed_macro_source_stays_a_gap_never_a_fabricated_finding(self):
        r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                      adapters=(LocalMacroDataAdapter(_MALFORMED_DIR),))
        self.assertFalse(any(f.discipline == "macro_regime" for f in r.findings))
        self.assertFalse(any(a.agent_id == "tattva.macro_regime" for a in r.agent_runs))
        self.assertTrue(any("malformed" in g and "nothing fabricated" in g
                            for g in r.data_gaps))
        self.assertEqual(r.adapter_results[0].status, "failed")

    def test_pulse_with_adapters_is_deterministic(self):
        again = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_EVIDENCE_DIR),
                                    LocalMacroDataAdapter(_TIGHTENING_DIR)))
        self.assertEqual(self.r, again)


# --------------------------------------------------------------------------- #
# 6. The DEFAULT pulse stays byte-identical (every new sensor is event-gated)    #
# --------------------------------------------------------------------------- #
class DefaultPulseUnchangedTests(unittest.TestCase):
    def test_default_pulse_is_byte_identical_with_no_new_agent_runs(self):
        base = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        explicit_none = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                                  data_dir=None, adapters=None)
        self.assertEqual(base, explicit_none)               # every field, byte for byte
        self.assertIsInstance(base, PulseResult)
        # The bundled fixtures trigger NONE of the conditional gates: agent_runs stays
        # the original five, and no macro / evidence finding, signal, or gap appears.
        self.assertEqual(len(base.agent_runs), 5)
        self.assertEqual(
            [a.agent_id for a in base.agent_runs],
            ["tattva.market_regime", "tattva.sector_rotation", "tattva.theme_rotation",
             "tattva.news_filings", "tattva.narrative"])
        new_disciplines = {"macro_regime", "customer_evidence", "supplier_evidence",
                           "bottleneck_evidence", "leadership_evidence"}
        self.assertFalse(any(f.discipline in new_disciplines for f in base.findings))
        self.assertFalse(any(s.discipline in new_disciplines for s in base.signals))
        self.assertFalse(any("macro" in g.lower() for g in base.data_gaps))
        self.assertEqual(base.adapter_results, ())

    def test_default_pulse_is_deterministic_run_to_run(self):
        a = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        b = run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        self.assertEqual(a, b)


# --------------------------------------------------------------------------- #
# 7. Guardrails: offline; AST-clean; no scheduler / broker / score / wall-clock  #
# --------------------------------------------------------------------------- #
class GuardrailTests(unittest.TestCase):
    _NEW_FILES = (
        os.path.join(_SRC, "sensors", "macro_regime.py"),
        os.path.join(_SRC, "sensors", "company_evidence.py"),
        os.path.join(_SRC, "adapters", "local_macro_data.py"),
    )
    _BANNED_IMPORT_ROOTS = (
        "socket", "requests", "urllib", "http", "sched", "schedule", "apscheduler",
        "crontab", "asyncio", "threading", "multiprocessing", "subprocess", "smtplib",
        "ftplib", "socketserver", "telnetlib", "websocket", "websockets", "aiohttp",
        "httpx", "broker", "signal",
    )

    def test_no_network_scheduler_or_broker_import(self):
        for path in self._NEW_FILES:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                for name in names:
                    for banned in self._BANNED_IMPORT_ROOTS:
                        self.assertFalse(
                            name == banned or name.startswith(banned + "."),
                            "banned import {0!r} in {1}".format(name, path))

    def test_no_score_rank_or_rating_function_defs(self):
        for path in self._NEW_FILES:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                     "banned fn name {0!r} in {1}".format(node.name, path))

    def test_no_scheduler_loop_or_wall_clock_construct(self):
        for path in self._NEW_FILES:
            low = _read(path).lower()
            for token in ("while true", "run_forever", "serve_forever", "start_polling",
                          "schedule.every", "set_interval", "datetime.now(", "utcnow(",
                          "time.time("):
                self.assertNotIn(token, low,
                                 "forbidden construct {0!r} in {1}".format(token, path))

    def test_offline_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*a, **k):
            raise AssertionError("network blocked: 014F must be fully offline")

        socket.socket.connect = _block
        try:
            macro_events, macro_result = LocalMacroDataAdapter(
                _TIGHTENING_DIR).fetch_checked(now=_NOW)
            self.assertEqual(macro_result.status, "success")
            self.assertTrue(MacroRegimeAgent().run_checked(None, macro_events))
            evidence = _evidence_events()
            for factory in (CustomerEvidenceAgent, SupplierEvidenceAgent,
                            BottleneckEvidenceAgent, LeadershipEvidenceAgent):
                self.assertTrue(factory().run_checked(None, evidence))
            r = run_pulse(_WATCHLIST, _THEMES, now=_NOW,
                          adapters=(CompanyDocumentsAdapter(_EVIDENCE_DIR),
                                    LocalMacroDataAdapter(_TIGHTENING_DIR)))
            self.assertTrue(any(f.discipline == "macro_regime" for f in r.findings))
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)          # default path offline too
        finally:
            socket.socket.connect = orig

    def test_no_secret_shaped_content_in_results(self):
        _, result = LocalMacroDataAdapter(_TIGHTENING_DIR).fetch_checked(now=_NOW)
        blob = " ".join(result.warnings + result.errors + result.data_gaps).lower()
        for bad in ("api_key", "apikey", "password", "secret_key"):
            self.assertNotIn(bad, blob)


if __name__ == "__main__":
    unittest.main()
