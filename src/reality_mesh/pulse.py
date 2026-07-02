"""The manual, on-demand pulse orchestrator for the Reality Mesh (IMPLEMENTATION-012K).

The capstone of Phase 012. :func:`run_pulse` runs ONE manual pulse end to end, entirely OFFLINE
and FIXTURE-backed: it loads bundled :class:`~reality_mesh.models.RealityEvent`s, runs the five
concrete Tattva sensor agents (market regime, sector rotation, theme rotation, news/filings,
X/social narrative) through their boundary-enforcing ``run_checked`` wrapper, routes each finding
through the :class:`~reality_mesh.router.BuddhiRouter`, FUSES the findings into
:class:`~reality_mesh.models.RealitySignal`s / :class:`~reality_mesh.models.SignalCluster`s via the
:class:`~reality_mesh.fusion.TattvaSignalFusionSynthesizer`, synthesizes
:class:`~reality_mesh.models.ThemePulse`s via the
:class:`~reality_mesh.sphurana.ThemePulseSynthesizer`, and rolls up a Data-Quality summary.

MANUAL / ON-DEMAND ONLY. A human runs one pulse. There is NO scheduler, NO daemon, NO background
job, NO streaming, and NO always-on loop anywhere in this module. There is NO live X and NO
network: events come only from local JSON fixtures. There is NO broker, NO order, and no
buy/sell/order affordance -- the mesh emits qualitative LABELS only, never a score / rank / trade.

HONEST GAPS, NEVER A SILENT DEMO. A requested watchlist ticker or theme with no fixture coverage
becomes an EXPLICIT data gap (recorded in :attr:`PulseResult.data_gaps`), never a fabricated value
and never a silent fall-back to the demo universe. Missing / stale inputs stay visible; weak
X/social stays weak (rumor, never verified).

Deterministic, stdlib-only, Python 3.9. No network on import; ``now`` is an injected string (no
wall-clock in any id / replay path); every collection is sorted before it is returned.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .fusion import TattvaSignalFusionSynthesizer
from .models import (
    AgentFinding,
    HandoffEnvelope,
    RealityEvent,
    RealitySignal,
    SignalCluster,
    ThemePulse,
)
from .registry import build_default_registry
from .router import BuddhiRouter
from .sensors import (
    MarketRegimeAgent,
    NewsFilingsAgent,
    SectorRotationAgent,
    SocialNarrativeAgent,
    ThemeRotationAgent,
    events_from_fixture,
)
from .sphurana import ThemePulseSynthesizer

# The bundled pulse fixture directory: <repo>/tests/fixtures/reality_mesh/pulse/. Resolved
# relative to this module (src/reality_mesh/pulse.py -> repo root is three levels up) so it works
# regardless of the current working directory. OFFLINE JSON only -- never a network endpoint.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PULSE_FIXTURE_DIR = os.path.join(
    _REPO_ROOT, "tests", "fixtures", "reality_mesh", "pulse")

# The five concrete sensor agents this pulse runs (order-stable). Each is FIXTURE/MOCK only and
# filters the shared event stream to its own discipline inside ``run``.
_SENSOR_AGENT_FACTORIES = (
    MarketRegimeAgent,
    SectorRotationAgent,
    ThemeRotationAgent,
    NewsFilingsAgent,
    SocialNarrativeAgent,
)


def _norm_theme(text: str) -> str:
    """Normalise a theme token for coverage comparison (case / hyphen / underscore insensitive)."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


