"""The SEC/FMP evidence source adapter (IMPLEMENTATION-014B).

:class:`SecFmpEvidenceAdapter` feeds the two Phase-014 priority evidence agents -- the
News/Filings sensor (``tattva.news_filings``) and the Financial-Inflection consumer
(``tattva.financial_inflection``, descriptor-only in this slice) -- from the two evidence
sources onboarded in 009/010: SEC EDGAR (filings) and FMP (press-release/news feed +
fundamental figures). It emits :class:`~reality_mesh.models.RealityEvent`s ONLY, per
``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013``.

AUTHORITY LADDER, ASSIGNED IMMEDIATELY PER RECORD (contract §3 -- never promoted):

* **SEC filing fact** (8-K / S-3 / 424B / Form 4 out of the ``sec_submissions`` document) ->
  ``source_authority="canonical"`` + ``claim_status="verified_fact"`` (the filing exists and
  states the fact).
* **Press release / company announcement** (via the FMP news feed) ->
  ``claim_status="company_claim"``; third-party reported news -> ``claim_status=
  "reported_claim"``. Both stay at ``convenience`` authority (FMP is a convenience
  aggregator) and are NEVER promoted to a verified fact.
* **FMP figures** (profile / income statement -> ``fundamental_snapshot``) ->
  ``source_authority="convenience"`` + ``claim_status="inferred"`` -- never canonical.

CREDENTIALS ARE PRESENCE FLAGS ONLY. The descriptor names the required env vars
(``SEC_USER_AGENT`` / ``FMP_API_KEY``); this module reads NO environment variable and the
constructor accepts PRESENCE booleans only -- a value-shaped argument is rejected (and never
echoed back). A missing credential SKIPS that source with a ``credentials_missing`` health
label + a visible gap NAMING the env var -- never a crash, never a leak, never a silent
demo fallback.

NO AMBIENT NETWORK. The adapter is ``network_required=True`` but performs NO network access
itself: every payload arrives through the INJECTED ``transports=`` callables (the exact
per-payload ``fetch(ticker) -> payload`` bundle shape the 010D real mode /
``evidence_ingestion.live_transport.build_live_transports`` uses). This module imports NO
network library anywhere -- not even lazily. :meth:`SecFmpEvidenceAdapter.fetch_checked`
runs ONLY when explicit transports are injected; with NO transports the base boundary's
network refusal stands (skipped + visible gap) because the PRODUCTION network path is the
LAST onboarding stage (contract §4 stage 6) and does not exist in this slice.

FAILURE -> VISIBLE GAP, OTHER WORK CONTINUES. A transport raising a rate-limit-shaped error
is captured as ``rate_limited`` (``rate_limit_status="throttled"``, honoured, never retried
in-pulse); any other transport failure is ``source_unavailable``; a malformed payload is a
``parse_error``. Each failure names its payload/ticker in ``errors`` + ``data_gaps`` and the
remaining tickers/payloads still deliver (a ``partial`` result) -- nothing fabricated.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Ids and ``raw_payload_ref``s are
content-derived (sha256); ``now`` is an injected string (no wall-clock anywhere).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

# Reuse the audited 009B SEC parsing helpers (form classification + the conservative
# dilutive-offering flag) -- parsing rules live in exactly one place.
from evidence_ingestion.sec_edgar import classify_form, detect_offering_flags

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)

__all__ = [
    "SEC_FMP_EVIDENCE_ADAPTER_ID",
    "SEC_FMP_EVIDENCE_DESCRIPTOR",
    "SEC_FMP_EVIDENCE_DISCIPLINES",
    "SEC_TRANSPORT_KEYS",
    "FMP_TRANSPORT_KEYS",
    "FINANCIAL_INFLECTION_CONSUMER_GAP",
    "SecFmpEvidenceAdapter",
]

SEC_FMP_EVIDENCE_ADAPTER_ID = "evidence.sec_fmp"

# The two disciplines this adapter is the source for (Phase-014 priorities #4-#5). A pulse
# takes these disciplines from the adapter ONLY -- a failed/skipped source stays a VISIBLE
# gap and is never silently backfilled from the bundled fixtures.
SEC_FMP_EVIDENCE_DISCIPLINES: Tuple[str, ...] = (
    "news_filings",
    "financial_inflection",
)

# The injected transport bundle keys, mirroring the 010D real-mode per-payload fetch bundle
# (``build_live_transports`` / the watchlist-terrain mock bundles) exactly.
SEC_TRANSPORT_KEYS: Tuple[str, ...] = ("sec_submissions",)
FMP_TRANSPORT_KEYS: Tuple[str, ...] = ("fmp_news", "fmp_profile", "fmp_income_statement")

# The honest note that travels with every fundamental_snapshot delivery in this slice:
# ``tattva.financial_inflection`` has a registered descriptor but NO sensor implementation
# yet, so its events land in the event store / Data Quality as evidence WITHOUT a finding.
FINANCIAL_INFLECTION_CONSUMER_GAP = (
    "financial_inflection sensor is descriptor-only in this slice: "
    "tattva.financial_inflection has a registered descriptor but no sensor implementation, "
    "so fundamental_snapshot events flow to the event store / Data Quality as evidence "
    "without interpretation -- visible gap, no finding fabricated")

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
# ``source_authority`` here is the CEILING tier this adapter may assign (canonical, for SEC
# filing facts only); per-record assignment is stated verbatim in ``claim_status_rules``.
SEC_FMP_EVIDENCE_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=SEC_FMP_EVIDENCE_ADAPTER_ID,
    source_name="SEC EDGAR filings + FMP news/fundamentals",
    source_type="filing",
    source_authority="canonical",           # ceiling: SEC filing facts ONLY; FMP=convenience
    credential_requirements=("SEC_USER_AGENT", "FMP_API_KEY"),   # env var NAMES, never values
    network_required=True,                  # fetch runs ONLY via explicitly injected transports
    rate_limit_policy=(
        "SEC fair-access guidance (<= 10 requests/second with a declared User-Agent) and the "
        "FMP plan quota are honoured by the injected transports; a 429/quota response is "
        "surfaced as rate_limited (rate_limit_status=throttled), never retried inside a "
        "pulse, never hidden"),
    outputs=(
        "sec_8-k_material_event",
        "sec_s-3_shelf_registration",
        "sec_424b_prospectus_offering",
        "sec_form_4_insider_transaction",
        "press_release",
        "reported_news_item",
        "fundamental_snapshot",
    ),
    claim_status_rules=(
        "SEC filing fact (8-K / S-3 / 424B / Form 4 from sec_submissions) -> "
        "source_authority=canonical + claim_status=verified_fact (the filing exists and "
        "states the fact)",
        "press release / company announcement (via fmp_news) -> claim_status=company_claim; "
        "third-party reported news -> claim_status=reported_claim; NEVER promoted to a "
        "verified fact",
        "FMP figures (fmp_profile / fmp_income_statement -> fundamental_snapshot) -> "
        "source_authority=convenience + claim_status=inferred -- never canonical",
        "source_authority is assigned immediately PER RECORD: canonical is reserved for SEC "
        "filing facts; everything fetched via FMP is convenience",
    ),
    failure_modes=(
        "credentials_missing", "rate_limited", "source_unavailable", "parse_error"),
    description=(
        "SEC EDGAR + FMP evidence feeding the News/Filings agent and the (descriptor-only) "
        "Financial-Inflection consumer. Transports are injected; no ambient network; no "
        "scheduler; no broker; labels not numbers on every emitted object."),
)

# classify_form(...) token -> the emitted news_filings event_type. Forms outside this map
# (10-K / 10-Q / 13F / other) are not news_filings catalysts and are not emitted -- selection
# per the descriptor's declared outputs, not a failure.
_FILING_EVENT_TYPES = {
    "sec_8-k": "sec_8-k_material_event",
    "sec_s-3": "sec_s-3_shelf_registration",
    "sec_424b": "sec_424b_prospectus_offering",
    "sec_insider_form": "sec_form_4_insider_transaction",
}

# 8-K item numbers -> the wording of the observed fact (a label, no scoring). Item 1.01
# deliberately says "contract" so the News/Filings sensor's Contract Announcement subagent
# recognises a filed material definitive agreement.
_8K_ITEM_WORDING = (
    ("1.01", "a material definitive contract / agreement (Item 1.01)"),
    ("2.01", "an acquisition or disposition (Item 2.01)"),
    ("2.02", "results of operations (Item 2.02)"),
    ("5.02", "a management change (Item 5.02)"),
    ("8.01", "another material event (Item 8.01)"),
)

# Latest-period income-statement keys -> (metric name, unit) for numeric_values. ONLY these
# are read; an absent key becomes an explicit per-event data gap, never a fabricated number.
_INCOME_NUMERIC_FIELDS = (
    ("revenue", "revenue_usd", "usd"),
    ("grossProfit", "gross_profit_usd", "usd"),
    ("operatingIncome", "operating_income_usd", "usd"),
    ("netIncome", "net_income_usd", "usd"),
)
_PROFILE_NUMERIC_FIELDS = (
    ("mktCap", "market_cap_usd", "usd"),
    ("sharesOutstanding", "shares_outstanding", "shares"),
)

# Error-text shapes recognised as a RATE LIMIT (vs a generic source failure). Matching is
# conservative substring work on the exception text -- a rate limit is honoured (captured,
# never retried in-pulse), everything else is source_unavailable.
_RATE_LIMIT_TOKENS = (
    "429", "rate limit", "rate-limit", "ratelimit", "too many requests", "quota",
    "throttle",
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = "{0} {1}".format(type(exc).__name__, exc).lower()
    return any(token in text for token in _RATE_LIMIT_TOKENS)


def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _payload_ref(key: str, ticker: str, payload: Any) -> str:
    """A content-derived pointer at the exact payload fetched (a ref, never inlined)."""
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return "raw:{0}/{1}#sha256={2}".format(key, ticker, digest)


def _normalise_tickers(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens."""
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


