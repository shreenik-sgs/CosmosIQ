"""The deterministic ReplayHarness for the Reality Mesh (IMPLEMENTATION-013C).

The replay capability specified in ``PERSISTENCE_REPLAY_CONTRACT_013.md`` §3/§4 and
``RUNTIME_CONTRACT_013.md`` (:class:`~reality_mesh.runtime.ReplayRequest` /
:class:`~reality_mesh.runtime.ReplayResult`). A :class:`ReplayHarness` READS the append-only
013B stores and RE-COMPUTES synthesis deterministically, then COMPARES the recomputed outputs
against the persisted ones. It answers, from stored records alone, "why did the system say X?"
and -- crucially -- proves the answer is reproducible:

    same inputs + same schema + same code version  =>  same outputs  (deterministic_match=True)

HARD DISCIPLINE (PERSISTENCE_REPLAY_CONTRACT_013 §4):

* **Reads, never mutates.** Replay only ``query`` / ``read_all`` on the stores; it NEVER appends,
  updates, or deletes. Stored bytes are byte-unchanged after any replay. History is corrected only
  by a NEW correction record (013B :class:`~reality_mesh.stores.AuditStore`), never on a replay.
* **Recompute, never rubber-stamp.** The recomputed signals / pulses are compared FIELD-BY-FIELD
  against the persisted records. A divergence (non-determinism leaked in, or tampered history) is
  surfaced in :attr:`~reality_mesh.runtime.ReplayResult.differences` with
  ``deterministic_match=False`` -- a replay that cannot reproduce identical outputs is a FAILURE,
  never a silent pass.
* **Evidence preserved end to end.** Conflicts, data gaps, source / evidence refs, and (on any
  reconstructed :class:`~reality_mesh.models.HandoffEnvelope`) forbidden downstream uses flow
  through the recompute unchanged -- nothing is averaged, dropped, or upgraded on replay.
* **No decision affordance.** No scheduler / daemon / streaming / broker / network / order / score
  / rank is reachable from here. Replay is a read-and-verify, not a run loop.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no broker, no wall-clock: ids are
content-derived and ``now`` is an injected string (the run's own persisted ``started_at`` is
re-injected so a reconstructed envelope is byte-stable).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields as _dc_fields
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
from .pulse import PulseResult, _load_pulse_events
from .runtime import PulseRun, ReplayRequest, ReplayResult
from .sphurana import ThemePulseSynthesizer
from .stores import (
    SCHEMA_VERSION,
    EventStore,
    FindingStore,
    RunStore,
    SignalStore,
    ThemePulseStore,
)

__all__ = [
    "ReplayHarness",
    "ReplayReconstruction",
]


def _norm_theme(text) -> str:
    """Case / hyphen / underscore-insensitive theme token (mirrors the stores + pulse matcher)."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _has_ticker(values, ticker: str) -> bool:
    want = str(ticker).strip().upper()
    return any(str(v).strip().upper() == want for v in (values or ()))


def _has_theme(values, theme: str) -> bool:
    want = _norm_theme(theme)
    return any(_norm_theme(v) == want for v in (values or ()))


# --------------------------------------------------------------------------- #
# ReplayReconstruction -- the full recompute detail (envelopes + typed objects) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayReconstruction:
    """Everything a replay RE-COMPUTED, plus the persisted records it was compared against.

    :class:`~reality_mesh.runtime.ReplayResult` is the frozen contract summary; this is the
    richer detail (recomputed envelopes with their preserved ``forbidden_downstream_uses``, the
    scoped events / findings that were read, and the persisted signals / pulses used for the
    field-by-field comparison) so a caller can inspect the whole reconstruction, not just counts.
    """

    run_ids: Tuple[str, ...] = field(default_factory=tuple)
    events: Tuple[RealityEvent, ...] = field(default_factory=tuple)
    findings: Tuple[AgentFinding, ...] = field(default_factory=tuple)
    signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    clusters: Tuple[SignalCluster, ...] = field(default_factory=tuple)
    theme_pulses: Tuple[ThemePulse, ...] = field(default_factory=tuple)
    fusion_envelopes: Tuple[HandoffEnvelope, ...] = field(default_factory=tuple)
    sphurana_envelopes: Tuple[HandoffEnvelope, ...] = field(default_factory=tuple)
    persisted_signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    persisted_theme_pulses: Tuple[ThemePulse, ...] = field(default_factory=tuple)
    differences: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def deterministic_match(self) -> bool:
        """True iff the recompute reproduced every persisted output (no field-level divergence)."""
        return bool(self.run_ids) and not self.differences


