"""Evidence-driven ticker/universe DISCOVERY for the Reality Mesh (UNIVERSE-DISCOVERY UD-1).

The operator no longer hand-curates the universe: given a theme / sector, UD-1 finds REAL
companies with full provenance from two real sources and emits provenanced
:class:`DiscoveredUniverseCandidate`s. This slice is **DISCOVERY ONLY** -- it surfaces
provenanced candidates and NOTHING more:

* it does NOT accept them (that is a later slice),
* it does NOT modify the theme graph (:mod:`reality_mesh.theme_graph`),
* it does NOT drive the engine / pulse / lineage (that is UD-3 / UD-4).

HONESTY IS THE INVARIANT. Every candidate traces to a REAL screener row (FMP
``company-screener``) or a REAL EDGAR full-text-search filing hit (``efts.sec.gov``). A source
miss / empty / 429 / timeout / malformed payload / an unmapped CIK is a VISIBLE ``data_gap`` --
NEVER a fabricated ticker, theme, or company, and NEVER a fixture/demo fallback. There is no
score / rank / rating field and no buy / sell / order / broker affordance anywhere
(``assert_no_trade_fields``-clean).

AUTHORITY IS DISCOVERY PROVENANCE, NOT A RECOMMENDATION.

* ``sec_fulltext`` candidates are ``source_authority="canonical"`` -- the company REALLY files
  about the phrase (a canonical regulatory filing exists), which is high-authority DISCOVERY
  evidence, never an investment conclusion.
* ``fmp_screener`` candidates are ``source_authority="convenience"`` -- a commercial provider
  says the company is in that sector; useful context, never canonical, never a claim about value.
* On a cross-method dedupe (same ticker from both), the HIGHER authority wins (``canonical`` >
  ``convenience``) and BOTH provenance refs are preserved.

NO NETWORK ON IMPORT. This module imports NO network library at top level. The DEFAULT real
transports are built lazily inside the producers from ``evidence_ingestion.live_transport``
(whose ``urllib`` is itself function-local). The whole test suite runs OFFLINE under a socket
kill-switch and NEVER exercises the real network path: tests inject mock transports. A LIVE
fetch reaches the wire ONLY when an operator runs a producer with a supplied credential.

CREDENTIALS ARE PRESENCE LABELS ONLY. ``FMP_API_KEY`` / ``SEC_USER_AGENT`` presence is read
from an injected ``env`` (default ``os.environ``); the VALUE transits only into the transport
builder and is never stored / logged / echoed. A missing credential is a visible
``credentials_missing`` gap, never a crash or a leak.

Deterministic, stdlib-only, Python 3.9, OFFLINE tests. ``candidate_id`` is content-derived
(sha256 of the ticker); ``discovered_at`` is an injected string (no wall-clock).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .labels import authority_rank
from .validation import assert_no_trade_fields

__all__ = [
    "UNIVERSE_DISCOVERY_SCHEMA_VERSION",
    "DISCOVERY_METHODS",
    "DISCOVERY_METHOD_AUTHORITY",
    "DISCOVERY_SOURCE_HEALTH_LABELS",
    "DiscoveredUniverseCandidate",
    "UniverseDiscoveryResult",
    "candidate_id_for",
    "discover_via_fmp_screener",
    "discover_via_sec_fulltext",
    "merge_universe_discovery",
]

UNIVERSE_DISCOVERY_SCHEMA_VERSION = "ud-1"

# The two discovery producers. A candidate ALWAYS carries exactly one (its originating method);
# a merged cross-method candidate carries the HIGHER-authority method.
DISCOVERY_METHODS: Tuple[str, ...] = ("fmp_screener", "sec_fulltext")

# Method -> discovery-provenance authority. A screener row is convenience (a provider says the
# company is in the sector); a full-text filing hit is canonical (the company really files about
# the phrase). This is DISCOVERY provenance, NOT an investment claim.
DISCOVERY_METHOD_AUTHORITY: Dict[str, str] = {
    "fmp_screener": "convenience",
    "sec_fulltext": "canonical",
}

# Per-source health labels (a subset of the closed HEALTH_STATES vocabulary).
DISCOVERY_SOURCE_HEALTH_LABELS: Tuple[str, ...] = (
    "healthy", "degraded", "failed", "credentials_missing", "rate_limited",
    "source_unavailable",
)

# Error-text shapes recognised as a RATE LIMIT / quota / access throttle (vs a generic failure).
_RATE_LIMIT_TOKENS = (
    "429", "403", "rate limit", "rate-limit", "ratelimit", "too many requests",
    "forbidden", "throttle", "quota", "limit reach", "limit reached", "exceeded your",
)

# Extracts a bracketed ticker from an SEC ``display_names`` entry, e.g.
# "IREN Limited (IREN) (CIK 0001878848)" -> the "(IREN)" group. Used only for the company NAME
# split below; the AUTHORITATIVE ticker always comes from the CIK->ticker map (never guessed).
_DISPLAY_NAME_TICKER = re.compile(r"\(([A-Za-z0-9.\-]{1,10})\)")


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = "{0} {1}".format(type(exc).__name__, exc).lower()
    return any(token in text for token in _RATE_LIMIT_TOKENS)


def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _pad_cik(cik: object) -> str:
    digits = "".join(ch for ch in str(cik or "") if ch.isdigit())
    return digits.zfill(10) if digits else ""


def candidate_id_for(ticker: str) -> str:
    """A deterministic, content-derived candidate id from the ticker (order-stable).

    Derived from the ticker ALONE so the same real company discovered by both producers collides
    on one id -- that is exactly what lets dedupe merge BOTH provenance refs into a single
    candidate while preserving the higher authority.
    """
    tk = str(ticker or "").strip().upper()
    return "udc:{0}:{1}".format(tk, _sha12(tk))


# --------------------------------------------------------------------------- #
# The typed candidate contract (frozen, validated, trade/score-clean)           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiscoveredUniverseCandidate:
    """One REAL company surfaced by discovery, with provenance -- NOT accepted, NOT in the graph.

    A candidate is a provenanced POINTER at a real company that a real source surfaced for a
    theme/sector/phrase. It is emphatically NOT a recommendation and confers NO capital standing:
    acceptance, graph placement, and any engine role are later slices. There is NO score / rank /
    rating field and NO trade affordance anywhere (``assert_no_trade_fields``-clean).
    """

    candidate_id: str = ""                 # REQUIRED, content-derived (from the ticker)
    ticker: str = ""                       # REQUIRED -- a REAL symbol from a REAL source
    company_name: str = ""                 # as reported by the source
    theme_hint: str = ""                   # the sector/industry/query that surfaced it
    discovery_method: str = ""             # closed: DISCOVERY_METHODS (higher-authority on merge)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)   # REAL provenance refs
    source_authority: str = ""             # canonical (sec_fulltext) / convenience (fmp_screener)
    evidence_note: str = ""                # e.g. market cap / filing date / form (plain English)
    discovered_at: str = ""                # injected timestamp (no wall-clock)
    schema_version: str = UNIVERSE_DISCOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("candidate_id", "ticker"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "DiscoveredUniverseCandidate.{0} is a required id/field and must be "
                    "non-empty (nothing fabricated)".format(name))
        if self.discovery_method not in DISCOVERY_METHODS:
            raise ValueError(
                "DiscoveredUniverseCandidate.discovery_method {0!r} invalid (allowed: {1})".format(
                    self.discovery_method, list(DISCOVERY_METHODS)))
        if self.source_authority not in ("canonical", "convenience"):
            raise ValueError(
                "DiscoveredUniverseCandidate.source_authority {0!r} invalid -- discovery "
                "provenance is canonical (sec_fulltext) or convenience (fmp_screener)".format(
                    self.source_authority))
        if not self.source_refs:
            raise ValueError(
                "DiscoveredUniverseCandidate must carry at least one REAL source_ref "
                "(provenance) -- a candidate with no provenance would be fabricated")


# The contract (for registry / test introspection). Trade/score-clean.
UNIVERSE_DISCOVERY_MODELS = (DiscoveredUniverseCandidate,)


# --------------------------------------------------------------------------- #
# The checked-result shape (mirrors the adapters' candidates+health+gaps result) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UniverseDiscoveryResult:
    """The provenanced output of a discovery run: candidates + per-source health + visible gaps.

    A miss is ALWAYS a ``data_gap`` here (with 0 candidates for that source), never a fabricated
    candidate. ``source_health`` maps each discovery method that ran to a closed health label.
    """

    candidates: Tuple[DiscoveredUniverseCandidate, ...] = field(default_factory=tuple)
    source_health: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def health_of(self, method: str) -> str:
        for name, label in self.source_health:
            if name == method:
                return label
        return ""


# --------------------------------------------------------------------------- #
# Dedupe (canonical > convenience), preserving BOTH provenance refs             #
# --------------------------------------------------------------------------- #
def _merge_two(base: DiscoveredUniverseCandidate,
               other: DiscoveredUniverseCandidate) -> DiscoveredUniverseCandidate:
    """Merge two same-ticker candidates: HIGHER authority wins its fields; BOTH refs preserved."""
    hi, lo = base, other
    if authority_rank(other.source_authority) > authority_rank(base.source_authority):
        hi, lo = other, base
    # Union of provenance refs, higher-authority first, order-stable, de-duplicated.
    refs = tuple(dict.fromkeys(tuple(hi.source_refs) + tuple(lo.source_refs)))
    notes = " | ".join(dict.fromkeys(n for n in (hi.evidence_note, lo.evidence_note) if n))
    hints = " | ".join(dict.fromkeys(h for h in (hi.theme_hint, lo.theme_hint) if h))
    return DiscoveredUniverseCandidate(
        candidate_id=hi.candidate_id,
        ticker=hi.ticker,
        company_name=hi.company_name or lo.company_name,
        theme_hint=hints,
        discovery_method=hi.discovery_method,          # the higher-authority method
        source_refs=refs,
        source_authority=hi.source_authority,          # the HIGHER authority (canonical wins)
        evidence_note=notes,
        discovered_at=hi.discovered_at or lo.discovered_at,
        schema_version=hi.schema_version,
    )


def _dedupe(candidates: List[DiscoveredUniverseCandidate]
            ) -> Tuple[DiscoveredUniverseCandidate, ...]:
    """Dedupe by candidate_id (== ticker-derived), first-seen order, merging refs + authority."""
    order: List[str] = []
    merged: Dict[str, DiscoveredUniverseCandidate] = {}
    for cand in candidates:
        key = cand.candidate_id
        if key not in merged:
            merged[key] = cand
            order.append(key)
        else:
            merged[key] = _merge_two(merged[key], cand)
    return tuple(merged[k] for k in order)


def _health(*, candidates: bool, rate_limited: bool, unavailable: bool,
            parse_failed: bool, creds_missing: bool) -> str:
    """A per-source health LABEL mirroring the adapters' precedence."""
    if creds_missing:
        return "credentials_missing"
    if rate_limited:
        return "rate_limited"
    if unavailable:
        return "source_unavailable"
    if candidates:
        return "degraded" if parse_failed else "healthy"
    if parse_failed:
        return "failed"
    return "healthy"          # a valid but empty response -- the source worked, found nothing