# --------------------------------------------------------------------------- #
# The injected-transports fetch boundary                                       #
# --------------------------------------------------------------------------- #
class _InjectedTransportsBoundary(SourceAdapter):
    """The ``fetch_checked`` boundary for a ``network_required`` adapter whose transports
    are explicitly INJECTED.

    The base boundary refuses any ``network_required`` adapter outright because the
    production network path is the LAST onboarding stage (contract §4 stage 6) and does not
    exist in this slice. When every payload arrives through injected callables, NO ambient
    network is possible -- so this view re-runs the base boundary with the SAME descriptor
    except ``network_required=False`` (the refusal is disarmed; every OTHER check --
    RealityEvents only, authority/raw-ref/provenance per event, honest counts, failure ->
    gap -- still runs unchanged). It is reachable ONLY via
    :meth:`SecFmpEvidenceAdapter.fetch_checked` when transports were injected.
    """

    def __init__(self, outer: "SecFmpEvidenceAdapter",
                 offline_descriptor: SourceAdapterDescriptor) -> None:
        self._outer = outer
        self._descriptor = offline_descriptor

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return self._descriptor

    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        return self._outer.fetch_events(watchlist=watchlist, themes=themes, now=now)


# --------------------------------------------------------------------------- #
# SecFmpEvidenceAdapter                                                        #
# --------------------------------------------------------------------------- #
class SecFmpEvidenceAdapter(SourceAdapter):
    """SEC EDGAR + FMP -> RealityEvents via INJECTED transports. Honest gaps; no network.

    ``transports`` is the 010D-shaped per-payload bundle: a dict mapping
    ``sec_submissions`` / ``fmp_news`` / ``fmp_profile`` / ``fmp_income_statement`` to a
    ``fetch(ticker) -> payload`` callable. ``sec_user_agent_present`` /
    ``fmp_api_key_present`` are PRESENCE flags only (True / False / None=infer from wiring);
    a credential VALUE passed by mistake is rejected without being stored or echoed.
    """

    def __init__(self, transports: Optional[Dict[str, Any]] = None, *,
                 sec_user_agent_present: Optional[bool] = None,
                 fmp_api_key_present: Optional[bool] = None) -> None:
        transports = dict(transports or {})
        for key, fetch in transports.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    "SecFmpEvidenceAdapter transports keys must be non-empty payload names "
                    "(e.g. 'sec_submissions')")
            if not callable(fetch):
                raise ValueError(
                    "SecFmpEvidenceAdapter transports[{0!r}] must be a callable "
                    "fetch(ticker) -> payload (the 010D bundle shape)".format(key))
        for name, flag in (("sec_user_agent_present", sec_user_agent_present),
                           ("fmp_api_key_present", fmp_api_key_present)):
            if flag is not None and not isinstance(flag, bool):
                # NEVER echo the offending argument: it may BE the credential value.
                raise ValueError(
                    "SecFmpEvidenceAdapter.{0} is a PRESENCE flag (True/False/None) -- "
                    "never pass the credential value; the argument was rejected and has "
                    "not been stored".format(name))
        self._transports = transports
        self._sec_present = sec_user_agent_present
        self._fmp_present = fmp_api_key_present
        self._boundary = _InjectedTransportsBoundary(
            self, replace(SEC_FMP_EVIDENCE_DESCRIPTOR, network_required=False))

    # -- identity ----------------------------------------------------------- #
    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return SEC_FMP_EVIDENCE_DESCRIPTOR

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """news_filings + financial_inflection come from this adapter ONLY when it runs --
        a failed / skipped source stays a visible gap, never a fixture backfill."""
        return SEC_FMP_EVIDENCE_DISCIPLINES

    def __repr__(self) -> str:  # presence labels only -- a credential value never exists here
        return ("SecFmpEvidenceAdapter(transports={0}, sec_user_agent_present={1}, "
                "fmp_api_key_present={2})".format(
                    sorted(self._transports), self._sec_present, self._fmp_present))

    # -- the injected-transports gate over fetch_checked --------------------- #
    def fetch_checked(self, *, watchlist=(), themes=(),
                      now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Fetch with the 013 boundary enforced -- accepted ONLY with injected transports.

        * NO transports injected -> the base boundary's ``network_required`` refusal stands:
          a ``skipped`` result with a visible gap (the production network path is the LAST
          onboarding stage and does not exist in this slice). Nothing is fetched.
        * transports injected -> no ambient network is possible (every payload arrives
          through the injected callables; this module imports no network library), so the
          base boundary runs with the network refusal disarmed and every other contract
          check (RealityEvents only; authority + raw ref + provenance per event; honest
          counts; failure -> gap) enforced unchanged.
        """
        if not self._transports:
            return super().fetch_checked(watchlist=watchlist, themes=themes, now=now)
        return self._boundary.fetch_checked(watchlist=watchlist, themes=themes, now=now)

    # -- fetch --------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Pull each ticker's filings / press releases / fundamentals via the injected
        transports into RealityEvents + an honest result.

        Deterministic + offline: calls the injected callables only. Missing credentials
        skip that source with a visible gap; a raising transport is captured as
        ``rate_limited`` / ``source_unavailable`` and the OTHER tickers/payloads continue
        (partial); a malformed payload is a ``parse_error`` gap. Never fabricates; never
        falls back silently.
        """
        state = {"rate_limited": False, "unavailable": False, "parse_failed": False}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        tickers = _normalise_tickers(watchlist)
        if not tickers:
            gaps.append(
                "empty watchlist: the SEC/FMP evidence adapter fetches per ticker and was "
                "given none -- nothing fetched, nothing fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps,
                                    state, now)

        sec_on = self._source_enabled(
            self._sec_present, SEC_TRANSPORT_KEYS, "SEC_USER_AGENT", "SEC EDGAR filings",
            gaps)
        fmp_on = self._source_enabled(
            self._fmp_present, FMP_TRANSPORT_KEYS, "FMP_API_KEY",
            "FMP news / fundamentals", gaps)

        for ticker in tickers:
            if sec_on:
                payload = self._call(
                    "sec_submissions", ticker, errors, gaps, state)
                if payload is not None:
                    events.extend(self._sec_filing_events(
                        ticker, payload, refs, errors, gaps, state, now))
            if fmp_on:
                news = self._call("fmp_news", ticker, errors, gaps, state)
                if news is not None:
                    events.extend(self._news_events(
                        ticker, news, refs, errors, gaps, state, now))
                profile = self._call("fmp_profile", ticker, errors, gaps, state)
                income = self._call("fmp_income_statement", ticker, errors, gaps, state)
                snapshot = self._fundamental_snapshot_event(
                    ticker, profile, income, refs, errors, gaps, state, now)
                if snapshot is not None:
                    events.append(snapshot)

        if any(e.discipline == "financial_inflection" for e in events):
            gaps.append(FINANCIAL_INFLECTION_CONSUMER_GAP)

        creds_missing = (self._sec_present is False or self._fmp_present is False)
        problems = (creds_missing or state["rate_limited"] or state["unavailable"]
                    or state["parse_failed"])
        if events:
            status = "partial" if problems else "success"
        elif creds_missing and not (state["rate_limited"] or state["unavailable"]
                                    or state["parse_failed"]):
            status = "skipped"      # nothing ran: credentials absent, honestly refused
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "SEC/FMP evidence transports delivered no events for {0} -- visible gap, "
                "nothing fabricated".format(", ".join(tickers)))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, state, now)

    # -- source enablement (credentials as PRESENCE + wiring, never values) --- #
    def _source_enabled(self, present_flag: Optional[bool], keys: Tuple[str, ...],
                        env_var: str, source_label: str, gaps: List[str]) -> bool:
        if present_flag is False:
            gaps.append(
                "{0} missing (presence flag false): {1} skipped this pulse -- their events "
                "have NO coverage; visible gap (credentials_missing), nothing fabricated, "
                "no silent demo fallback".format(env_var, source_label))
            return False
        wired = [k for k in keys if k in self._transports]
        if not wired:
            gaps.append(
                "no {0} transport wired ({1}): {2} skipped this pulse -- visible gap, "
                "nothing fabricated".format(
                    source_label, "/".join(keys), source_label))
            return False
        # A wired transport implies its credential seam was satisfied upstream, exactly as
        # in 010D where build_live_transports only wires a source when its credential is
        # supplied -- presence is a label, the value never reaches this module.
        return True

    # -- one guarded transport call ------------------------------------------ #
    def _call(self, key: str, ticker: str, errors: List[str], gaps: List[str],
              state: Dict[str, bool]) -> Any:
        fetch = self._transports.get(key)
        if fetch is None:
            gaps.append(
                "transport {0} not wired: its payloads are missing this pulse -- visible "
                "gap, nothing fabricated".format(key))
            return None
        try:
            return fetch(ticker)
        except Exception as exc:  # noqa: BLE001 -- failure becomes a gap, never a crash
            reason = "{0}: {1}".format(type(exc).__name__, exc)
            if _is_rate_limit_error(exc):
                state["rate_limited"] = True
                errors.append("rate_limited: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "rate limit hit on {0} for {1}: payload missing this pulse -- limit "
                    "honoured (not retried in-pulse); visible gap, nothing "
                    "fabricated".format(key, ticker))
            else:
                state["unavailable"] = True
                errors.append("source_unavailable: {0} {1}: {2}".format(key, ticker, reason))
                gaps.append(
                    "source {0} unavailable for {1}: payload missing this pulse -- visible "
                    "gap, nothing fabricated, no silent demo fallback".format(key, ticker))
            return None

    # -- SEC submissions -> canonical filing-fact events ---------------------- #
    def _sec_filing_events(self, ticker: str, payload: Any, refs: List[str],
                           errors: List[str], gaps: List[str], state: Dict[str, bool],
                           now: str) -> List[RealityEvent]:
        ref = _payload_ref("sec_submissions", ticker, payload)
        refs.append(ref)
        try:
            filings = _filings_from_submissions(payload)
        except Exception as exc:
            state["parse_failed"] = True
            errors.append("parse_error: sec_submissions {0}: {1}: {2}".format(
                ticker, type(exc).__name__, exc))
            gaps.append(
                "malformed SEC submissions payload for {0} (parse_error): canonical filing "
                "facts have NO coverage for {0} this pulse -- visible gap, nothing "
                "fabricated".format(ticker))
            return []

        out: List[RealityEvent] = []
        for filing in filings:
            kind = classify_form(filing["form"])
            event_type = _FILING_EVENT_TYPES.get(kind)
            if event_type is None:
                continue    # 10-K/10-Q/13F/other: not a declared output of this adapter
            out.append(self._filing_event(ticker, filing, kind, event_type, ref, now))
        if not out:
            gaps.append(
                "SEC submissions for {0} carried no 8-K / S-3 / 424B / Form 4 filings: no "
                "filing-fact events this pulse -- honest absence, nothing "
                "fabricated".format(ticker))
        return out

    def _filing_event(self, ticker: str, filing: Dict[str, str], kind: str,
                      event_type: str, ref: str, now: str) -> RealityEvent:
        form = filing["form"]
        accession = filing["accession"]
        items = filing["items"]
        desc = filing["primary_desc"]

        if kind in ("sec_s-3", "sec_424b") or detect_offering_flags(form, desc, items):
            fact = ("{0} filed {1}: shelf / at-the-market registration (dilutive offering "
                    "risk){2}".format(
                        ticker, form, " -- {0}".format(desc.lower()) if desc else ""))
        elif kind == "sec_insider_form":
            fact = "{0}: insider Form 4 transaction filed".format(ticker)
        else:
            wording = next((w for code, w in _8K_ITEM_WORDING if code in items), "")
            fact = "{0} filed an 8-K disclosing {1}".format(
                ticker, wording or "a material event")

        slug = kind.replace("sec_", "").replace("-", "").replace("/", "_")
        excerpt = ()
        if filing["primary_document"]:
            excerpt = ("sec:edgar/{0}/{1}/{2}".format(
                ticker, accession, filing["primary_document"]),)
        return RealityEvent(
            event_id="secfmp.sec.{0}.{1}.{2}".format(
                ticker.lower(), slug, _sha12(ticker, form, accession)),
            timestamp=filing["filing_date"] or now,
            source_id="sec.edgar",
            source_type=kind,
            source_authority="canonical",       # SEC filing fact: assigned immediately
            claim_status="verified_fact",       # the filing exists and states the fact
            raw_payload_ref=ref,
            discipline="news_filings",
            event_type=event_type,
            affected_companies=(ticker,),
            observed_fact=fact,
            text_excerpt_refs=excerpt,
            evidence_refs=("sec:edgar/{0}/{1}/{2}".format(ticker, form, accession),),
            source_refs=(ref,),
            confidence_label="high",
            freshness_label="recent",
            half_life="weeks",
        )

    # -- FMP news -> company_claim / reported_claim events --------------------- #
    def _news_events(self, ticker: str, payload: Any, refs: List[str],
                     errors: List[str], gaps: List[str], state: Dict[str, bool],
                     now: str) -> List[RealityEvent]:
        ref = _payload_ref("fmp_news", ticker, payload)
        refs.append(ref)
        if not isinstance(payload, list) or not all(
                isinstance(entry, dict) for entry in payload):
            state["parse_failed"] = True
            errors.append(
                "parse_error: fmp_news {0}: payload must be a list of news objects".format(
                    ticker))
            gaps.append(
                "malformed FMP news payload for {0} (parse_error): press-release / news "
                "events have NO coverage for {0} this pulse -- visible gap, nothing "
                "fabricated".format(ticker))
            return []

        out: List[RealityEvent] = []
        for index, entry in enumerate(payload):
            title = str(entry.get("title", "") or "").strip()
            if not title:
                state["parse_failed"] = True
                errors.append(
                    "parse_error: fmp_news {0} entry {1}: missing title".format(
                        ticker, index))
                gaps.append(
                    "invalid FMP news entry {0} for {1} rejected (parse_error) -- "
                    "surfaced, never silently repaired".format(index, ticker))
                continue
            published = str(entry.get("publishedDate", "") or "")
            is_pr = (str(entry.get("type", "") or "").strip().lower() == "press_release"
                     or "announc" in title.lower())
            url = str(entry.get("url", "") or "")
            kwargs = dict(
                event_id="secfmp.fmp.news.{0}.{1}".format(
                    ticker.lower(), _sha12(ticker, published, title)),
                timestamp=published or now,
                source_id="fmp.news",
                # company statement delivered via the FMP aggregator: the claim is the
                # company's, the TRANSPORT authority stays convenience -- never promoted.
                source_type="fmp_press_release" if is_pr else "fmp_reported_news",
                source_authority="convenience",
                claim_status="company_claim" if is_pr else "reported_claim",
                raw_payload_ref=ref,
                discipline="news_filings",
                event_type="press_release" if is_pr else "reported_news_item",
                affected_companies=(ticker,),
                observed_fact="{0}: {1}".format(
                    "press release" if is_pr else "reported news", title),
                text_excerpt_refs=(url,) if url else (),
                evidence_refs=(url,) if url else (ref,),
                source_refs=(ref,),
                confidence_label="moderate",
                freshness_label="recent",
                half_life="days",
            )
            if is_pr:
                kwargs["company_claim"] = title     # marked as the company's statement
            out.append(RealityEvent(**kwargs))
        return out

    # -- FMP profile + income statement -> ONE fundamental_snapshot event ------ #
    def _fundamental_snapshot_event(self, ticker: str, profile: Any, income: Any,
                                    refs: List[str], errors: List[str], gaps: List[str],
                                    state: Dict[str, bool],
                                    now: str) -> Optional[RealityEvent]:
        if profile is None and income is None:
            return None     # both payloads already reported as gaps by _call

        numeric: List[Tuple[str, object, str]] = []
        event_gaps: List[str] = []
        evidence: List[str] = []
        latest_period = ""
        prior_period = ""

        if income is not None:
            income_ref = _payload_ref("fmp_income_statement", ticker, income)
            refs.append(income_ref)
            try:
                rows = _income_rows(income)
            except Exception as exc:
                state["parse_failed"] = True
                errors.append("parse_error: fmp_income_statement {0}: {1}: {2}".format(
                    ticker, type(exc).__name__, exc))
                gaps.append(
                    "malformed FMP income statement for {0} (parse_error): fundamental "
                    "figures have NO coverage for {0} this pulse -- visible gap, nothing "
                    "fabricated".format(ticker))
                rows = []
            if rows:
                evidence.append(income_ref)
                latest = rows[-1]
                latest_period = str(latest.get("date", "") or "")
                for key, name, unit in _INCOME_NUMERIC_FIELDS:
                    value = latest.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        numeric.append((name, value, unit))
                    else:
                        event_gaps.append(
                            "{0} not reported in the latest FMP income statement for {1} "
                            "-- left absent, never fabricated".format(name, ticker))
                if len(rows) >= 2:
                    prior = rows[-2]
                    prior_period = str(prior.get("date", "") or "")
                    prior_rev = prior.get("revenue")
                    if isinstance(prior_rev, (int, float)) and not isinstance(
                            prior_rev, bool):
                        numeric.append(("revenue_prior_usd", prior_rev, "usd"))
                else:
                    event_gaps.append(
                        "only one reported period in the FMP income statement for {0}: no "
                        "prior-period comparison -- not fabricated".format(ticker))

        if profile is not None:
            profile_ref = _payload_ref("fmp_profile", ticker, profile)
            refs.append(profile_ref)
            row = profile[0] if isinstance(profile, list) and profile else profile
            if isinstance(row, dict):
                evidence.append(profile_ref)
                for key, name, unit in _PROFILE_NUMERIC_FIELDS:
                    value = row.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        numeric.append((name, value, unit))
            else:
                state["parse_failed"] = True
                errors.append(
                    "parse_error: fmp_profile {0}: payload must be an object or a "
                    "one-object list".format(ticker))
                gaps.append(
                    "malformed FMP profile for {0} (parse_error): market-cap / share-count "
                    "figures missing this pulse -- visible gap, nothing "
                    "fabricated".format(ticker))

        if not evidence:
            return None     # nothing parseable: the gaps above already tell the story

        fact = "FMP fundamental snapshot for {0}".format(ticker)
        if latest_period:
            fact += ": latest reported period {0}".format(latest_period)
        if prior_period:
            fact += " (prior {0})".format(prior_period)
        return RealityEvent(
            event_id="secfmp.fmp.fundamental.{0}.{1}".format(
                ticker.lower(), _sha12(ticker, latest_period, *sorted(evidence))),
            timestamp=latest_period or now,
            source_id="fmp",
            source_type="fmp_fundamental_snapshot",
            source_authority="convenience",     # FMP figures: convenience, never canonical
            claim_status="inferred",            # derived vendor figures, never a verified fact
            raw_payload_ref=evidence[0],
            discipline="financial_inflection",
            event_type="fundamental_snapshot",
            affected_companies=(ticker,),
            observed_fact=fact,
            numeric_values=tuple(numeric),
            evidence_refs=tuple(evidence),
            source_refs=tuple(evidence),
            confidence_label="moderate",
            freshness_label="recent",
            half_life="quarters",
            data_gaps=tuple(event_gaps),
        )

    # -- result builder -------------------------------------------------------- #
    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                state: Dict[str, bool], now: str) -> SourceAdapterResult:
        creds_missing = (self._sec_present is False or self._fmp_present is False)
        if creds_missing:
            health = "credentials_missing"
        elif state["rate_limited"]:
            health = "rate_limited"
        elif status == "success":
            health = "healthy"
        elif status == "partial":
            health = "degraded"
        elif status == "skipped":
            health = "source_unavailable"
        else:
            health = "failed"
        run_id = deterministic_adapter_run_id(
            SEC_FMP_EVIDENCE_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=SEC_FMP_EVIDENCE_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="missing" if creds_missing else "present",
            rate_limit_status="throttled" if state["rate_limited"] else "ok",
            source_health=health)


