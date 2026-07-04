"""The four company-evidence sensor agents for the Reality Mesh (IMPLEMENTATION-014F).

:class:`CustomerEvidenceAgent`, :class:`SupplierEvidenceAgent`,
:class:`BottleneckEvidenceAgent`, and :class:`LeadershipEvidenceAgent` consume the
company-document :class:`~reality_mesh.models.RealityEvent`s the 014C
:class:`~reality_mesh.adapters.company_documents.CompanyDocumentsAdapter` ALREADY emits and
produce ``CustomerEvidenceFinding`` / ``SupplierEvidenceFinding`` /
``BottleneckEvidenceFinding`` / ``LeadershipEvidenceFinding``s (each an
:class:`~reality_mesh.models.AgentFinding` in its own discipline). Each agent reuses its
built-in ``tattva.*`` descriptor (AGENT_MAP_012 §3.3) and passes
:meth:`~reality_mesh.agents.SensorAgent.run_checked`.

WHAT EACH AGENT CONSUMES (the 014C event routing):

* ``customer_mention`` events (stamped ``customer_evidence`` discipline) -> Customer.
* ``supplier_mention`` events (stamped ``supplier_evidence`` discipline) -> Supplier.
* ``leadership_statement`` events (stamped ``leadership_evidence`` discipline) PLUS
  ``ir_deck_claim`` deck claims (stamped ``news_filings`` by 014C) whose text reads on
  leadership topics -> Leadership. The agent filters news_filings input by EVENT TYPE +
  content and emits in ITS OWN discipline, referencing the input events.
* 014C emits NO bottleneck-discipline event, so Bottleneck reads capacity / lead-time /
  shortage statements out of the same company documents: ``ir_deck_claim`` /
  ``guidance_statement`` / ``transcript_remark`` / ``transcript_qa`` events (stamped
  ``news_filings`` by 014C) filtered by event type + content, emitted in the
  ``bottleneck_evidence`` discipline with the input events referenced.

THE CLAIM DISCIPLINE (the 012G ``claim_status=`` stamping pattern, contract §C):

* **A company-sourced statement STAYS a ``company_claim``** -- the source claim status is
  stamped verbatim into every ``finding_summary`` (readable via
  :func:`reality_mesh.sensors.news_filings.claim_status_of`) and an evidence sensor NEVER
  upgrades a company claim to a fact. There is NO path in this module that stamps
  ``verified_fact``.
* an analyst's transcript content stays ``reported_claim`` / ``analyst_estimate``.
* **company-stated capacity carries the explicit gap**
  :data:`COMPANY_STATED_CAPACITY_GAP` ("company-stated ... not independently verified") --
  the 014C TAM technique applied to capacity / lead-time figures.
* concentration / dependency / credibility reads are LABELS -- qualitative evidence
  states, never a score, never an instruction to act.

Deterministic, stdlib-only, Python 3.9, OFFLINE. No network on import; ids are
content-derived; no wall-clock anywhere. No scheduler / broker / score.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS

__all__ = [
    "COMPANY_DOCUMENT_TEXT_EVENT_TYPES",
    "COMPANY_STATED_CAPACITY_GAP",
    "CUSTOMER_EVIDENCE_FINDING_TYPES",
    "SUPPLIER_EVIDENCE_FINDING_TYPES",
    "BOTTLENECK_EVIDENCE_FINDING_TYPES",
    "LEADERSHIP_EVIDENCE_FINDING_TYPES",
    "CustomerEvidenceAgent",
    "SupplierEvidenceAgent",
    "BottleneckEvidenceAgent",
    "LeadershipEvidenceAgent",
    "has_bottleneck_evidence_events",
]

# The 014C company-document event types that carry free text an evidence sensor may read
# (all stamped ``news_filings`` discipline by the adapter).
COMPANY_DOCUMENT_TEXT_EVENT_TYPES: Tuple[str, ...] = (
    "ir_deck_claim",
    "guidance_statement",
    "transcript_remark",
    "transcript_qa",
)

# The 014C TAM technique applied to capacity: a company's own capacity / lead-time figure
# travels as its claim WITH this explicit per-finding gap -- never adopted as a fact.
COMPANY_STATED_CAPACITY_GAP = (
    "company-stated capacity / lead-time -- not independently verified (a capacity, "
    "lead-time, or utilization figure in a company document is the company's own claim, "
    "never adopted as a fact)")

# Finding types per agent -- qualitative evidence LABELS, never a trade / score.
CUSTOMER_EVIDENCE_FINDING_TYPES: Tuple[str, ...] = (
    "customer_win_claim",
    "adoption_signal",
    "concentration_note",
)
SUPPLIER_EVIDENCE_FINDING_TYPES: Tuple[str, ...] = (
    "supplier_dependency",
    "substitution_risk",
)
BOTTLENECK_EVIDENCE_FINDING_TYPES: Tuple[str, ...] = (
    "capacity_expansion_claim",
    "lead_time_note",
    "shortage_evidence",
)
LEADERSHIP_EVIDENCE_FINDING_TYPES: Tuple[str, ...] = (
    "execution_track_record_note",
    "capital_allocation_note",
    "credibility_flag",
    "dilution_history_note",
)

# Claim statuses that mark a statement as COMPANY-SOURCED (never upgraded to a fact).
_COMPANY_SOURCED = ("company_claim",)

_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _sha8(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _text_of(event: RealityEvent) -> str:
    """The lowercased searchable text of one company-document event."""
    return "{0} {1}".format(event.observed_fact or "", event.company_claim or "").lower()


def _matches(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _claim_of(event: RealityEvent) -> Tuple[str, str]:
    """Resolve ``(claim_status, source_authority)`` for a finding -- NEVER upgrading.

    The source claim status passes through UNCHANGED (a company_claim stays a
    company_claim; an analyst's reported_claim / analyst_estimate stays what it is) --
    there is no upgrade path to ``verified_fact`` here. A company-sourced statement is
    capped at ``primary`` authority (company IR is primary-but-claim, never canonical).
    """
    claim = (event.claim_status or "").strip() or "reported_claim"
    authority = event.source_authority or "convenience"
    if claim in _COMPANY_SOURCED and authority == "canonical":
        authority = "primary"
    return claim, authority


def _weakest_freshness(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.freshness_label for e in events if e.freshness_label in _FRESHNESS_REAL_ORDER]
    if not present:
        return "missing"
    return min(present, key=lambda v: _FRESHNESS_REAL_ORDER.index(v))


def _weakest_confidence(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.confidence_label for e in events
               if e.confidence_label not in ("", "missing")]
    if not present:
        return "moderate"
    return min(present, key=lambda v: _CONFIDENCE_ORDER.index(v)
               if v in _CONFIDENCE_ORDER else len(_CONFIDENCE_ORDER))


def _stale_note(events: Tuple[RealityEvent, ...]) -> Optional[str]:
    stale_ids = sorted(e.event_id for e in events if e.freshness_label in _FRESHNESS_STALE)
    if stale_ids:
        return "stale company-document data preserved (not dropped): {0}".format(
            ", ".join(stale_ids))
    return None


def _is_company_document_text_event(event: RealityEvent) -> bool:
    """True iff ``event`` is a 014C free-text company-document event (news_filings side)."""
    return (event.discipline == "news_filings"
            and event.event_type in COMPANY_DOCUMENT_TEXT_EVENT_TYPES)


# --------------------------------------------------------------------------- #
# Content patterns (regex on the lowercased event text)                         #
# --------------------------------------------------------------------------- #
_CUSTOMER_CONCENTRATION = (r"\bconcentrat", r"largest customer", r"top customer",
                           r"% of revenue", r"of total revenue", r"of revenue\b")
_CUSTOMER_WIN = (r"\bwin\b", r"\bwon\b", r"\bsigned\b", r"\bawarded\b", r"\bselected\b",
                 r"design win", r"contract\b")
_CUSTOMER_ADOPTION_STRONG = (r"\bbacklog\b", r"\bdeployment", r"\badoption\b",
                             r"\bexpanded\b", r"\bramping\b", r"purchase commitment")

_SUPPLIER_SUBSTITUTION = (r"\bsubstitut", r"second[- ]sourc", r"alternative supplier",
                          r"qualify(ing)? additional", r"\bswitch(ing)?\b",
                          r"\bdual[- ]sourc")
_SUPPLIER_DEPENDENCY_STRONG = (r"\bsole\b", r"single[- ]sourc", r"\bdepend",
                               r"\brelian", r"\brelies\b", r"priority allocation",
                               r"\bexclusive\b")

_BOTTLENECK_LEAD_TIME = (r"lead[- ]time",)
_BOTTLENECK_SHORTAGE = (r"\bshortage", r"\bconstrain", r"\bsold out\b",
                        r"supply (remains )?tight", r"\bon allocation\b",
                        r"\bundersuppl")
_BOTTLENECK_CAPACITY = (r"\bcapacity\b", r"\bexpansion\b", r"\benergiz", r"\bmegawatt",
                        r"\bfab\b", r"\butilization\b", r"\bramp(ing|ed)?\b",
                        r"\bthroughput\b")

_LEADERSHIP_DILUTION = (r"\bdilut", r"share count", r"shares outstanding",
                        r"\batm program\b", r"equity raise", r"\boffering\b")
_LEADERSHIP_CREDIBILITY = (r"\bmissed\b", r"\brestat", r"\bresign", r"\bdeparture",
                           r"\bturnover\b", r"\bdelay(ed|s)?\b", r"\bpromotional\b",
                           r"\boverpromis", r"guidance withdrawn")
_LEADERSHIP_CAPITAL = (r"capital allocation", r"\bbuyback", r"\brepurchase",
                       r"\bdividend", r"\bacquisition", r"\breinvest",
                       r"capital discipline")
_LEADERSHIP_TRACK_RECORD = (r"track record", r"\bdelivered\b", r"\bon track\b",
                            r"\bon schedule\b", r"\bon time\b", r"\bfounder",
                            r"\bexecuted\b", r"guidance met", r"ahead of schedule",
                            r"\benergized\b")


# --------------------------------------------------------------------------- #
# Internal per-event verdict (pure data, never emitted).                        #
# --------------------------------------------------------------------------- #
class _Reading:
    """One evidence read of one company-document event. Never an output object."""

    __slots__ = ("finding_type", "direction", "magnitude", "urgency", "detail",
                 "extra_gaps")

    def __init__(self, finding_type, direction, magnitude, urgency, detail,
                 extra_gaps=()):
        self.finding_type = finding_type
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.detail = detail
        self.extra_gaps = tuple(extra_gaps)


# --------------------------------------------------------------------------- #
# The shared base agent                                                         #
# --------------------------------------------------------------------------- #
class _CompanyEvidenceAgentBase(SensorAgent):
    """Shared machinery for the four company-evidence sensors.

    Subclasses set ``_AGENT_ID`` / ``_DISCIPLINE`` / ``_AGENT_NAME`` and implement
    :meth:`_select_events` (which 014C events are theirs) + :meth:`_read_event` (one
    event -> one qualitative evidence label, or None). The base builds AgentFindings ONLY,
    in the agent's own discipline, stamping the source claim status into every summary --
    a company claim is NEVER upgraded to a fact.
    """

    _AGENT_ID = ""
    _DISCIPLINE = ""
    _AGENT_NAME = ""

    def __init__(self) -> None:
        # Reuse the built-in tattva.* descriptor (single source of identity).
        self._descriptor = next(
            d for d in DEFAULT_DESCRIPTORS if d.agent_id == self._AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- hooks ------------------------------------------------------------- #
    def _select_events(self, events: Tuple[RealityEvent, ...]) -> Tuple[RealityEvent, ...]:
        """Default: the events 014C stamped with this agent's own discipline."""
        return tuple(e for e in events if e.discipline == self._DISCIPLINE)

    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        raise NotImplementedError

    # -- run ----------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret this agent's company-document events into evidence findings.

        Deterministic + offline: reads only the injected ``events``. One finding per
        readable event; the source claim status is stamped verbatim (never upgraded);
        stale input marks the finding stale (never dropped). Sorted by finding_id.
        """
        mine = self._select_events(events)
        findings: List[AgentFinding] = []
        for event in sorted(mine, key=lambda e: e.event_id):
            reading = self._read_event(event)
            if reading is not None:
                findings.append(self._build_finding(event, reading))
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- finding builder ------------------------------------------------------ #
    def _build_finding(self, event: RealityEvent, r: _Reading) -> AgentFinding:
        claim, authority = _claim_of(event)
        companies = tuple(event.affected_companies or ())
        subject = companies[0] if companies else "unscoped"

        gaps: List[str] = list(r.extra_gaps)
        if not companies:
            gaps.append(
                "subject company not identified on {0} (finding subject unscoped -- "
                "surfaced, never guessed)".format(event.event_id))
        note = _stale_note((event,))
        if note:
            gaps.append(note)
        inherited_gaps = sorted(event.data_gaps)
        data_gaps = tuple(dict.fromkeys(gaps + inherited_gaps))

        # The 012G stamping pattern: the source claim status travels in the summary so
        # provenance is inspectable end-to-end (claim_status_of reads it back). A
        # company-sourced statement stays company_claim -- never upgraded to a fact.
        summary = "{0} for {1}: {2} | claim_status={3} | source_authority={4}".format(
            r.finding_type, subject, r.detail, claim, authority)

        return AgentFinding(
            finding_id="finding.{0}.{1}.{2}.{3}".format(
                self._DISCIPLINE, r.finding_type, _slug(subject),
                _sha8(event.event_id)),
            agent_id=self._AGENT_ID,
            agent_layer="reality_intelligence",
            agent_name=self._AGENT_NAME,
            discipline=self._DISCIPLINE,
            input_events=(event.event_id,),
            finding_type=r.finding_type,
            finding_summary=summary,
            affected_companies=companies,
            affected_themes=tuple(event.affected_themes or ()),
            direction_label=r.direction,
            magnitude_label=r.magnitude,
            urgency_label=r.urgency,
            confidence_label=_weakest_confidence((event,)),
            freshness_label=_weakest_freshness((event,)),
            half_life="months",
            source_authority_summary=authority,
            # A company / reported claim is uncorroborated by definition here -- an
            # evidence sensor records the claim, it does not confirm it.
            corroboration_status="uncorroborated",
            contradiction_status="unopposed",
            evidence_refs=tuple(sorted(event.evidence_refs)),
            source_refs=tuple(sorted(event.source_refs)),
            conflicts=tuple(sorted(event.conflicts)),
            data_gaps=data_gaps,
            routing_targets=("TattvaSignalFusion",),
        )


# --------------------------------------------------------------------------- #
# CustomerEvidenceAgent (#13)                                                   #
# --------------------------------------------------------------------------- #
class CustomerEvidenceAgent(_CompanyEvidenceAgentBase):
    """Tattva Customer Evidence sensor. Consumes 014C ``customer_mention`` events.

    Subagents (structural): Customer Win / Customer Concentration / Adoption Signal /
    Backlog-Order Signal. Emits ``CustomerEvidenceFinding``s: a company-claimed customer
    win stays a claim; a concentration read is a dependency LABEL, not a judgement.
    """

    _AGENT_ID = "tattva.customer_evidence"
    _DISCIPLINE = "customer_evidence"
    _AGENT_NAME = "Customer Evidence"

    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        text = _text_of(event)
        if _matches(text, _CUSTOMER_CONCENTRATION):
            return _Reading(
                "concentration_note", "neutral", "moderate", "elevated",
                "customer-concentration read from a company document -- a dependency "
                "label (company-sourced statement, not independently verified)")
        if _matches(text, _CUSTOMER_WIN):
            return _Reading(
                "customer_win_claim", "improving", "moderate", "watch",
                "customer win asserted in a company document -- stays the company's own "
                "claim until independently confirmed")
        if _matches(text, _CUSTOMER_ADOPTION_STRONG):
            return _Reading(
                "adoption_signal", "improving", "moderate", "watch",
                "customer adoption / backlog evidence in a company document "
                "(company-sourced statement, not independently verified)")
        return _Reading(
            "adoption_signal", "improving", "minor", "watch",
            "customer named in a company document -- adoption evidence label "
            "(company-sourced statement, not independently verified)")


# --------------------------------------------------------------------------- #
# SupplierEvidenceAgent (#14)                                                   #
# --------------------------------------------------------------------------- #
class SupplierEvidenceAgent(_CompanyEvidenceAgentBase):
    """Tattva Supplier Evidence sensor. Consumes 014C ``supplier_mention`` events.

    Subagents (structural): Supplier Relationship / Supplier-of-Supplier / Dependency
    Risk / Substitution Risk. Emits ``SupplierEvidenceFinding``s: dependency /
    substitution reads are LABELS on company-sourced statements.
    """

    _AGENT_ID = "tattva.supplier_evidence"
    _DISCIPLINE = "supplier_evidence"
    _AGENT_NAME = "Supplier Evidence"

    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        text = _text_of(event)
        if _matches(text, _SUPPLIER_SUBSTITUTION):
            return _Reading(
                "substitution_risk", "deteriorating", "moderate", "elevated",
                "supplier-substitution read from a company document -- a substitution "
                "risk label (company-sourced statement, not independently verified)")
        if _matches(text, _SUPPLIER_DEPENDENCY_STRONG):
            return _Reading(
                "supplier_dependency", "neutral", "moderate", "elevated",
                "supplier-dependency read from a company document -- a dependency label "
                "(company-sourced statement, not independently verified)")
        return _Reading(
            "supplier_dependency", "neutral", "minor", "watch",
            "supplier / partner named in a company document -- relationship evidence "
            "label (company-sourced statement, not independently verified)")


# --------------------------------------------------------------------------- #
# BottleneckEvidenceAgent (#15)                                                 #
# --------------------------------------------------------------------------- #
class BottleneckEvidenceAgent(_CompanyEvidenceAgentBase):
    """Tattva Bottleneck Evidence sensor. Reads capacity / lead-time / shortage statements
    out of the 014C company documents.

    014C stamps deck claims and transcript statements ``news_filings``, so this agent
    filters by EVENT TYPE + content (the same documents, a different discipline lens) and
    emits in ITS OWN ``bottleneck_evidence`` discipline with the input events referenced.
    Subagents (structural): Lead-Time / Capacity Expansion / Utilization / Pricing Power /
    Shortage Evidence / Resolution Risk. Company-stated capacity carries the explicit
    :data:`COMPANY_STATED_CAPACITY_GAP` -- the 014C TAM technique.
    """

    _AGENT_ID = "tattva.bottleneck_evidence"
    _DISCIPLINE = "bottleneck_evidence"
    _AGENT_NAME = "Bottleneck Evidence"

    def _select_events(self, events: Tuple[RealityEvent, ...]) -> Tuple[RealityEvent, ...]:
        out = []
        for event in events:
            if event.discipline == self._DISCIPLINE:
                out.append(event)
            elif _is_company_document_text_event(event) and self._classify(event):
                out.append(event)
        return tuple(out)

    @staticmethod
    def _classify(event: RealityEvent) -> str:
        text = _text_of(event)
        if _matches(text, _BOTTLENECK_LEAD_TIME):
            return "lead_time_note"
        if _matches(text, _BOTTLENECK_SHORTAGE):
            return "shortage_evidence"
        if _matches(text, _BOTTLENECK_CAPACITY):
            return "capacity_expansion_claim"
        return ""

    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        finding_type = self._classify(event)
        if not finding_type:
            return None
        claim, _authority = _claim_of(event)
        # Company-stated capacity / lead-time is NEVER independently verified here: the
        # figure travels as the company's claim WITH the explicit gap (TAM technique).
        extra_gaps = (COMPANY_STATED_CAPACITY_GAP,) if claim in _COMPANY_SOURCED else ()
        if finding_type == "lead_time_note":
            return _Reading(
                "lead_time_note", "neutral", "moderate", "elevated",
                "lead-time statement in a company document -- a supply-chain timing "
                "label (company-sourced statement, not independently verified)",
                extra_gaps)
        if finding_type == "shortage_evidence":
            return _Reading(
                "shortage_evidence", "deteriorating", "moderate", "elevated",
                "shortage / supply-constraint statement in a company document -- a "
                "supply-tightness label (company-sourced statement, not independently "
                "verified)", extra_gaps)
        return _Reading(
            "capacity_expansion_claim", "improving", "moderate", "watch",
            "capacity / utilization statement in a company document -- stays the "
            "company's own claim until independently confirmed", extra_gaps)


def has_bottleneck_evidence_events(events: Iterable[RealityEvent]) -> bool:
    """True iff ``events`` carry anything the Bottleneck Evidence agent can read.

    Used by ``run_pulse`` as the agent's conditional gate (the 014D pattern): the agent
    joins a pulse ONLY when a bottleneck-discipline event exists or a 014C company
    document carries a capacity / lead-time / shortage statement -- so the default
    fixture-only pulse stays byte-identical.
    """
    for event in events:
        if event.discipline == "bottleneck_evidence":
            return True
        if (_is_company_document_text_event(event)
                and BottleneckEvidenceAgent._classify(event)):
            return True
    return False


# --------------------------------------------------------------------------- #
# LeadershipEvidenceAgent (#16)                                                 #
# --------------------------------------------------------------------------- #
class LeadershipEvidenceAgent(_CompanyEvidenceAgentBase):
    """Tattva Leadership Evidence sensor. Consumes 014C ``leadership_statement`` events
    plus ``ir_deck_claim`` deck claims that read on leadership topics.

    Subagents (structural): Founder-Led / Execution Track Record / Capital Allocation /
    Credibility Flag / Dilution History. Emits ``LeadershipEvidenceFinding``s: a
    credibility read is a LABEL; a leadership statement stays the company's claim.
    """

    _AGENT_ID = "tattva.leadership_evidence"
    _DISCIPLINE = "leadership_evidence"
    _AGENT_NAME = "Leadership Evidence"

    def _select_events(self, events: Tuple[RealityEvent, ...]) -> Tuple[RealityEvent, ...]:
        out = []
        for event in events:
            if event.discipline == self._DISCIPLINE:
                out.append(event)
            elif (event.discipline == "news_filings"
                  and event.event_type == "ir_deck_claim"
                  and self._classify(event)):
                out.append(event)
        return tuple(out)

    @staticmethod
    def _classify(event: RealityEvent) -> str:
        text = _text_of(event)
        if _matches(text, _LEADERSHIP_DILUTION):
            return "dilution_history_note"
        if _matches(text, _LEADERSHIP_CREDIBILITY):
            return "credibility_flag"
        if _matches(text, _LEADERSHIP_CAPITAL):
            return "capital_allocation_note"
        if _matches(text, _LEADERSHIP_TRACK_RECORD):
            return "execution_track_record_note"
        return ""

    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        finding_type = self._classify(event)
        if finding_type == "dilution_history_note":
            return _Reading(
                "dilution_history_note", "deteriorating", "moderate", "elevated",
                "dilution-history read from a company document -- a capital-structure "
                "label (company-sourced statement, not independently verified)")
        if finding_type == "credibility_flag":
            return _Reading(
                "credibility_flag", "deteriorating", "moderate", "elevated",
                "leadership-credibility read from a company document -- a credibility "
                "label, not a judgement (company-sourced statement, not independently "
                "verified)")
        if finding_type == "capital_allocation_note":
            return _Reading(
                "capital_allocation_note", "neutral", "moderate", "watch",
                "capital-allocation read from a company document -- an allocation-style "
                "label (company-sourced statement, not independently verified)")
        if finding_type == "execution_track_record_note":
            return _Reading(
                "execution_track_record_note", "improving", "moderate", "watch",
                "execution track-record evidence in a company document (company-sourced "
                "statement, not independently verified)")
        # A leadership statement with no keyword read is still evidence -- recorded as a
        # neutral track-record note, never dropped and never embellished.
        return _Reading(
            "execution_track_record_note", "neutral", "minor", "watch",
            "leadership statement recorded from a company document -- execution-evidence "
            "label (company-sourced statement, not independently verified)")