# --------------------------------------------------------------------------- #
# Producer 1: FMP company screener (CONVENIENCE)                                 #
# --------------------------------------------------------------------------- #
def discover_via_fmp_screener(*, sector: str = "", industry: str = "",
                              market_cap_min: Optional[float] = None, limit: int = 50,
                              transport: Optional[Callable[..., Any]] = None,
                              env: Optional[Dict[str, str]] = None,
                              now: str = "") -> UniverseDiscoveryResult:
    """Discover REAL companies from the FMP company screener for a sector/industry.

    ``transport`` is an INJECTABLE ``screen(*, sector, industry, market_cap_min, limit) ->
    decoded JSON array`` callable. When ``None`` the DEFAULT real transport is built lazily from
    ``env`` (default ``os.environ``) FMP_API_KEY PRESENCE (import-time is network-free); a
    missing key is a ``credentials_missing`` gap, never a crash/leak. Every candidate is a REAL
    screener row (``symbol`` required) stamped ``source_authority="convenience"``. An empty /
    429 / timeout / malformed response is a VISIBLE gap with 0 fabricated tickers.
    """
    method = "fmp_screener"
    gaps: List[str] = []
    rate_limited = unavailable = parse_failed = False

    if transport is None:
        transport = _default_fmp_transport(env)
        if transport is None:
            gaps.append(
                "FMP_API_KEY missing (presence only): FMP screener discovery skipped -- visible "
                "gap (credentials_missing), nothing fabricated, no fixture fallback")
            return UniverseDiscoveryResult(
                candidates=(), data_gaps=tuple(gaps),
                source_health=((method, "credentials_missing"),))

    theme_hint = " / ".join(p for p in (sector.strip(), industry.strip()) if p) or "screener"
    provenance = "fmp:screener/{0}/{1}".format(sector.strip() or "-", industry.strip() or "-")

    try:
        payload = transport(sector=sector, industry=industry,
                            market_cap_min=market_cap_min, limit=limit)
    except Exception as exc:                # noqa: BLE001 -- failure becomes a gap, never a crash
        reason = "{0}: {1}".format(type(exc).__name__, exc)
        if _is_rate_limit_error(exc):
            rate_limited = True
            gaps.append(
                "rate limit / quota (HTTP 429/403) hit on FMP screener ({0}): no candidates this "
                "run -- limit honoured (not retried); visible gap, nothing fabricated".format(
                    theme_hint))
        else:
            unavailable = True
            gaps.append(
                "FMP screener unavailable / timed out ({0}): {1} -- no candidates this run; "
                "visible gap, nothing fabricated, no fixture fallback".format(theme_hint, reason))
        return UniverseDiscoveryResult(
            candidates=(), data_gaps=tuple(gaps),
            source_health=((method, _health(
                candidates=False, rate_limited=rate_limited, unavailable=unavailable,
                parse_failed=False, creds_missing=False)),))

    rows = _as_rows(payload)
    if rows is None:
        parse_failed = True
        gaps.append(
            "malformed FMP screener payload ({0}): expected a JSON array of company rows -- no "
            "candidates this run; visible gap, nothing fabricated".format(theme_hint))
        rows = []

    candidates: List[DiscoveredUniverseCandidate] = []
    for row in rows:
        ticker = str(row.get("symbol") or "").strip().upper()
        if not ticker:
            continue                        # never fabricate a ticker for a symbol-less row
        market_cap = row.get("marketCap")
        row_sector = str(row.get("sector") or sector or "").strip()
        row_industry = str(row.get("industry") or industry or "").strip()
        note_bits = []
        if market_cap not in (None, ""):
            note_bits.append("market cap {0}".format(market_cap))
        descriptor = " -- ".join(p for p in (row_sector, row_industry) if p)
        if descriptor:
            note_bits.append(descriptor)
        candidates.append(DiscoveredUniverseCandidate(
            candidate_id=candidate_id_for(ticker),
            ticker=ticker,
            company_name=str(row.get("companyName") or row.get("name") or "").strip(),
            theme_hint=theme_hint,
            discovery_method=method,
            source_refs=(provenance,),
            source_authority="convenience",
            evidence_note="; ".join(note_bits) or "FMP screener match (provider context)",
            discovered_at=now,
        ))

    deduped = _dedupe(candidates)
    if not deduped and not (rate_limited or unavailable or parse_failed):
        gaps.append(
            "FMP screener returned no companies for {0} -- visible gap, nothing fabricated".format(
                theme_hint))
    return UniverseDiscoveryResult(
        candidates=deduped, data_gaps=tuple(gaps),
        source_health=((method, _health(
            candidates=bool(deduped), rate_limited=rate_limited, unavailable=unavailable,
            parse_failed=parse_failed, creds_missing=False)),))


