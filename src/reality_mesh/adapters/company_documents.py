"""The Company IR / investor-presentation + earnings-transcript adapter (IMPLEMENTATION-014C).

:class:`CompanyDocumentsAdapter` reads OPERATOR-DROPPED local JSON extracts of company IR
documents from ``data_dir/<TICKER>/`` -- an investor-presentation / IR-deck extract
(``ir_deck.json``, alias ``investor_presentation.json``) and earnings-call transcripts
(``transcript_<period>.json``) -- and emits :class:`~reality_mesh.models.RealityEvent`s ONLY,
per ``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013``. Phase-014 priorities #6-#7.

THE ONE RULE THAT GOVERNS THIS SOURCE (contract §3, verbatim: "company IR = company_claim
unless independently verified"):

* **Everything a company says about itself is a ``company_claim`` -- NEVER a
  ``verified_fact``.** IR-deck claims, numeric guidance, TAM statements, customer / supplier
  / leadership mentions, prepared remarks, and a company speaker's Q&A answers are all
  stamped ``claim_status="company_claim"`` with the statement carried in the event's
  ``company_claim`` field. No path in this module can produce a ``verified_fact``.
* **Authority is ``primary`` throughout** -- company IR is primary-BUT-CLAIM on the accepted
  ladder. Nothing here is ever ``canonical`` (only an SEC filing fact is; see 014B).
* **An analyst's question / commentary inside a transcript is NOT the company speaking**:
  it is stamped ``reported_claim`` (or ``analyst_estimate`` when the entry is explicitly an
  estimate) and never populates the ``company_claim`` field. An UNKNOWN speaker role is
  treated conservatively as ``reported_claim`` with a visible per-event gap -- never assumed
  to be the company.
* **TAM discipline**: a TAM / market-size statement stays a ``company_claim`` AND carries the
  explicit per-event data gap :data:`TAM_NOT_INDEPENDENTLY_VERIFIED_GAP` ("company-stated
  TAM -- not independently verified") -- a company's market-size figure is never adopted.
* **Numeric guidance carries units**: a guidance figure becomes a ``numeric_values`` entry
  ``(metric, value, unit)``; a figure WITHOUT a unit is NOT emitted as a number (a bare
  number is not a reading) -- the statement still flows as a claim and the absence is a
  visible per-event gap, never a fabricated unit.

LOCAL FILES ONLY (onboarding stage 2 of contract §4): ``network_required=False``, NO
credential (``credentials_status="not_required"``), NO rate limit (a filesystem read is
``ok`` by construction). A MISSING ticker directory / document or a MALFORMED file becomes a
visible gap / ``parse_error`` NAMING the path -- never a crash, never a fabricated value,
never a silent demo fallback. A STALE ``as_of`` (older than :data:`DOCUMENT_STALE_AFTER_DAYS`
versus the injected ``now``) marks every event from that document ``freshness_label="stale"``
(preserved, never dropped, never silently refreshed).

CONSUMERS. ``news_filings`` consumes the deck-claim / guidance / transcript events today;
``customer_evidence`` / ``supplier_evidence`` / ``leadership_evidence`` have registered
descriptors but NO sensor implementation in this slice, so their events flow to the event
store / Data Quality as evidence with the honest per-discipline consumer gap
(:data:`DESCRIPTOR_ONLY_CONSUMER_GAPS`) -- mirroring 014B's financial_inflection gap.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Ids and ``raw_payload_ref``s are
content-derived (sha256); ``now`` is an injected string (no wall-clock anywhere).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)
# Reuse the audited 014A ISO parser -- timestamp parsing rules live in exactly one place.
from .local_market_data import _parse_iso

__all__ = [
    "COMPANY_DOCUMENTS_ADAPTER_ID",
    "COMPANY_DOCUMENTS_DESCRIPTOR",
    "COMPANY_DOCUMENTS_DISCIPLINES",
    "IR_DECK_FILENAMES",
    "TRANSCRIPT_FILE_PREFIX",
    "DOCUMENT_STALE_AFTER_DAYS",
    "TAM_NOT_INDEPENDENTLY_VERIFIED_GAP",
    "DESCRIPTOR_ONLY_CONSUMER_GAPS",
    "CompanyDocumentsAdapter",
]

COMPANY_DOCUMENTS_ADAPTER_ID = "evidence.company_documents"

# The disciplines this adapter is the source for. news_filings has a real sensor today; the
# three evidence disciplines are descriptor-only consumers in this slice (honest gap below).
COMPANY_DOCUMENTS_DISCIPLINES: Tuple[str, ...] = (
    "news_filings",
    "customer_evidence",
    "supplier_evidence",
    "leadership_evidence",
)

# The operator-dropped files read from ``data_dir/<TICKER>/``. The deck extract is read from
# the FIRST of these names present; transcripts are every ``transcript_*.json`` in the dir.
IR_DECK_FILENAMES: Tuple[str, ...] = ("ir_deck.json", "investor_presentation.json")
TRANSCRIPT_FILE_PREFIX = "transcript_"

# A document whose ``as_of`` is older than this (versus the injected ``now``) has ALL its
# events marked stale. ~One quarter: an IR deck / transcript older than a reporting cycle is
# not a current statement of the company's position.
DOCUMENT_STALE_AFTER_DAYS = 120

# The accepted TAM discipline (memory: TAM-not-invented): a company's own market-size figure
# travels as its claim WITH this explicit per-event gap -- it is never adopted as a fact.
TAM_NOT_INDEPENDENTLY_VERIFIED_GAP = (
    "company-stated TAM -- not independently verified (a TAM / market-size figure in an IR "
    "document is the company's own claim, never adopted as a fact)")

# The honest note that travels with every delivery into a descriptor-only consumer: the
# discipline has a registered tattva.* descriptor but NO sensor implementation in this slice,
# so its events land in the event store / Data Quality as evidence WITHOUT a finding
# (mirrors 014B's FINANCIAL_INFLECTION_CONSUMER_GAP).
_CONSUMER_GAP_TEMPLATE = (
    "{0} sensor is descriptor-only in this slice: tattva.{0} has a registered descriptor "
    "but no sensor implementation, so {1} events flow to the event store / Data Quality as "
    "evidence without interpretation -- visible gap, no finding fabricated")
DESCRIPTOR_ONLY_CONSUMER_GAPS: Dict[str, str] = {
    "customer_evidence": _CONSUMER_GAP_TEMPLATE.format(
        "customer_evidence", "customer_mention"),
    "supplier_evidence": _CONSUMER_GAP_TEMPLATE.format(
        "supplier_evidence", "supplier_mention"),
    "leadership_evidence": _CONSUMER_GAP_TEMPLATE.format(
        "leadership_evidence", "leadership_statement"),
}

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
COMPANY_DOCUMENTS_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=COMPANY_DOCUMENTS_ADAPTER_ID,
    source_name="Company IR documents (investor presentations + earnings transcripts, "
                "operator-dropped local extracts)",
    source_type="company_ir",
    source_authority="primary",             # company IR: primary-but-claim, NEVER canonical
    credential_requirements=(),             # local files: NO credential (env or otherwise)
    network_required=False,                 # LOCAL FILES ONLY -- no network path exists here
    rate_limit_policy="not_applicable: local filesystem read, no remote quota",
    outputs=(
        "ir_deck_claim",
        "guidance_statement",
        "transcript_remark",
        "transcript_qa",
        "customer_mention",
        "supplier_mention",
        "leadership_statement",
    ),
    claim_status_rules=(
        "everything the company says about itself (deck claims, guidance, TAM statements, "
        "customer / supplier / leadership mentions, prepared remarks, company Q&A answers) "
        "-> claim_status=company_claim with the statement in the company_claim field -- "
        "NEVER a verified_fact, however confident the document sounds",
        "analyst question / commentary inside a transcript -> claim_status=reported_claim "
        "(analyst_estimate when explicitly an estimate); an unknown speaker role is treated "
        "as reported_claim with a visible gap -- never assumed to be the company",
        "TAM / market-size statement -> company_claim PLUS the explicit per-event gap "
        "'company-stated TAM -- not independently verified' (TAM is never invented or "
        "adopted from the company's own figure)",
        "numeric guidance -> numeric_values (metric, value, unit) at company_claim; a "
        "figure without a unit is not emitted as a number (visible gap, nothing fabricated)",
        "source_authority=primary is assigned immediately on every record: company IR is "
        "primary-but-claim on the accepted ladder and is never promoted to canonical",
    ),
    failure_modes=("source_unavailable", "parse_error"),
    description="Operator-dropped local extracts of company investor presentations and "
                "earnings-call transcripts feeding the News/Filings sensor today and the "
                "(descriptor-only) customer / supplier / leadership evidence consumers. "
                "Offline; no scheduler; no broker; labels not scores.",
)

# Speaker-role tokens that mark a transcript speaker as THE COMPANY (substring match on the
# lowercased role, after the analyst check). Exact-match extras cover the short labels a
# substring match would over-trigger on.
_COMPANY_ROLE_SUBSTRINGS: Tuple[str, ...] = (
    "ceo", "cfo", "coo", "cto", "chief", "chair", "president", "founder", "executive",
    "officer", "evp", "svp", "treasurer", "general counsel", "investor relations",
)
_COMPANY_ROLE_EXACT = frozenset({"company", "management", "ir"})

_HALF_LIFE_BY_EVENT_TYPE = {
    "ir_deck_claim": "months",
    "guidance_statement": "quarters",
    "transcript_remark": "months",
    "transcript_qa": "months",
    "customer_mention": "months",
    "supplier_mention": "months",
    "leadership_statement": "months",
}

_STATUS_TO_HEALTH = {
    "success": "healthy",
    "partial": "degraded",
    "failed": "failed",
    "skipped": "source_unavailable",
}


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _normalise_tickers(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens."""
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _is_stale(as_of: str, now: str) -> bool:
    """True iff ``as_of`` is more than DOCUMENT_STALE_AFTER_DAYS older than ``now``.

    Deterministic: purely a comparison of the two injected strings -- no wall-clock. An
    absent / unparsable timestamp on either side reads False (the caller surfaces a warning
    for an unparsable ``as_of`` -- staleness is never guessed).
    """
    as_of_dt = _parse_iso(as_of)
    now_dt = _parse_iso(now)
    if as_of_dt is None or now_dt is None:
        return False
    return (now_dt - as_of_dt) > _dt.timedelta(days=DOCUMENT_STALE_AFTER_DAYS)