# --------------------------------------------------------------------------- #
# Payload shape helpers (raise on a malformed payload -> parse_error upstream)  #
# --------------------------------------------------------------------------- #
def _filings_from_submissions(payload: Any) -> List[Dict[str, str]]:
    """The parallel ``filings.recent`` arrays of a data.sec.gov submissions document,
    zipped into one dict per filing. Raises ``ValueError`` on a malformed payload."""
    if not isinstance(payload, dict):
        raise ValueError("SEC submissions payload must be a JSON object")
    recent = ((payload.get("filings") or {}).get("recent")) or {}
    forms = recent.get("form")
    if not isinstance(forms, list) or not forms:
        raise ValueError("SEC submissions payload has no filings.recent.form list")

    def _at(name: str, i: int) -> str:
        arr = recent.get(name) or []
        return str(arr[i]) if isinstance(arr, list) and i < len(arr) and arr[i] else ""

    return [
        {
            "form": str(forms[i]),
            "accession": _at("accessionNumber", i),
            "filing_date": _at("filingDate", i),
            "primary_document": _at("primaryDocument", i),
            "primary_desc": _at("primaryDocDescription", i),
            "items": _at("items", i),
        }
        for i in range(len(forms))
    ]


def _income_rows(payload: Any) -> List[Dict[str, Any]]:
    """FMP income-statement rows sorted oldest -> latest by ``date``. Raises on malformed."""
    if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload):
        raise ValueError("FMP income statement payload must be a list of period objects")
    rows = [row for row in payload if row.get("date")]
    if payload and not rows:
        raise ValueError("FMP income statement periods carry no 'date' field")
    return sorted(rows, key=lambda row: str(row.get("date", "")))
