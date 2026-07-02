"""On-demand REAL evidence terrain builder (IMPLEMENTATION-010D).

``build_real_evidence_terrain_for_ticker`` builds a sparse
:class:`~universe_ui.terrain.UniverseTerrain` (mode ``real_evidence_on_demand``) from
REAL, current source data (SEC / FMP / yfinance) for ONE requested ticker. It is gated
behind explicit on-demand execution ONLY -- it is never the default and never runs on
import.

Discipline:

* **No network on import.** This module never imports the network boundary at top
  level; ``evidence_ingestion.live_transport`` is imported LAZILY, inside the builder,
  and only when the caller did not inject its own transports. Importing this module is
  inert.
* **No secrets here.** Credentials are EXPLICIT arguments (``sec_user_agent`` /
  ``fmp_api_key``), resolved from env by the CLI, never read here. This module reads no
  environment variable. Missing credentials become a VISIBLE Data-Quality DATA GAP and a
  ``credentials_missing`` per-source status -- never a crash-with-leak, never a silent
  skip.
* **No new reasoning.** Every reasoning object comes from an EXISTING constructor
  (Genesis / Prometheus / Personal CIO / Kriya). Downstream stages are GATED on
  sufficient inputs: OpportunityHypothesis only if the ingested assessment carries
  signals; InvestmentThesis only if diligence inputs are supplied; PersonalizedAction
  only if a profile + portfolio are supplied; ManualExecutionIntent only if an explicit
  user-selected size is supplied. A skipped stage records an honest data gap; nothing is
  fabricated and no broker order is placed.
* **Deterministic where testable.** ``now`` is injectable, so a build with mock
  transports + a fixed ``now`` is byte-stable. The real CLI run stamps the actual clock
  (real mode may use the clock); demo / fixture modes stay clock-free.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Tuple

from evidence_ingestion.vertical_slice import run_fixture_ingestion_slice
from runtime.evidence_alpha_slice_runner import (
    EvidenceAlphaSliceResult,
    _downstream_provenance,
    _overridden_facts,
)

from eios_core.ids import stable_id
from genesis.opportunity_hypothesis import generate_opportunity_hypothesis
from prometheus.investment_thesis import generate_investment_thesis
from prometheus.investment_action import generate_investment_action
from personal_cio.personalized_action import generate_personalized_action
from execution_manual.manual_execution_intent import make_manual_execution_intent
from execution_manual.manual_trade_ticket import create_or_get_ticket
from infinite_canvas.cockpit import build_alpha_decision_cockpit_view

from .terrain_adapters import terrain_from_slice

# The per-payload keys the builder knows how to fetch, grouped by source.
_SEC_KEYS = ("sec_submissions", "sec_companyfacts")
_FMP_KEYS = ("fmp_profile", "fmp_income_statement", "fmp_ohlcv", "fmp_news", "fmp_ownership")
_YF_KEYS = ("yf_history", "yf_quote")
_ALL_KEYS = _SEC_KEYS + _FMP_KEYS + _YF_KEYS


def _fetch_payloads(
    ticker: str, transports: Dict[str, Callable[[str], Any]],
    cred_status: Dict[str, str], *, enable_yfinance: bool,
) -> Tuple[Dict[str, Any], Dict[str, str], Tuple[Tuple[str, str], ...]]:
    """Run each available transport, returning (payloads, per-source status, gaps).

    Per-source STATUS is one of: fetched / unavailable / credentials_missing / failed /
    deferred. A transport that raises is caught and recorded as ``failed`` (with the
    source name only -- never the exception's URL/credential detail leaking a secret).
    """
    payloads: Dict[str, Any] = {}
    gaps = []
    fetched_by_source = {"sec": 0, "fmp": 0, "yfinance": 0}
    failed_by_source: Dict[str, bool] = {}

    def _source_of(key: str) -> str:
        if key in _SEC_KEYS:
            return "sec"
        if key in _FMP_KEYS:
            return "fmp"
        return "yfinance"

    for key in _ALL_KEYS:
        fetch = transports.get(key)
        if fetch is None:
            continue
        src = _source_of(key)
        try:
            payload = fetch(ticker)
        except Exception:  # noqa: BLE001 -- never let a transport crash the whole run
            failed_by_source[src] = True
            gaps.append(("source_fetch_failed",
                         "{0}: fetch of {1} failed (source degraded; run continues)".format(
                             src, key)))
            continue
        if payload is None:
            gaps.append(("source_payload_unavailable",
                         "{0}: {1} unavailable (no data returned)".format(src, key)))
            continue
        payloads[key] = payload
        fetched_by_source[src] += 1

    # --- derive a per-source status from creds + fetch outcome --------------- #
    status: Dict[str, str] = {}
    for src in ("sec", "fmp", "yfinance"):
        cred = cred_status.get(src, "")
        if cred == "credentials_missing":
            status[src] = "credentials_missing"
            label = {"sec": "SEC User-Agent missing / canonical source unavailable",
                     "fmp": "FMP key missing / convenience source unavailable",
                     "yfinance": "yfinance not enabled"}[src]
            gaps.append(("credentials_missing", label))
        elif cred == "deferred" or (src == "yfinance" and not enable_yfinance):
            status[src] = "deferred"
            gaps.append(("source_deferred",
                         "yfinance live fetching DEFERRED (fallback/research-only, not "
                         "wired for this run)"))
        elif failed_by_source.get(src):
            status[src] = "failed"
        elif fetched_by_source[src] > 0:
            status[src] = "fetched"
        else:
            status[src] = "unavailable"
            gaps.append(("source_unavailable",
                         "{0}: no records fetched (source unavailable)".format(src)))

    return payloads, status, tuple(gaps)


def _gated_slice_result(
    *, subject: str, domain: str, payloads: Dict[str, Any], now: float,
    diligence_inputs: Any, profile: Any, portfolio: Any,
    user_selected_size: Optional[float], actor: str,
) -> Tuple[EvidenceAlphaSliceResult, Tuple[Tuple[str, str], ...]]:
    """Run ingestion, then the EXISTING alpha chain GATED on sufficient inputs."""
    gaps = []
    ingestion = run_fixture_ingestion_slice(
        subject=subject, domain=domain,
        sec_submissions=payloads.get("sec_submissions"),
        sec_companyfacts=payloads.get("sec_companyfacts"),
        fmp_income_statement=payloads.get("fmp_income_statement"),
        fmp_profile=payloads.get("fmp_profile"),
        fmp_ohlcv=payloads.get("fmp_ohlcv"),
        fmp_news=payloads.get("fmp_news"),
        fmp_ownership=payloads.get("fmp_ownership"),
        yf_history=payloads.get("yf_history"),
        yf_quote=payloads.get("yf_quote"),
        now=now, actor=actor,
    )
    ia = ingestion.intelligence_assessment
    base_provenance = {
        "ingestion": ingestion.provenance_chain,
        "source_traces": (ingestion.provenance_chain.traces
                          if ingestion.provenance_chain is not None else ()),
        "conflict_winners": ingestion.resolved_facts,
        "overridden_facts": _overridden_facts(ingestion),
        "downstream": (),
        "cockpit": (),
    }

    oh = thesis = action = personalized = intent = ticket = cockpit = None

    if ia is None or len(ia.signals) == 0:
        gaps.append(("opportunity_skipped",
                     "no signal-bearing assessment from ingested evidence — no opportunity "
                     "hypothesis (factual/deferred input only)"))
    else:
        oh = generate_opportunity_hypothesis([ia], domain=domain, actor=actor, now=now)
        if diligence_inputs is None:
            gaps.append(("thesis_skipped",
                         "InvestmentThesis skipped — no diligence inputs supplied for an "
                         "on-demand run (Nivesha gauntlet needs price/financial diligence)"))
        else:
            thesis = generate_investment_thesis(
                oh, diligence_inputs, actor=actor, now=now)
            action = generate_investment_action(thesis, actor=actor, now=now)
            if profile is not None and portfolio is not None:
                personalized = generate_personalized_action(
                    thesis, action, profile, portfolio, actor=actor, now=now)
                if user_selected_size is not None and float(user_selected_size) > 0:
                    intent = make_manual_execution_intent(
                        personalized,
                        selected_instrument=(
                            thesis.security_or_instrument_mapping or subject),
                        user_selected_allocation_amount=float(user_selected_size),
                        execution_side="open_candidate", actor="user", now=now)
                    ticket = create_or_get_ticket(
                        {}, intent, {
                            "order_type": "limit", "limit_price": None,
                            "time_in_force": "day", "venue": "MANUAL",
                            "price": float(user_selected_size), "actor": "user",
                            "queue_item_id": stable_id("QUE", action.id),
                            "risk_warning": ("manual execution only; preview does not "
                                             "place an order")},
                        now=now)
                else:
                    gaps.append(("intent_skipped",
                                 "ManualExecutionIntent skipped — no explicit user-selected "
                                 "size supplied (no broker order; manual review required)"))
            else:
                gaps.append(("personalized_skipped",
                             "PersonalizedAction skipped — no profile/portfolio supplied "
                             "(Saarathi personalization needs the user's context)"))
            # A decision cockpit is only meaningful once a thesis exists.
            cockpit = build_alpha_decision_cockpit_view(
                opportunity_hypothesis=oh, investment_thesis=thesis,
                investment_action=action, personalized_action=personalized,
                manual_execution_intent=intent, intelligence_assessment=ia,
                observations=ingestion.observations, ticket=ticket)

    provenance = dict(base_provenance)
    provenance["downstream"] = _downstream_provenance(
        intelligence_assessment=ia, opportunity_hypothesis=oh, investment_thesis=thesis,
        investment_action=action, personalized_action=personalized,
        manual_execution_intent=intent, ticket=ticket)
    if cockpit is not None:
        provenance["cockpit"] = cockpit.provenance_chain

    result = EvidenceAlphaSliceResult(
        subject=subject, ingestion_result=ingestion, observations=ingestion.observations,
        intelligence_assessment=ia, opportunity_hypothesis=oh, investment_thesis=thesis,
        investment_action=action, personalized_action=personalized,
        manual_execution_intent=intent, manual_trade_ticket=ticket, cockpit_view=cockpit,
        conflict_warnings=ingestion.conflict_warnings,
        deferred_records=ingestion.deferred_records,
        data_gaps=ingestion.data_gaps + tuple(gaps), provenance_chain=provenance)
    return result, tuple(gaps)


def build_real_evidence_terrain_for_ticker(
    ticker: str, *,
    transports: Optional[Dict[str, Callable[[str], Any]]] = None,
    sec_user_agent: Optional[str] = None,
    fmp_api_key: Optional[str] = None,
    enable_yfinance: bool = False,
    domain: str = "ai-infrastructure",
    diligence_inputs: Any = None,
    profile: Any = None,
    portfolio: Any = None,
    user_selected_size: Optional[float] = None,
    enrichment: Any = None,
    now: Optional[float] = None,
    actor: str = "real-evidence-on-demand",
):
    """Build a sparse REAL-evidence :class:`UniverseTerrain` for one ticker on demand.

    Returns ``(terrain, source_status)`` where ``source_status`` is a mapping
    ``{"sec"/"fmp"/"yfinance": status}`` plus ``run_timestamp`` / ``ticker`` metadata.

    ``transports`` is the injection seam: a mapping of payload key ->
    ``fetch(ticker) -> payload_or_None`` callables. Tests inject MOCK callables that
    return fixture dicts (fully offline). When ``transports`` is None the REAL transports
    are built LAZILY from the supplied credentials via ``evidence_ingestion.live_transport``
    -- the only place network is reached, and only on an explicit on-demand run.
    """
    if not ticker:
        raise ValueError("real_evidence_on_demand requires an explicit ticker")
    ticker = str(ticker).strip().upper()
    run_now = float(now) if now is not None else time.time()

    if transports is None:
        # LAZY import of the single network boundary -- keeps import-time inert.
        from evidence_ingestion import live_transport
        transports, cred_status = live_transport.build_live_transports(
            sec_user_agent=sec_user_agent, fmp_api_key=fmp_api_key,
            enable_yfinance=enable_yfinance)
    else:
        # Injected (mock) transports: creds are irrelevant; yfinance still honours the flag.
        cred_status = {"sec": "wired", "fmp": "wired",
                       "yfinance": "wired" if enable_yfinance else "deferred"}

    payloads, source_status, fetch_gaps = _fetch_payloads(
        ticker, transports, cred_status, enable_yfinance=enable_yfinance)

    result, chain_gaps = _gated_slice_result(
        subject=ticker, domain=domain, payloads=payloads, now=run_now,
        diligence_inputs=diligence_inputs, profile=profile, portfolio=portfolio,
        user_selected_size=user_selected_size, actor=actor)

    run_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(run_now))
    status_gaps = tuple(
        "source status — {0}: {1}".format(k, v) for k, v in sorted(source_status.items()))
    extra_gaps = (
        ("real evidence on demand — manual refresh only; not scheduled; not "
         "broker-connected; data may be incomplete",)
        + status_gaps
        + tuple("{0}: {1}".format(k, d) for k, d in fetch_gaps))

    terrain = terrain_from_slice(
        result, mode="real_evidence_on_demand", extra_data_gaps=extra_gaps,
        enrichment=enrichment)

    status_out = dict(source_status)
    status_out["run_timestamp"] = run_ts
    status_out["ticker"] = ticker
    status_out["mode_label"] = "real_evidence_on_demand"
    # The computed slice result is carried alongside the per-source status so the app can
    # project the view from it. Tests that only want the terrain + statuses can ignore it.
    status_out["slice_result"] = result
    return terrain, status_out