# --------------------------------------------------------------------------- #
# ReplayHarness                                                                #
# --------------------------------------------------------------------------- #
class ReplayHarness:
    """Read the 013B stores + re-compute synthesis deterministically + verify against persistence.

    Constructed with the five stores a run touches. Stateless across calls (holds only the store
    handles); every :meth:`replay` reads, never writes. The recompute reuses the SAME
    :class:`~reality_mesh.fusion.TattvaSignalFusionSynthesizer` and
    :class:`~reality_mesh.sphurana.ThemePulseSynthesizer` the live pulse used, so identical
    inputs + schema + code reproduce identical outputs.
    """

    def __init__(
        self,
        event_store: EventStore,
        finding_store: FindingStore,
        signal_store: SignalStore,
        theme_pulse_store: ThemePulseStore,
        run_store: RunStore,
    ) -> None:
        self.event_store = event_store
        self.finding_store = finding_store
        self.signal_store = signal_store
        self.theme_pulse_store = theme_pulse_store
        self.run_store = run_store

    # -- persistence convenience (persist a run_pulse output, then replay it) --- #
    def persist_pulse(
        self,
        pulse_result: PulseResult,
        *,
        run_id: str,
        now: str = "",
        mode: str = "pulse",
        runtime_version: str = "013C",
    ) -> PulseRun:
        """Persist ONE :func:`~reality_mesh.pulse.run_pulse` output into the stores; return the run.

        Writes the spine :class:`~reality_mesh.runtime.PulseRun` (RunStore), the run's input
        events (re-loaded from the SAME offline fixtures the pulse read, via
        ``pulse_result.fixture_dir``), and its findings / signals / theme pulses. Deterministic:
        ``run_id`` is caller-supplied and every timestamp is the pulse's injected ``now`` (no
        wall-clock). Append-only -- this is the only writer; :meth:`replay` never writes.
        """
        if not str(run_id).strip():
            raise ValueError("persist_pulse requires a non-empty run_id")
        run_now = now or pulse_result.now
        # PROD-LIVE-4: persist the pulse's ACTUAL merged events -- the fixtures-after-adapter-
        # replacement + REAL adapter events (or, under suppression, the real adapter events only)
        # that the pulse ran over. A LIVE run therefore writes its real ``sec:accession/...`` /
        # ``fmp:...`` events to the event_store, so the findings' cited event ids resolve there
        # (provenance holds). Fall back to re-loading the offline fixtures only for a legacy
        # PulseResult that carries no ``events`` (back-compat); the default fixture pulse now
        # carries events == the same loaded fixtures, so the persisted bytes are unchanged.
        pulse_events = tuple(getattr(pulse_result, "events", ()) or ())
        if pulse_events:
            events = pulse_events
        elif pulse_result.fixture_dir:
            events = _load_pulse_events(pulse_result.fixture_dir)
        else:
            events = ()

        run = PulseRun(
            run_id=run_id,
            started_at=run_now,
            completed_at=run_now,
            mode=mode,
            trigger_type="manual",
            watchlist=tuple(pulse_result.watchlist),
            themes=tuple(pulse_result.themes),
            events_created=len(events),
            findings_created=len(pulse_result.findings),
            signals_created=len(pulse_result.signals),
            theme_pulses_created=len(pulse_result.theme_pulses),
            schema_version=SCHEMA_VERSION,
            runtime_version=runtime_version,
        )
        self.run_store.append(run)
        for event in events:
            self.event_store.append(event, run_id=run_id)
        for finding in pulse_result.findings:
            self.finding_store.append(finding, run_id=run_id)
        for signal in pulse_result.signals:
            self.signal_store.append(signal, run_id=run_id)
        for pulse in pulse_result.theme_pulses:
            self.theme_pulse_store.append(pulse, run_id=run_id)
        return run

    # -- replay ---------------------------------------------------------------- #
    def replay(self, request: ReplayRequest, *, now: str = "") -> ReplayResult:
        """Reconstruct + verify a past run; return a :class:`~reality_mesh.runtime.ReplayResult`.

        Resolves the run(s) in scope, reads the persisted events + findings, RE-COMPUTES signals
        (fusion) and pulses (sphurana) with the run's own injected ``now``, and COMPARES the
        recompute field-by-field against the persisted SignalStore / ThemePulseStore records.
        ``deterministic_match`` is True iff nothing diverged; every divergence is named in
        ``differences``. Reads only -- no store is mutated.
        """
        rec = self.reconstruct(request, now=now)

        outputs = tuple(sorted(
            [s.signal_id for s in rec.signals]
            + [c.cluster_id for c in rec.clusters]
            + [p.theme_pulse_id for p in rec.theme_pulses]
            + [e.envelope_id for e in rec.fusion_envelopes if e is not None]
            + [e.envelope_id for e in rec.sphurana_envelopes if e is not None]))

        if rec.run_ids:
            source_run_id = rec.run_ids[0] if len(rec.run_ids) == 1 else ",".join(rec.run_ids)
        else:
            source_run_id = request.run_id.strip() or "unresolved-scope"

        token = "|".join(rec.run_ids) + "||" + "|".join(outputs) + "||" + now
        replay_id = "replay.{0}".format(hashlib.md5(token.encode("utf-8")).hexdigest()[:12])

        return ReplayResult(
            replay_id=replay_id,
            source_run_id=source_run_id,
            events_replayed=len(rec.events),
            findings_replayed=len(rec.findings),
            signals_replayed=len(rec.signals),
            outputs_reconstructed=outputs,
            differences=rec.differences,
            deterministic_match=rec.deterministic_match,
        )

    def reconstruct(self, request: ReplayRequest, *, now: str = "") -> ReplayReconstruction:
        """The full recompute detail behind :meth:`replay` (recomputed objects + envelopes + diff).

        Public so a caller can inspect the reconstructed envelopes (and their preserved
        ``forbidden_downstream_uses``), the scoped events / findings, and the persisted records
        the recompute was compared against -- not just the summary counts.
        """
        run_ids = self._resolve_runs(request)

        events: List[RealityEvent] = []
        findings: List[AgentFinding] = []
        signals: List[RealitySignal] = []
        clusters: List[SignalCluster] = []
        pulses: List[ThemePulse] = []
        fusion_envelopes: List[HandoffEnvelope] = []
        sphurana_envelopes: List[HandoffEnvelope] = []
        persisted_signals: List[RealitySignal] = []
        persisted_pulses: List[ThemePulse] = []
        differences: List[str] = []

        for run_id in run_ids:
            run = self._get_run(run_id)
            run_now = run.started_at if run is not None else now

            run_events = self._read_events(run_id, request)
            run_findings = self._read_findings(run_id, request)

            fusion = TattvaSignalFusionSynthesizer().fuse(
                tuple(run_events), tuple(run_findings), now=run_now)
            sphurana = ThemePulseSynthesizer().synthesize(
                fusion.clusters, fusion.signals, now=run_now)

            run_persisted_signals = list(self.signal_store.query(run_id=run_id))
            run_persisted_pulses = list(self.theme_pulse_store.query(run_id=run_id))

            differences.extend(self._compare(
                fusion.signals, run_persisted_signals, "signal", "signal_id", run_id))
            differences.extend(self._compare(
                sphurana.theme_pulses, run_persisted_pulses, "theme_pulse",
                "theme_pulse_id", run_id))

            events.extend(run_events)
            findings.extend(run_findings)
            signals.extend(fusion.signals)
            clusters.extend(fusion.clusters)
            pulses.extend(sphurana.theme_pulses)
            if fusion.envelope is not None:
                fusion_envelopes.append(fusion.envelope)
            if sphurana.envelope is not None:
                sphurana_envelopes.append(sphurana.envelope)
            persisted_signals.extend(run_persisted_signals)
            persisted_pulses.extend(run_persisted_pulses)

        if not run_ids:
            differences.append(
                "no persisted run matched the replay scope (run_id={0!r} ticker={1!r} "
                "theme={2!r} time_window={3!r}) -- nothing to reconstruct".format(
                    request.run_id, request.ticker, request.theme, request.time_window))

        return ReplayReconstruction(
            run_ids=run_ids,
            events=tuple(events),
            findings=tuple(findings),
            signals=tuple(signals),
            clusters=tuple(clusters),
            theme_pulses=tuple(pulses),
            fusion_envelopes=tuple(fusion_envelopes),
            sphurana_envelopes=tuple(sphurana_envelopes),
            persisted_signals=tuple(persisted_signals),
            persisted_theme_pulses=tuple(persisted_pulses),
            differences=tuple(differences),
        )

    # -- scope resolution ------------------------------------------------------ #
    def _resolve_runs(self, request: ReplayRequest) -> Tuple[str, ...]:
        """The run_id(s) in scope: an explicit ``run_id`` else a RunStore query by axes."""
        if request.run_id.strip():
            rid = request.run_id.strip()
            return (rid,) if self._get_run(rid) is not None else ()
        filters: Dict[str, object] = {}
        if request.ticker.strip():
            filters["ticker"] = request.ticker
        if request.theme.strip():
            filters["theme"] = request.theme
        if request.time_window:
            filters["time_window"] = tuple(request.time_window)
        runs = self.run_store.query(**filters) if filters else ()
        return tuple(sorted({r.run_id for r in runs}))

    def _get_run(self, run_id: str) -> Optional[PulseRun]:
        for run in self.run_store.query(run_id=run_id):
            return run
        return None

    def _read_events(self, run_id: str, request: ReplayRequest) -> List[RealityEvent]:
        """The run's persisted events, narrowed by ticker / theme / window / source scope."""
        events = list(self.event_store.query(run_id=run_id))
        if request.ticker.strip():
            events = [e for e in events if _has_ticker(e.affected_companies, request.ticker)]
        if request.theme.strip():
            events = [e for e in events if _has_theme(e.affected_themes, request.theme)]
        if request.time_window:
            lo, hi = request.time_window[0], request.time_window[-1]
            events = [e for e in events if lo <= e.timestamp <= hi]
        if request.source_filter:
            allowed = set(request.source_filter)
            events = [e for e in events if e.source_id in allowed]
        return sorted(events, key=lambda e: e.event_id)

    def _read_findings(self, run_id: str, request: ReplayRequest) -> List[AgentFinding]:
        """The run's persisted findings, narrowed by ticker / theme / agent scope."""
        findings = list(self.finding_store.query(run_id=run_id))
        if request.ticker.strip():
            findings = [f for f in findings if _has_ticker(f.affected_companies, request.ticker)]
        if request.theme.strip():
            findings = [f for f in findings if _has_theme(f.affected_themes, request.theme)]
        if request.agent_filter:
            allowed = set(request.agent_filter)
            findings = [f for f in findings if f.agent_id in allowed]
        return sorted(findings, key=lambda f: f.finding_id)

    # -- comparison (verify, never rubber-stamp) ------------------------------- #
    @staticmethod
    def _compare(recomputed, persisted, kind: str, id_field: str, run_id: str) -> List[str]:
        """Field-by-field divergence of each recomputed object vs its persisted counterpart.

        Matches by stable id. A recomputed output absent from the store, or a field that differs,
        is a named divergence. (Persisted outputs outside the recompute scope are not divergences
        -- a narrowed replay legitimately reconstructs a subset.)
        """
        by_id = {getattr(p, id_field): p for p in persisted}
        diffs: List[str] = []
        for obj in recomputed:
            oid = getattr(obj, id_field)
            match = by_id.get(oid)
            if match is None:
                diffs.append(
                    "run {0}: {1} {2!r} reconstructed but absent from the persisted store".format(
                        run_id, kind, oid))
                continue
            if obj == match:
                continue
            for f in _dc_fields(obj):
                recomputed_value = getattr(obj, f.name)
                persisted_value = getattr(match, f.name)
                if recomputed_value != persisted_value:
                    diffs.append(
                        "run {0}: {1} {2!r} field {3!r} diverged -- persisted={4!r} "
                        "recomputed={5!r}".format(
                            run_id, kind, oid, f.name, persisted_value, recomputed_value))
        return diffs