def _text_of(entry: Dict[str, Any], *keys: str) -> str:
    """The first non-empty text among ``keys`` on ``entry`` (stripped; '' if none)."""
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _speaker_claim(role: str, kind: str) -> Tuple[str, str]:
    """Resolve ``(claim_status, gap_note)`` for one transcript speaker -- WITHOUT laundering.

    * analyst -> ``reported_claim`` (``analyst_estimate`` when the entry is explicitly an
      estimate); the company_claim field stays empty -- an analyst is not the company.
    * a company role (CEO / CFO / chair / executive / IR ...) -> ``company_claim``.
    * unknown / missing role -> ``reported_claim`` + a visible gap note: a speaker is never
      ASSUMED to be the company.
    """
    role_l = (role or "").strip().lower()
    kind_l = (kind or "").strip().lower()
    if "analyst" in role_l or kind_l in ("question", "analyst_question"):
        claim = "analyst_estimate" if kind_l == "estimate" else "reported_claim"
        return claim, ""
    if role_l in _COMPANY_ROLE_EXACT or any(
            token in role_l for token in _COMPANY_ROLE_SUBSTRINGS):
        return "company_claim", ""
    return "reported_claim", (
        "speaker role {0!r} not recognised as the company: statement treated as "
        "reported_claim, NOT a company_claim -- surfaced, never assumed".format(role or ""))