# --------------------------------------------------------------------------- #
# Per-agent run status (label-only; NO score / rank / trade field)             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PulseAgentRun:
    """The status of one sensor agent within a pulse. Counts + a status label -- no numbers/scores.

    ``status`` is a plain label: ``"ok"`` (produced >= 1 finding), ``"no_findings"`` (saw events
    in its discipline but read nothing actionable), or ``"no_matching_events"`` (no fixture events
    in its discipline -- an honest coverage gap, never a fabricated finding).
    """

    agent_id: str = ""
    agent_name: str = ""
    discipline: str = ""
    events_seen: int = 0
    findings: int = 0
    status: str = ""
    finding_ids: Tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# PulseResult -- the frozen output bundle of one manual pulse                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PulseResult:
    """Everything one manual pulse produced -- frozen, deterministic, evidence-preserving.

    Carries the produced :attr:`signals` / :attr:`clusters` / :attr:`theme_pulses`, the per-agent
    :attr:`agent_runs` status, the fusion :attr:`authority_by_signal` sidecar (a signal has no
    authority field, so authority is summarised here -- proving ``rumor stays rumor``), and the
    consolidated :attr:`data_gaps` (fusion/sphurana gaps PLUS explicit coverage gaps for requested
    watchlist tickers / themes with no fixture coverage). No score / rank / trade field anywhere.
    """

    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    now: str = ""
    fixture_dir: str = ""
    events_loaded: int = 0
    findings: Tuple[AgentFinding, ...] = field(default_factory=tuple)
    signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    clusters: Tuple[SignalCluster, ...] = field(default_factory=tuple)
    theme_pulses: Tuple[ThemePulse, ...] = field(default_factory=tuple)
    agent_runs: Tuple[PulseAgentRun, ...] = field(default_factory=tuple)
    authority_by_signal: Dict[str, str] = field(default_factory=dict)
    freshness_by_signal: Dict[str, str] = field(default_factory=dict)
    corroboration_by_signal: Dict[str, str] = field(default_factory=dict)
    covered_companies: Tuple[str, ...] = field(default_factory=tuple)
    covered_themes: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    handoff_envelopes: Tuple[HandoffEnvelope, ...] = field(default_factory=tuple)
    fusion_envelope: Optional[HandoffEnvelope] = None
    sphurana_envelope: Optional[HandoffEnvelope] = None


# --------------------------------------------------------------------------- #
# Fixture loading (OFFLINE JSON only)                                           #
# --------------------------------------------------------------------------- #
def _load_pulse_events(fixture_dir: str) -> Tuple[RealityEvent, ...]:
    """Load every ``*.json`` fixture in ``fixture_dir`` into a sorted tuple of RealityEvents.

    Reads the local filesystem only -- no network, no scheduler. Files are read in sorted order and
    the resulting events are sorted by ``event_id`` so a pulse is byte-stable across machines.
    """
    if not os.path.isdir(fixture_dir):
        raise FileNotFoundError(
            "pulse fixture dir not found: {0} (no live fetch -- pulses are fixture-backed; pass "
            "--fixture-dir or create the bundled dir)".format(fixture_dir))
    events: List[RealityEvent] = []
    for name in sorted(os.listdir(fixture_dir)):
        if not name.endswith(".json"):
            continue
        events.extend(events_from_fixture(os.path.join(fixture_dir, name)))
    return tuple(sorted(events, key=lambda e: e.event_id))