# --------------------------------------------------------------------------- #
# Producer 2: SEC EDGAR full-text search (CANONICAL)                             #
# --------------------------------------------------------------------------- #
def discover_via_sec_fulltext(query: str, *, forms: Tuple[str, ...] = ("10-K",),
                              transport: Optional[Dict[str, Any]] = None,
                              env: Optional[Dict[str, str]] = None,
                              now: str = "") -> UniverseDiscoveryResult:
    """Discover REAL companies whose filings match a phrase via SEC EDGAR full-text search.

    ``transport`` is an INJECTABLE bundle: ``"search"`` -> ``fetch(query, forms) -> FTS hits``
    and ``"company_tickers"`` -> ``fetch() -> ticker->CIK map`` (for CIK->ticker mapping). When
    ``None`` the DEFAULT real transport is built lazily from ``env`` (default ``os.environ``)
    SEC_USER_AGENT PRESENCE (import-time is network-free); a missing User-Agent is a
    ``credentials_missing`` gap, never a crash/leak. Each candidate carries the REAL matching
    accession + CIK as provenance and is ``source_authority="canonical"`` (the company really
    files about the phrase). A CIK with no ticker mapping is an HONEST gap (never dropped
    silently, never guessed); 429 / timeout / malformed is a visible gap. Nothing fabricated.
    """
    method = "sec_fulltext"
    gaps: List[str] = []
    rate_limited = unavailable = parse_failed = False

    if transport is None:
        transport = _default_sec_transport(env)
        if transport is None:
            gaps.append(
                "SEC_USER_AGENT missing (presence only): SEC full-text discovery skipped -- "
                "visible gap (credentials_missing), nothing fabricated, no fixture fallback")
            return UniverseDiscoveryResult(
                candidates=(), data_gaps=tuple(gaps),
                source_health=((method, "credentials_missing"),))

    query_text = str(query or "").strip()
    if not query_text:
        gaps.append(
            "empty query: SEC full-text discovery needs a phrase and was given none -- nothing "
            "fetched, nothing fabricated")
        return UniverseDiscoveryResult(
            candidates=(), data_gaps=tuple(gaps), source_health=((method, "healthy"),))

    search = transport.get("search") if isinstance(transport, dict) else None
    if not callable(search):
        gaps.append(
            "SEC full-text 'search' transport not wired: no candidates this run -- visible gap, "
            "nothing fabricated")
        return UniverseDiscoveryResult(
            candidates=(), data_gaps=tuple(gaps), source_health=((method, "source_unavailable"),))

    try:
        payload = search(query_text, tuple(forms or ()))
    except Exception as exc:                # noqa: BLE001 -- failure becomes a gap, never a crash
        reason = "{0}: {1}".format(type(exc).__name__, exc)
        if _is_rate_limit_error(exc):
            rate_limited = True
            gaps.append(
                "rate limit (HTTP 429/403) hit on SEC full-text search ({0!r}): no candidates "
                "this run -- limit honoured (not retried); visible gap, nothing fabricated".format(
                    query_text))
        else:
            unavailable = True
            gaps.append(
                "SEC full-text search unavailable / timed out ({0!r}): {1} -- no candidates this "
                "run; visible gap, nothing fabricated, no fixture fallback".format(
                    query_text, reason))
        return UniverseDiscoveryResult(
            candidates=(), data_gaps=tuple(gaps),
            source_health=((method, _health(
                candidates=False, rate_limited=rate_limited, unavailable=unavailable,
                parse_failed=False, creds_missing=False)),))

    try:
        hits = _fts_hits(payload)
    except Exception as exc:                # noqa: BLE001 -- malformed -> visible parse gap
        parse_failed = True
        gaps.append(
            "malformed SEC full-text payload ({0!r}): {1}: {2} -- no candidates this run; visible "
            "gap, nothing fabricated".format(query_text, type(exc).__name__, exc))
        return UniverseDiscoveryResult(
            candidates=(), data_gaps=tuple(gaps),
            source_health=((method, "failed"),))

    # CIK -> ticker map (canonical mapping; never a guessed ticker). Fetched lazily, once.
    cik_map, map_gap = _sec_cik_map(transport, query_text)
    if map_gap:
        gaps.append(map_gap)

    candidates: List[DiscoveredUniverseCandidate] = []
    for hit in hits:
        cik = _pad_cik(hit.get("cik"))
        accession = str(hit.get("accession") or "").strip()
        if not cik:
            gaps.append(
                "SEC full-text hit with no CIK for {0!r} -- honest gap, ticker never guessed, "
                "nothing fabricated".format(query_text))
            continue
        ticker = cik_map.get(cik, "") if cik_map else ""
        if not ticker:
            gaps.append(
                "SEC full-text hit CIK {0} has no ticker mapping ({1!r}) -- honest gap, ticker "
                "never guessed, candidate not fabricated".format(cik, query_text))
            continue
        candidates.append(DiscoveredUniverseCandidate(
            candidate_id=candidate_id_for(ticker),
            ticker=ticker,
            company_name=hit.get("company_name") or "",
            theme_hint=query_text,
            discovery_method=method,
            source_refs=tuple(dict.fromkeys(r for r in (
                "sec:fts/{0}".format(accession) if accession else "",
                "sec:cik/{0}".format(cik),
            ) if r)),
            source_authority="canonical",
            evidence_note=_fts_note(hit, query_text),
            discovered_at=now,
        ))

    deduped = _dedupe(candidates)
    if not deduped and not (rate_limited or unavailable or parse_failed) and not gaps:
        gaps.append(
            "SEC full-text search matched no mappable filers for {0!r} -- visible gap, nothing "
            "fabricated".format(query_text))
    return UniverseDiscoveryResult(
        candidates=deduped, data_gaps=tuple(gaps),
        source_health=((method, _health(
            candidates=bool(deduped), rate_limited=rate_limited, unavailable=unavailable,
            parse_failed=parse_failed, creds_missing=False)),))