# --------------------------------------------------------------------------- #
# CompanyDocumentsAdapter                                                       #
# --------------------------------------------------------------------------- #
class CompanyDocumentsAdapter(SourceAdapter):
    """Operator-dropped LOCAL company IR extracts -> RealityEvents. Offline; honest gaps.

    ``data_dir/<TICKER>/`` holds one IR-deck extract (``ir_deck.json`` or
    ``investor_presentation.json``) and any number of ``transcript_<period>.json`` files.
    Everything the company says is a ``company_claim`` at ``primary`` authority -- never a
    verified fact, never canonical.
    """

    def __init__(self, data_dir: str) -> None:
        if not isinstance(data_dir, str) or data_dir.strip() == "":
            raise ValueError("CompanyDocumentsAdapter requires a non-empty data_dir")
        self._data_dir = data_dir

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return COMPANY_DOCUMENTS_DESCRIPTOR

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The disciplines this adapter sources. A consumer takes these from the adapter
        ONLY -- a missing/failed document stays a visible gap, never a fixture fallback."""
        return COMPANY_DOCUMENTS_DISCIPLINES

    # -- fetch ---------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Read each ticker's IR documents under ``data_dir/<TICKER>/`` into RealityEvents
        plus an honest result.

        Deterministic + offline: reads the local filesystem only. A missing ticker directory
        / document or a malformed file becomes an explicit error/gap NAMING it -- never a
        crash, never a fabricated value, never a silent demo fallback.
        """
        state = {"parse_failed": False, "missing": 0}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        tickers = _normalise_tickers(watchlist)
        if not tickers:
            gaps.append(
                "empty watchlist: the company-documents adapter reads per-ticker IR files "
                "and was given no tickers -- nothing read, nothing fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, now)

        if not os.path.isdir(self._data_dir):
            errors.append(
                "source_unavailable: data_dir not found: {0}".format(self._data_dir))
            for ticker in tickers:
                gaps.append(
                    "missing company-documents directory {0}: ticker {1} has NO company "
                    "IR coverage this run -- visible gap, never fabricated, no silent demo "
                    "fallback".format(os.path.join(self._data_dir, ticker), ticker))
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        for ticker in tickers:
            ticker_dir = os.path.join(self._data_dir, ticker)
            if not os.path.isdir(ticker_dir):
                state["missing"] += 1
                gaps.append(
                    "missing ticker directory {0}: ticker {1} has NO company IR coverage "
                    "this run -- visible gap, never fabricated, no silent demo "
                    "fallback".format(ticker_dir, ticker))
                continue
            self._read_deck(ticker, ticker_dir, events, refs, warnings, errors, gaps,
                            state, now)
            self._read_transcripts(ticker, ticker_dir, events, refs, warnings, errors,
                                   gaps, state, now)

        # Honest consumer gaps: a delivery into a descriptor-only discipline is evidence
        # without interpretation this slice (mirrors 014B's financial_inflection gap).
        delivered = {e.discipline for e in events}
        for discipline in sorted(DESCRIPTOR_ONLY_CONSUMER_GAPS):
            if discipline in delivered:
                gaps.append(DESCRIPTOR_ONLY_CONSUMER_GAPS[discipline])

        problems = state["parse_failed"] or state["missing"] > 0
        if events:
            status = "partial" if problems else "success"
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "company IR documents under {0} delivered no events -- visible gap, "
                "nothing fabricated".format(self._data_dir))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, now)

    # -- one local file: bytes -> sha256 ref -> parsed JSON object -------------- #
    def _load_document(self, ticker: str, path: str, refs: List[str], errors: List[str],
                       gaps: List[str], state: Dict[str, int]) -> Tuple[Optional[Dict], str]:
        """Read + parse one document. Returns ``(doc, ref)``; ``doc`` is None on parse error
        (already surfaced as a visible ``parse_error`` naming the file)."""
        name = "{0}/{1}".format(ticker, os.path.basename(path))
        with open(path, "rb") as fh:
            raw = fh.read()
        ref = "localfile:{0}#sha256={1}".format(
            name, hashlib.sha256(raw).hexdigest()[:16])
        refs.append(ref)
        try:
            doc = json.loads(raw.decode("utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("a company IR document must be a JSON object")
        except Exception as exc:  # malformed file -> parse_error, NEVER fabricated events
            state["parse_failed"] = True
            errors.append("parse_error: {0}: {1}: {2}".format(
                name, type(exc).__name__, exc))
            gaps.append(
                "malformed company IR document {0} (parse_error): its statements have NO "
                "coverage this run -- visible gap, nothing fabricated".format(name))
            return None, ref
        return doc, ref

    def _freshness(self, doc: Dict, name: str, now: str,
                   warnings: List[str]) -> Tuple[bool, str]:
        """Assess document staleness from its ``as_of`` versus the injected ``now``."""
        as_of = str(doc.get("as_of", "") or "")
        if as_of and now and _parse_iso(as_of) is None:
            warnings.append(
                "unparsable as_of {0!r} in {1}: staleness cannot be assessed -- surfaced, "
                "not guessed".format(as_of, name))
        stale = _is_stale(as_of, now)
        if stale:
            warnings.append(
                "stale as_of {0} in {1} (now {2}, threshold {3} days): all its events "
                "marked stale -- preserved, never dropped, never silently "
                "refreshed".format(as_of, name, now, DOCUMENT_STALE_AFTER_DAYS))
        return stale, as_of

    # -- the IR deck / investor presentation ------------------------------------ #
    def _read_deck(self, ticker: str, ticker_dir: str, events: List[RealityEvent],
                   refs: List[str], warnings: List[str], errors: List[str],
                   gaps: List[str], state: Dict[str, int], now: str) -> None:
        path = ""
        for filename in IR_DECK_FILENAMES:
            candidate = os.path.join(ticker_dir, filename)
            if os.path.isfile(candidate):
                path = candidate
                break
        if not path:
            state["missing"] += 1
            gaps.append(
                "missing IR deck extract for {0} (no {1}): investor-presentation claims "
                "have NO coverage this run -- visible gap, never fabricated, no silent "
                "demo fallback".format(ticker, " / ".join(IR_DECK_FILENAMES)))
            return
        doc, ref = self._load_document(ticker, path, refs, errors, gaps, state)
        if doc is None:
            return
        name = "{0}/{1}".format(ticker, os.path.basename(path))
        stale, as_of = self._freshness(doc, name, now, warnings)
        base = dict(ticker=ticker, name=name, ref=ref, as_of=as_of, now=now, stale=stale,
                    source_type="company_ir_deck")

        for index, entry in enumerate(self._entries(doc, "claims", name, errors, gaps,
                                                    state)):
            text = _text_of(entry, "claim", "statement", "text")
            if not text:
                self._reject_entry(name, "claims", index, "missing claim text",
                                   errors, gaps, state)
                continue
            events.append(self._event(
                event_type="ir_deck_claim", discipline="news_filings",
                section="claims[{0}]".format(index), slide=entry.get("slide"),
                observed_fact="IR deck claim: {0}".format(text),
                claim_status="company_claim", company_claim=text, **base))

        for index, entry in enumerate(self._entries(doc, "guidance", name, errors, gaps,
                                                    state)):
            event = self._guidance_event(entry, index, base, name, errors, gaps, state)
            if event is not None:
                events.append(event)

        for index, entry in enumerate(self._entries(doc, "tam_statements", name, errors,
                                                    gaps, state)):
            event = self._tam_event(entry, index, base, name, errors, gaps, state)
            if event is not None:
                events.append(event)

        for list_name, event_type, discipline, label in (
                ("customer_mentions", "customer_mention", "customer_evidence",
                 "customer mention in IR deck"),
                ("supplier_mentions", "supplier_mention", "supplier_evidence",
                 "supplier / partner mention in IR deck"),
                ("partner_mentions", "supplier_mention", "supplier_evidence",
                 "supplier / partner mention in IR deck"),
                ("leadership_statements", "leadership_statement", "leadership_evidence",
                 "leadership statement in IR deck")):
            for index, entry in enumerate(self._entries(doc, list_name, name, errors,
                                                        gaps, state)):
                text = _text_of(entry, "statement", "claim", "text")
                who = _text_of(entry, "name", "speaker")
                if not text and not who:
                    self._reject_entry(name, list_name, index, "missing statement/name",
                                       errors, gaps, state)
                    continue
                fact = "{0}: {1}".format(
                    label, text or "{0} named".format(who))
                events.append(self._event(
                    event_type=event_type, discipline=discipline,
                    section="{0}[{1}]".format(list_name, index),
                    slide=entry.get("slide"), observed_fact=fact,
                    claim_status="company_claim", company_claim=text or fact, **base))

    def _guidance_event(self, entry: Dict, index: int, base: Dict, name: str,
                        errors: List[str], gaps: List[str],
                        state: Dict[str, int]) -> Optional[RealityEvent]:
        statement = _text_of(entry, "statement", "claim", "text")
        metric = _text_of(entry, "metric")
        if not statement and not metric:
            self._reject_entry(name, "guidance", index, "missing statement and metric",
                               errors, gaps, state)
            return None
        value = entry.get("value")
        unit = _text_of(entry, "unit")
        numeric: Tuple[Tuple[str, object, str], ...] = ()
        event_gaps: List[str] = []
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                self._reject_entry(
                    name, "guidance", index,
                    "non-numeric guidance value {0!r}".format(value), errors, gaps, state)
                return None
            if metric and unit:
                numeric = ((metric, value, unit),)
            else:
                # A bare number is not a reading: the statement still flows as the
                # company's claim; the figure is NOT emitted -- visible gap, no unit invented.
                event_gaps.append(
                    "guidance figure in {0} guidance[{1}] has no {2}: the number is not "
                    "emitted as a reading -- visible gap, nothing fabricated".format(
                        name, index, "unit" if metric else "metric name"))
        fact = "guidance statement: {0}".format(statement or metric)
        period = _text_of(entry, "period")
        if period:
            fact += " (period {0})".format(period)
        return self._event(
            event_type="guidance_statement", discipline="news_filings",
            section="guidance[{0}]".format(index), slide=entry.get("slide"),
            observed_fact=fact, claim_status="company_claim",
            company_claim=statement or fact, numeric_values=numeric,
            extra_gaps=tuple(event_gaps), **base)

    def _tam_event(self, entry: Dict, index: int, base: Dict, name: str,
                   errors: List[str], gaps: List[str],
                   state: Dict[str, int]) -> Optional[RealityEvent]:
        statement = _text_of(entry, "statement", "claim", "text")
        if not statement:
            self._reject_entry(name, "tam_statements", index, "missing statement text",
                               errors, gaps, state)
            return None
        value = entry.get("value")
        unit = _text_of(entry, "unit")
        numeric: Tuple[Tuple[str, object, str], ...] = ()
        event_gaps: List[str] = [TAM_NOT_INDEPENDENTLY_VERIFIED_GAP]
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                self._reject_entry(
                    name, "tam_statements", index,
                    "non-numeric TAM value {0!r}".format(value), errors, gaps, state)
                return None
            if unit:
                numeric = (("company_stated_tam", value, unit),)
            else:
                event_gaps.append(
                    "TAM figure in {0} tam_statements[{1}] has no unit: the number is not "
                    "emitted as a reading -- visible gap, nothing fabricated".format(
                        name, index))
        return self._event(
            event_type="ir_deck_claim", discipline="news_filings",
            section="tam_statements[{0}]".format(index), slide=entry.get("slide"),
            observed_fact="TAM statement (company-stated): {0}".format(statement),
            claim_status="company_claim", company_claim=statement,
            numeric_values=numeric, extra_gaps=tuple(event_gaps), **base)

    # -- earnings transcripts ----------------------------------------------------- #
    def _read_transcripts(self, ticker: str, ticker_dir: str,
                          events: List[RealityEvent], refs: List[str],
                          warnings: List[str], errors: List[str], gaps: List[str],
                          state: Dict[str, int], now: str) -> None:
        names = sorted(
            n for n in os.listdir(ticker_dir)
            if n.startswith(TRANSCRIPT_FILE_PREFIX) and n.endswith(".json")
            and os.path.isfile(os.path.join(ticker_dir, n)))
        if not names:
            state["missing"] += 1
            gaps.append(
                "missing earnings transcript for {0} (no {1}<period>.json): transcript "
                "statements have NO coverage this run -- visible gap, never fabricated, "
                "no silent demo fallback".format(ticker, TRANSCRIPT_FILE_PREFIX))
            return
        for filename in names:
            doc, ref = self._load_document(
                ticker, os.path.join(ticker_dir, filename), refs, errors, gaps, state)
            if doc is None:
                continue
            name = "{0}/{1}".format(ticker, filename)
            stale, as_of = self._freshness(doc, name, now, warnings)
            period = _text_of(doc, "period") or filename[
                len(TRANSCRIPT_FILE_PREFIX):-len(".json")]
            base = dict(ticker=ticker, name=name, ref=ref, as_of=as_of, now=now,
                        stale=stale, source_type="earnings_transcript")

            for index, entry in enumerate(self._entries(
                    doc, "prepared_remarks", name, errors, gaps, state)):
                event = self._transcript_event(
                    entry, "transcript_remark", "prepared_remarks", index, period,
                    base, name, errors, gaps, state)
                if event is not None:
                    events.append(event)
            for index, entry in enumerate(self._entries(
                    doc, "qa", name, errors, gaps, state)):
                event = self._transcript_event(
                    entry, "transcript_qa", "qa", index, period,
                    base, name, errors, gaps, state)
                if event is not None:
                    events.append(event)

    def _transcript_event(self, entry: Dict, event_type: str, list_name: str, index: int,
                          period: str, base: Dict, name: str, errors: List[str],
                          gaps: List[str],
                          state: Dict[str, int]) -> Optional[RealityEvent]:
        text = _text_of(entry, "text", "statement")
        if not text:
            self._reject_entry(name, list_name, index, "missing text", errors, gaps, state)
            return None
        speaker = _text_of(entry, "speaker")
        role = _text_of(entry, "role")
        kind = _text_of(entry, "kind")
        claim_status, role_gap = _speaker_claim(role, kind)
        who = " ".join(p for p in (role, speaker) if p) or "unattributed speaker"
        section = _text_of(entry, "section")
        part = ("prepared remarks" if event_type == "transcript_remark"
                else "Q&A {0}".format(kind or "exchange"))
        fact = "earnings call {0} {1}{2} ({3}): {4}".format(
            period, part, " [{0}]".format(section) if section else "", who, text)
        extra_gaps: List[str] = []
        if role_gap:
            extra_gaps.append(role_gap)
        return self._event(
            event_type=event_type, discipline="news_filings",
            section="{0}[{1}]".format(list_name, index), slide=None,
            observed_fact=fact, claim_status=claim_status,
            # ONLY a company speaker's words populate company_claim -- an analyst's (or an
            # unknown speaker's) words are never marked as the company's statement.
            company_claim=text if claim_status == "company_claim" else "",
            extra_gaps=tuple(extra_gaps), **base)

    # -- shared builders ------------------------------------------------------------ #
    def _entries(self, doc: Dict, key: str, name: str, errors: List[str],
                 gaps: List[str], state: Dict[str, int]) -> List[Dict]:
        """The list ``doc[key]`` with every non-object element rejected as a parse error."""
        value = doc.get(key)
        if value is None:
            return []
        if not isinstance(value, list):
            self._reject_entry(name, key, "-", "must be a list of objects",
                               errors, gaps, state)
            return []
        out: List[Dict] = []
        for index, entry in enumerate(value):
            if isinstance(entry, dict):
                out.append(entry)
            else:
                self._reject_entry(name, key, index, "entry must be a JSON object",
                                   errors, gaps, state)
        return out

    def _reject_entry(self, name: str, list_name: str, index, reason: str,
                      errors: List[str], gaps: List[str], state: Dict[str, int]) -> None:
        state["parse_failed"] = True
        errors.append("parse_error: {0} {1}[{2}]: {3}".format(
            name, list_name, index, reason))
        gaps.append(
            "invalid entry {0}[{1}] in {2} rejected (parse_error) -- surfaced, never "
            "silently repaired".format(list_name, index, name))

    def _event(self, *, ticker: str, name: str, ref: str, as_of: str, now: str,
               stale: bool, source_type: str, event_type: str, discipline: str,
               section: str, slide, observed_fact: str, claim_status: str,
               company_claim: str,
               numeric_values: Tuple[Tuple[str, object, str], ...] = (),
               extra_gaps: Tuple[str, ...] = ()) -> RealityEvent:
        """One provenance-stamped RealityEvent from one document section.

        Authority is ``primary`` on EVERY record (assigned immediately, never canonical);
        the claim status was resolved by the caller and is never ``verified_fact``.
        """
        excerpt = "companydoc:{0}#{1}".format(name, section)
        if slide is not None:
            excerpt += "@slide={0}".format(slide)
        return RealityEvent(
            event_id="companydocs.{0}.{1}.{2}".format(
                ticker.lower(), event_type,
                _sha12(ticker, name, section, observed_fact)),
            timestamp=as_of or now,
            source_id="company_ir",
            source_type=source_type,
            source_authority="primary",         # company IR: primary-but-claim, NEVER canonical
            claim_status=claim_status,
            raw_payload_ref=ref,
            discipline=discipline,
            event_type=event_type,
            affected_companies=(ticker,),
            observed_fact=observed_fact,
            company_claim=company_claim,
            numeric_values=numeric_values,
            text_excerpt_refs=(excerpt,),
            evidence_refs=(excerpt,),
            source_refs=(ref,),
            confidence_label="moderate",
            freshness_label="stale" if stale else "recent",
            half_life=_HALF_LIFE_BY_EVENT_TYPE[event_type],
            data_gaps=extra_gaps,
        )

    # -- result builder --------------------------------------------------------------- #
    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                now: str) -> SourceAdapterResult:
        run_id = deterministic_adapter_run_id(
            COMPANY_DOCUMENTS_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=COMPANY_DOCUMENTS_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="not_required",   # local files: no credential exists to check
            rate_limit_status="ok",              # a local filesystem read cannot be throttled
            source_health=_STATUS_TO_HEALTH[status])