# --------------------------------------------------------------------------- #
# The pulse                                                                     #
# --------------------------------------------------------------------------- #
def run_pulse(
    watchlist,
    themes,
    *,
    fixture_dir: Optional[str] = None,
    now: str = "",
) -> PulseResult:
    """Run ONE manual, on-demand pulse over the bundled fixtures. Deterministic + OFFLINE.

    ``watchlist`` and ``themes`` are REQUIRED and must be non-empty (like real mode requires a
    ticker): an empty watchlist or an empty theme list is rejected with ``ValueError`` and nothing
    is produced. Requested tickers / themes with no fixture coverage become explicit ``data_gaps``
    -- never fabricated, never a silent demo fall-back.

    The chain is: fixtures -> sensor agents (``run_checked``) -> Buddhi routing -> Tattva signal
    fusion -> Sphurana theme pulses -> Data-Quality roll-up. ``now`` is injected (no wall-clock).
    """
    watch = _normalise_watchlist(watchlist)
    theme_list = _normalise_themes(themes)
    if not watch:
        raise ValueError(
            "run_pulse requires a non-empty watchlist (empty --watchlist rejected; a manual pulse "
            "needs an explicit universe, nothing is produced)")
    if not theme_list:
        raise ValueError(
            "run_pulse requires a non-empty themes list (empty --themes rejected; a manual pulse "
            "needs explicit themes, nothing is produced)")

    fx_dir = fixture_dir or DEFAULT_PULSE_FIXTURE_DIR
    events = _load_pulse_events(fx_dir)

    # -- run the five sensor agents through their boundary-enforcing wrapper ----------------- #
    registry = build_default_registry()
    router = BuddhiRouter(registry=registry)

    all_findings: List[AgentFinding] = []
    agent_runs: List[PulseAgentRun] = []
    for factory in _SENSOR_AGENT_FACTORIES:
        agent = factory()
        desc = agent.descriptor
        discipline = desc.discipline
        seen = tuple(e for e in events if e.discipline == discipline)
        produced = agent.run_checked(None, events)  # each agent filters to its own discipline
        produced = tuple(sorted(produced, key=lambda f: f.finding_id))
        all_findings.extend(produced)
        status = ("ok" if produced else
                  ("no_findings" if seen else "no_matching_events"))
        agent_runs.append(PulseAgentRun(
            agent_id=desc.agent_id, agent_name=desc.agent_name, discipline=discipline,
            events_seen=len(seen), findings=len(produced), status=status,
            finding_ids=tuple(f.finding_id for f in produced)))

    all_findings.sort(key=lambda f: f.finding_id)
    findings = tuple(all_findings)

    # -- Buddhi routing: wrap every finding in a HandoffEnvelope (proves the routing step) --- #
    envelopes = tuple(router.route_finding(f, created_at=now) for f in findings)

    # -- Tattva signal fusion ---------------------------------------------------------------- #
    fusion = TattvaSignalFusionSynthesizer().fuse(events, findings, now=now)

    # -- Sphurana theme pulses --------------------------------------------------------------- #
    sphurana = ThemePulseSynthesizer().synthesize(
        fusion.clusters, fusion.signals, now=now)

    # -- Data-Quality roll-up: preserved gaps + explicit coverage gaps ----------------------- #
    covered_companies = tuple(sorted({c for e in events for c in e.affected_companies}))
    covered_theme_names = tuple(sorted({t for e in events for t in e.affected_themes}))
    covered_theme_norms = {_norm_theme(t) for t in covered_theme_names}

    data_gaps = _rollup_gaps(
        fusion.signals, fusion.clusters, sphurana.theme_pulses,
        watch, theme_list, set(covered_companies), covered_theme_norms)

    return PulseResult(
        watchlist=watch,
        themes=theme_list,
        now=now,
        fixture_dir=fx_dir,
        events_loaded=len(events),
        findings=findings,
        signals=fusion.signals,
        clusters=fusion.clusters,
        theme_pulses=sphurana.theme_pulses,
        agent_runs=tuple(agent_runs),
        authority_by_signal=dict(fusion.authority_by_signal),
        freshness_by_signal=dict(fusion.freshness_by_signal),
        corroboration_by_signal=dict(fusion.corroboration_by_signal),
        covered_companies=covered_companies,
        covered_themes=covered_theme_names,
        data_gaps=data_gaps,
        handoff_envelopes=envelopes,
        fusion_envelope=fusion.envelope,
        sphurana_envelope=sphurana.envelope,
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _normalise_watchlist(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens. Empty -> ()."""
    if watchlist is None:
        return ()
    if isinstance(watchlist, str):
        raw = watchlist.split(",")
    else:
        raw = list(watchlist)
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _normalise_themes(themes) -> Tuple[str, ...]:
    """Strip / lower / dedupe (first-seen order); reject blank tokens. Empty -> ()."""
    if themes is None:
        return ()
    if isinstance(themes, str):
        raw = themes.split(",")
    else:
        raw = list(themes)
    out: List[str] = []
    for token in raw:
        th = str(token).strip().lower()
        if th and th not in out:
            out.append(th)
    return tuple(out)


def _rollup_gaps(signals, clusters, theme_pulses, watch, theme_list,
                 covered_companies, covered_theme_norms) -> Tuple[str, ...]:
    """Consolidate preserved gaps + explicit coverage gaps (deterministic, deduped, sorted-ish)."""
    gaps: List[str] = []
    for obj in list(signals) + list(clusters) + list(theme_pulses):
        gaps.extend(getattr(obj, "data_gaps", ()) or ())
    # Explicit coverage gaps -- a requested ticker / theme with no fixture coverage is NEVER
    # silently dropped or fabricated; it is surfaced as an honest gap.
    for ticker in watch:
        if ticker not in covered_companies:
            gaps.append(
                "no fixture coverage for watchlist ticker {0} in this pulse -- honest gap, not "
                "fabricated (a real source would be required)".format(ticker))
    for theme in theme_list:
        if _norm_theme(theme) not in covered_theme_norms:
            gaps.append(
                "no fixture coverage for theme '{0}' in this pulse -- honest gap, not fabricated "
                "(no signals; requires a real source)".format(theme))
    # Order-stable de-dup, then a stable sort so the summary is byte-identical run to run.
    return tuple(sorted(dict.fromkeys(gaps)))
