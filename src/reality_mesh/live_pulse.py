"""A thin, credential-gated wiring helper for a REAL LIVE pulse (PROD-LIVE-1).

This module turns the hand-run "shadow live" snippet (``reports/
REAL_SHADOW_RUN_OPERATOR_GUIDE_021D.md``) into a first-class, sanctioned operator action: it
COMPOSES the already-accepted live source adapters (020B :class:`~reality_mesh.adapters.
sec_edgar_live.SecEdgarLiveAdapter`, 021A :class:`~reality_mesh.adapters.fmp_live.FmpLiveAdapter`)
with the frozen :func:`~reality_mesh.pulse.run_pulse` and :func:`~reality_mesh.pulse_persistence.
persist_and_summarize`, so real SEC filings / FMP financials flow into the cockpit store.

Nothing here is new machinery: it wires existing parts and reports honestly.

CREDENTIAL-GATED, HONEST GAPS, NEVER A FIXTURE FALLBACK:

* the live adapter set is built from credential PRESENCE only -- the SEC adapter joins ONLY when
  ``SEC_USER_AGENT`` is set, the FMP adapter ONLY when ``FMP_API_KEY`` is set;
* BOTH credentials missing -> an HONEST result (``sources_configured=()`` + a clear note) that
  persists NO run and fabricates NOTHING -- never a fixture / demo fallback;
* a live-fetch FAILURE (429 / timeout / parse error) rides through the adapter as a VISIBLE source
  gap; other sources continue; never backfilled from fixtures.

SECRETS ARE PRESENCE-ONLY. A credential is read as ``name in env`` and NOTHING else: the VALUE is
never read, stored, logged, echoed, or rendered. The presence flag is passed to the adapter
(``transport=None`` -> the adapter builds the real transport lazily from the env itself).

AUTHORITY LADDER PRESERVED. SEC is canonical, FMP is convenience -- assigned per record by the
adapters and never re-ranked here; a contradiction is preserved to Data Quality downstream.

SHADOW-MARKED, RECORD-ONLY. A live pulse is a sanctioned operator REFRESH (like the manual-pulse
form): it records evidence into the store. It is NOT production 24x7, and there is NO broker /
order / trade affordance anywhere.

NO NETWORK ON IMPORT. This module imports no network library at top level and the adapters build
their real transports lazily; the whole test suite runs OFFLINE by injecting mock ``adapters`` and
the real network path is never exercised. Deterministic where it matters: ``now`` and ``run_id``
are injected; only the live payload itself varies.

Stdlib-only, Python 3.9, OFFLINE tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Tuple

from .adapters.fmp_live import FmpLiveAdapter
from .adapters.sec_edgar_live import SecEdgarLiveAdapter
from .pulse import PulseResult, run_pulse
from .pulse_persistence import persist_and_summarize

__all__ = [
    "SEC_LIVE_ENV_VAR",
    "FMP_LIVE_ENV_VAR",
    "NO_LIVE_SOURCES_NOTE",
    "LiveSourceHealth",
    "LivePulseResult",
    "build_live_adapters",
    "run_live_pulse",
]

#: The env var NAMES that gate each live source. NAMES only -- a value is never read here.
SEC_LIVE_ENV_VAR = "SEC_USER_AGENT"
FMP_LIVE_ENV_VAR = "FMP_API_KEY"

#: The honest message rendered / returned when neither live credential is configured.
NO_LIVE_SOURCES_NOTE = (
    "No live sources configured: set {0} (free) and/or {1}, then refresh. Nothing was fetched, "
    "nothing was fabricated, and there is no fixture/demo fallback.".format(
        SEC_LIVE_ENV_VAR, FMP_LIVE_ENV_VAR))


# --------------------------------------------------------------------------- #
# Presence-only env access (never reads a value)                                #
# --------------------------------------------------------------------------- #
def _resolve_env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    """Return the mapping presence is read from (``os.environ`` when ``env`` is None).

    A non-mapping ``env`` is REFUSED without being echoed -- it might BE a secret value passed by
    mistake. ``os`` is imported lazily so importing this module touches no environment.
    """
    if env is None:
        import os  # lazy; NOT a network import
        return os.environ
    if not isinstance(env, Mapping):
        # NEVER echo the argument -- it may be a credential value.
        raise ValueError(
            "run_live_pulse/build_live_adapters env must be a Mapping of NAME->value (presence "
            "is read via `name in env`; the value is never touched) -- the argument was rejected "
            "and has not been stored or echoed")
    return env


def build_live_adapters(*, env: Optional[Mapping[str, str]] = None):
    """Build the live adapter set from credential PRESENCE. Returns ``(adapters, config_notes)``.

    Reads ``SEC_USER_AGENT`` / ``FMP_API_KEY`` PRESENCE from ``env`` (``os.environ`` when None)
    via membership ONLY -- the value is never read or echoed. For each PRESENT credential the
    matching adapter is constructed with ``transport=None`` (so it builds its real transport
    lazily from the env at fetch time) and its presence flag set True. ``config_notes`` carries an
    honest one-line status per source ("SEC live: configured" / "SEC live: not configured
    (SEC_USER_AGENT missing)", same for FMP). Neither source configured -> ``()`` adapters + two
    "not configured" notes.
    """
    mapping = _resolve_env(env)
    sec_present = SEC_LIVE_ENV_VAR in mapping        # membership ONLY -- value never read
    fmp_present = FMP_LIVE_ENV_VAR in mapping        # membership ONLY -- value never read

    adapters: List = []
    notes: List[str] = []
    if sec_present:
        adapters.append(SecEdgarLiveAdapter(
            transport=None, sec_user_agent_present=True))
        notes.append("SEC live: configured")
    else:
        notes.append(
            "SEC live: not configured ({0} missing)".format(SEC_LIVE_ENV_VAR))
    if fmp_present:
        adapters.append(FmpLiveAdapter(
            transport=None, fmp_api_key_present=True))
        notes.append("FMP live: configured")
    else:
        notes.append(
            "FMP live: not configured ({0} missing)".format(FMP_LIVE_ENV_VAR))
    return tuple(adapters), tuple(notes)


# --------------------------------------------------------------------------- #
# The honest live-pulse result (labels + counts; NO secret value, NO trade field) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LiveSourceHealth:
    """One live source's honest health after a refresh -- LABELS + counts only, never a value.

    ``authority`` is the source's tier (``canonical`` for SEC, ``convenience`` for FMP -- preserved
    from the adapter, never re-ranked). ``health`` / ``credentials_status`` / ``rate_limit_status``
    are the closed adapter labels (a credential VALUE never appears here). ``status`` is the
    adapter run status; ``events_created`` a volume count; ``data_gaps`` the visible gaps.
    """

    adapter_id: str = ""
    source_name: str = ""
    authority: str = ""
    status: str = ""
    health: str = ""
    credentials_status: str = ""
    rate_limit_status: str = ""
    events_created: int = 0
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LivePulseResult:
    """Everything one sanctioned LIVE refresh produced -- honest, shadow-marked, secret-free.

    A live pulse is a record-only operator refresh: ``shadow`` is always True (never production
    24x7) and there is NO trade / order / broker field anywhere. When neither credential is
    configured, ``configured`` is False, ``sources_configured`` is empty, ``persisted`` is False
    (NO run fabricated), and ``config_notes`` / ``data_gaps`` carry the honest reason. No field
    ever holds a credential value.
    """

    watchlist: Tuple[str, ...] = field(default_factory=tuple)
    themes: Tuple[str, ...] = field(default_factory=tuple)
    now: str = ""
    run_id: str = ""
    configured: bool = False
    persisted: bool = False
    shadow: bool = True
    sources_configured: Tuple[str, ...] = field(default_factory=tuple)
    config_notes: Tuple[str, ...] = field(default_factory=tuple)
    source_health: Tuple[LiveSourceHealth, ...] = field(default_factory=tuple)
    events_loaded: int = 0
    findings: int = 0
    signals: int = 0
    theme_pulses: int = 0
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    replay_deterministic_match: Optional[bool] = None
    pulse_result: Optional[PulseResult] = None

    def summary_line(self) -> str:
        """A one-line honest summary (labels only -- safe to print / log; no value)."""
        if not self.configured:
            return NO_LIVE_SOURCES_NOTE
        srcs = ", ".join(self.sources_configured) or "none"
        return ("live refresh (shadow) · sources: {0} · events {1} · findings {2} · "
                "signals {3} · gaps {4}".format(
                    srcs, self.events_loaded, self.findings, self.signals,
                    len(self.data_gaps)))


def _default_run_id(watch: Tuple[str, ...], themes: Tuple[str, ...], now: str) -> str:
    """A deterministic run id derived from the scope + injected instant (never a wall clock)."""
    import hashlib  # lazy; stdlib
    digest = hashlib.md5(
        ("|".join(watch) + "||" + "|".join(themes) + "||" + str(now)).encode(
            "utf-8")).hexdigest()[:12]
    return "live-{0}".format(digest)


def run_live_pulse(watchlist, themes, *, store_dir: str, now: str, run_id: str = "",
                   env: Optional[Mapping[str, str]] = None,
                   adapters=None) -> LivePulseResult:
    """Run ONE sanctioned, credential-gated LIVE pulse into ``store_dir``. Honest; shadow-marked.

    Builds the live adapters from credential PRESENCE (or uses injected ``adapters`` for OFFLINE
    tests with mock transports), runs :func:`~reality_mesh.pulse.run_pulse` with them, persists via
    :func:`~reality_mesh.pulse_persistence.persist_and_summarize`, and returns a
    :class:`LivePulseResult` summarising which sources were configured, per-source health, produced
    volumes, and the visible data gaps.

    BOTH credentials missing (and no injected ``adapters``) -> an HONEST empty result: NO run is
    persisted, NOTHING is fabricated, and no network is attempted (the adapters are never built).
    A live-fetch failure surfaces as a visible source gap (never a fixture fallback). The authority
    ladder (SEC canonical > FMP convenience) is preserved by the adapters, never re-ranked here.

    ``now`` is REQUIRED (injected; the wall clock is never read). ``run_id`` defaults to a
    deterministic id derived from the scope + ``now``. This is a REFRESH: it records evidence and
    has NO broker / order / trade affordance.
    """
    if not str(store_dir).strip():
        raise ValueError("run_live_pulse requires a non-empty store_dir")
    if not str(now).strip():
        raise ValueError(
            "run_live_pulse requires an injected 'now' instant (the wall clock is never read)")

    # Build (or accept injected) the live adapter set. Injected adapters take precedence so the
    # test suite drives real code paths with mock transports, fully offline.
    if adapters is not None:
        adapter_list = tuple(adapters)
        _, config_notes = build_live_adapters(env=env)
    else:
        adapter_list, config_notes = build_live_adapters(env=env)

    watch = _norm_watch(watchlist)
    theme_list = _norm_themes(themes)

    # -- BOTH sources missing: honest no-run. Nothing built, nothing fetched, nothing faked. --- #
    if not adapter_list:
        return LivePulseResult(
            watchlist=watch, themes=theme_list, now=now, run_id="",
            configured=False, persisted=False, shadow=True,
            sources_configured=(), config_notes=tuple(config_notes),
            source_health=(), data_gaps=(NO_LIVE_SOURCES_NOTE,),
            pulse_result=None)

    effective_run_id = str(run_id).strip() or _default_run_id(watch, theme_list, now)

    # -- run the pulse with the live adapters, then persist it into the cockpit store. ---------- #
    pulse = run_pulse(watch, theme_list, now=now, adapters=adapter_list)
    _pulse_run, replay_result, _panel = persist_and_summarize(
        pulse, store_dir=store_dir, run_id=effective_run_id, now=now)

    # -- per-source health, zipping each adapter's descriptor with its run result. -------------- #
    descriptors = {a.descriptor.adapter_id: a.descriptor for a in adapter_list}
    order = tuple(a.descriptor.adapter_id for a in adapter_list)
    results_by_id = {r.adapter_id: r for r in pulse.adapter_results}
    source_health: List[LiveSourceHealth] = []
    sources_configured: List[str] = []
    for adapter_id in order:
        desc = descriptors[adapter_id]
        sources_configured.append(desc.source_name)
        result = results_by_id.get(adapter_id)
        if result is None:
            continue
        source_health.append(LiveSourceHealth(
            adapter_id=adapter_id,
            source_name=desc.source_name,
            authority=desc.source_authority,
            status=result.status,
            health=result.source_health,
            credentials_status=result.credentials_status,
            rate_limit_status=result.rate_limit_status,
            events_created=result.events_created,
            data_gaps=tuple(result.data_gaps)))

    return LivePulseResult(
        watchlist=watch, themes=theme_list, now=now, run_id=effective_run_id,
        configured=True, persisted=True, shadow=True,
        sources_configured=tuple(sources_configured),
        config_notes=tuple(config_notes),
        source_health=tuple(source_health),
        events_loaded=pulse.events_loaded,
        findings=len(pulse.findings),
        signals=len(pulse.signals),
        theme_pulses=len(pulse.theme_pulses),
        data_gaps=tuple(pulse.data_gaps),
        replay_deterministic_match=replay_result.deterministic_match,
        pulse_result=pulse)


# --------------------------------------------------------------------------- #
# Small normalisers (mirror run_pulse's own strip/dedupe rules)                 #
# --------------------------------------------------------------------------- #
def _norm_watch(watchlist) -> Tuple[str, ...]:
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _norm_themes(themes) -> Tuple[str, ...]:
    raw = themes.split(",") if isinstance(themes, str) else list(themes or ())
    out: List[str] = []
    for token in raw:
        th = str(token).strip().lower()
        if th and th not in out:
            out.append(th)
    return tuple(out)