# --------------------------------------------------------------------------- #
# Cross-method merge (dedupe canonical > convenience, preserve BOTH refs)        #
# --------------------------------------------------------------------------- #
def merge_universe_discovery(*results: UniverseDiscoveryResult) -> UniverseDiscoveryResult:
    """Merge several producers' results: dedupe candidates by ticker across methods (canonical >
    convenience, BOTH provenance refs preserved), and union source_health + data_gaps."""
    all_candidates: List[DiscoveredUniverseCandidate] = []
    health: List[Tuple[str, str]] = []
    gaps: List[str] = []
    seen_health: Dict[str, str] = {}
    for result in results:
        all_candidates.extend(result.candidates)
        for name, label in result.source_health:
            if name not in seen_health:
                seen_health[name] = label
                health.append((name, label))
        gaps.extend(result.data_gaps)
    return UniverseDiscoveryResult(
        candidates=_dedupe(all_candidates),
        source_health=tuple(health),
        data_gaps=tuple(dict.fromkeys(gaps)),
    )


# --------------------------------------------------------------------------- #
# Payload helpers (raise / None on a malformed payload -> visible gap upstream)  #
# --------------------------------------------------------------------------- #
def _as_rows(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """FMP screener returns a JSON array of rows. None on a payload that is neither array/object."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [payload]
    return None


def _fts_hits(payload: Any) -> List[Dict[str, Any]]:
    """Flatten the EDGAR FTS ``hits.hits`` list into per-filing dicts. Raises on a malformed doc."""
    if not isinstance(payload, dict):
        raise ValueError("SEC full-text payload must be a JSON object")
    outer = payload.get("hits")
    if not isinstance(outer, dict):
        raise ValueError("SEC full-text payload has no hits object")
    inner = outer.get("hits")
    if not isinstance(inner, list):
        raise ValueError("SEC full-text payload has no hits.hits list")
    out: List[Dict[str, Any]] = []
    for hit in inner:
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source") or {}
        if not isinstance(source, dict):
            source = {}
        raw_id = str(hit.get("_id") or "")
        # accession is the leading segment of ``<accession>:<doc>``; ``adsh`` is the same value.
        accession = (raw_id.split(":", 1)[0] if raw_id else "") or str(source.get("adsh") or "")
        display = source.get("display_names") or []
        name = ""
        if isinstance(display, list) and display:
            name = _company_name_from_display(str(display[0]))
        # EDGAR FTS carries the filer CIK(s) in ``ciks`` (a list); the singular ``cik`` is absent.
        raw_ciks = source.get("ciks")
        cik = ""
        if isinstance(raw_ciks, list) and raw_ciks:
            cik = str(raw_ciks[0] or "")
        elif source.get("cik"):
            cik = str(source.get("cik") or "")
        out.append({
            "cik": cik,
            "accession": accession,
            "company_name": name,
            "form": str(source.get("file_type") or source.get("form") or ""),
            "file_date": str(source.get("file_date") or ""),
        })
    return out


def _company_name_from_display(display: str) -> str:
    """"IREN Limited (IREN) (CIK 0001878848)" -> "IREN Limited" (the text before the ticker)."""
    match = _DISPLAY_NAME_TICKER.search(display)
    name = display[:match.start()] if match else display
    return name.strip()


def _fts_note(hit: Dict[str, Any], query_text: str) -> str:
    bits = []
    form = str(hit.get("form") or "").strip()
    if form:
        bits.append("{0} filing".format(form))
    date = str(hit.get("file_date") or "").strip()
    if date:
        bits.append("filed {0}".format(date))
    bits.append("mentions {0!r}".format(query_text))
    return "SEC full-text: " + ", ".join(bits)


def _sec_cik_map(transport: Any, query_text: str) -> Tuple[Dict[str, str], str]:
    """Build a CIK->ticker map from the wired ``company_tickers`` transport. Returns (map, gap)."""
    fetch = transport.get("company_tickers") if isinstance(transport, dict) else None
    if not callable(fetch):
        return {}, ("SEC company_tickers transport not wired: CIK->ticker mapping unavailable "
                    "({0!r}) -- hits recorded as honest gaps, tickers never guessed".format(
                        query_text))
    try:
        payload = fetch()
    except Exception as exc:                # noqa: BLE001 -- failure becomes a gap, never a crash
        return {}, ("SEC company_tickers unavailable ({0}: {1}): CIK->ticker mapping missing -- "
                    "hits recorded as honest gaps, tickers never guessed".format(
                        type(exc).__name__, exc))
    try:
        return _parse_company_tickers(payload), ""
    except Exception as exc:                # noqa: BLE001 -- malformed -> visible gap
        return {}, ("malformed SEC company_tickers payload ({0}: {1}): CIK->ticker mapping "
                    "unavailable -- hits recorded as honest gaps".format(type(exc).__name__, exc))


def _parse_company_tickers(payload: Any) -> Dict[str, str]:
    """Zip company_tickers.json (dict-of-rows or list-of-rows) into padded-CIK -> ticker."""
    if isinstance(payload, dict):
        rows = list(payload.values())
    elif isinstance(payload, list):
        rows = list(payload)
    else:
        raise ValueError("company_tickers payload must be a JSON object or list")
    out: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker", "") or "").strip().upper()
        cik = _pad_cik(row.get("cik_str", row.get("cik", "")))
        if ticker and cik and cik not in out:
            out[cik] = ticker
    if not out:
        raise ValueError("company_tickers payload carried no ticker/CIK rows")
    return out


# --------------------------------------------------------------------------- #
# DEFAULT real transports, built lazily (NO network on import)                  #
# --------------------------------------------------------------------------- #
def _default_fmp_transport(env: Optional[Dict[str, str]]) -> Optional[Callable[..., Any]]:
    """Build the real FMP screener transport lazily. None when FMP_API_KEY is absent (a
    credentials gap -- never a crash/leak). The value transits only into the transport builder and
    is never stored / logged / echoed. NEVER exercised by the offline test suite."""
    import os  # lazy; NOT a network import
    from evidence_ingestion.live_transport import fmp_screener_transport  # lazy boundary
    source = env if env is not None else os.environ
    api_key = str(source.get("FMP_API_KEY", "") or "")
    if not api_key:
        return None
    return fmp_screener_transport(api_key)


def _default_sec_transport(env: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Build the real SEC full-text transport lazily. None when SEC_USER_AGENT is absent (a
    credentials gap -- never a crash/leak). The value transits only into the transport builder and
    is never stored / logged / echoed. NEVER exercised by the offline test suite."""
    import os  # lazy; NOT a network import
    from evidence_ingestion.live_transport import sec_fts_transport  # lazy boundary
    source = env if env is not None else os.environ
    user_agent = str(source.get("SEC_USER_AGENT", "") or "")
    if not user_agent:
        return None
    return sec_fts_transport(user_agent)


# A construction-time self-check: the candidate contract is trade/score-clean.
assert_no_trade_fields(DiscoveredUniverseCandidate)
assert_no_trade_fields(UniverseDiscoveryResult)
