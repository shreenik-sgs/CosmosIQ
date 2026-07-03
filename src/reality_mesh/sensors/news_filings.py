"""The News / Filings / Press-Release sensor agent for the Reality Mesh (IMPLEMENTATION-012G).

Another real Tattva sensor, mirroring the 012D :mod:`reality_mesh.sensors.market_regime` and 012E
:mod:`reality_mesh.sensors.rotation` pattern (SensorAgent + fixture loader + ``run_checked`` +
finding construction). :class:`NewsFilingsAgent` reads FIXTURE-backed filing / press-release /
company-announcement / reported-news :class:`~reality_mesh.models.RealityEvent`s and produces
``NewsFilingFinding``s (each an :class:`~reality_mesh.models.AgentFinding` in the ``news_filings``
discipline). It reuses the built-in ``tattva.news_filings`` descriptor (AGENT_MAP_012 §3.3) and
passes :meth:`~reality_mesh.agents.SensorAgent.run_checked`.

SEVEN SUBAGENTS (AGENT_MAP_012 §3.3, verbatim): **8-K · S-3/ATM · Insider Sale · Press Release ·
Contract Announcement · Guidance Update · Partnership**.

FINDING TYPES emitted: ``dilution_risk`` · ``capital_raise_risk`` · ``insider_sale`` ·
``contract_validation`` · ``guidance_update`` · ``customer_win_claim`` · ``partnership_claim``.
Each maps to a ``direction_label``: dilution / capital-raise / insider-sale -> ``deteriorating``;
contract-validation / customer-win / partnership / guidance-up -> ``improving`` (a guidance CUT
reads ``deteriorating``).

AUTHORITY DISCIPLINE (ARCHITECTURE_CONTRACT_012 §C -- NO verified-fact laundering):

* An **SEC filing FACT** (8-K / S-3 / Form 4) is CANONICAL: ``source_authority_summary=canonical``
  and its claim-status is ``verified_fact`` (the filing exists and states the fact).
* A **press release / company announcement** (customer win, partnership, guidance) is a
  ``company_claim`` at ``primary`` (company-IR) authority -- NEVER auto-promoted to a verified
  fact, even when furnished inside an 8-K (the guidance NUMBER is a company statement).
* **Reported news** (a third party reported it) is a ``reported_claim`` at ``convenience``
  authority.
* A finding may carry ``verified_fact`` ONLY when its source authority is ``canonical``; the
  builder refuses to launder a lower-authority claim up to a verified fact.

CONFLICTS PRESERVED. When a company claim (e.g. a rosy customer-win press release, ``improving``)
conflicts with a filing fact about the SAME subject (e.g. a dilutive S-3, ``deteriorating``), BOTH
findings are emitted (neither dropped, neither promoted) and the clash is recorded in each
finding's ``conflicts`` with ``contradiction_status="disputed"``.

HONEST GAPS. A STALE input marks the finding ``freshness_label="stale"`` (never dropped) and
records a data gap; a MISSING / absent field (offering size, share count, contract value, subject
company) becomes an explicit ``data_gaps`` note -- never a fabricated value.

FIXTURE / MOCK ONLY. The agent NEVER fetches live data, opens a socket, schedules, streams, or
touches a broker (there is no such affordance in this module). It emits qualitative LABELS only --
never a number, score, rank, buy/sell/hold, order, or thesis, and none of these findings is an
investment decision.

Deterministic, stdlib-only, Python 3.9. No network on import; ids are content-derived; every
``now`` / timestamp is an injected string (no wall-clock).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS
from .market_regime import events_from_fixture  # reuse the 012D offline JSON loader

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.news_filings descriptor (AGENT_MAP_012). #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.news_filings"
_DISCIPLINE = "news_filings"

# The seven discipline-scoped subagents (AGENT_MAP_012 §3.3), verbatim.
NEWS_FILINGS_SUBAGENTS: Tuple[str, ...] = (
    "8-K",
    "S-3/ATM",
    "Insider Sale",
    "Press Release",
    "Contract Announcement",
    "Guidance Update",
    "Partnership",
)

# The finding types this agent may produce (descriptive, NOT numbers). Each is an AgentFinding
# whose structural subtype is ``NewsFilingFinding``.
NEWS_FILINGS_FINDING_TYPES: Tuple[str, ...] = (
    "dilution_risk",
    "capital_raise_risk",
    "insider_sale",
    "contract_validation",
    "guidance_update",
    "customer_win_claim",
    "partnership_claim",
)

# Finding types that assert a FILING FACT (verified_fact only from a canonical SEC filing).
FILING_FACT_FINDINGS: Tuple[str, ...] = (
    "dilution_risk", "capital_raise_risk", "insider_sale", "contract_validation")

# Finding types that are inherently a COMPANY STATEMENT (a company_claim, never a verified fact).
COMPANY_CLAIM_FINDINGS: Tuple[str, ...] = (
    "guidance_update", "customer_win_claim", "partnership_claim")

# finding_type -> direction_label (closed DIRECTION_LABELS). guidance_update follows its reading
# (a raise is improving, a cut deteriorating) and so is resolved at runtime, not here.
_TYPE_DIRECTION: Dict[str, str] = {
    "dilution_risk": "deteriorating",
    "capital_raise_risk": "deteriorating",
    "insider_sale": "deteriorating",
    "contract_validation": "improving",
    "customer_win_claim": "improving",
    "partnership_claim": "improving",
}

# Directional polarity for conflict detection (a company claim that OPPOSES a filing fact).
_POSITIVE_DIRECTIONS = frozenset({"improving", "accelerating", "rising"})
_NEGATIVE_DIRECTIONS = frozenset({"deteriorating", "decelerating", "falling", "reversing"})

# Optional numeric keys the subagents read for magnitude (raw observations -> LABELS; the finding
# itself carries no number). A missing key is an explicit data gap, never fabricated.
_K_OFFERING_AMOUNT = "offering_amount_usd"
_K_OFFERING_PCT = "offering_pct_of_shares"
_K_SHARES_SOLD = "shares_sold"
_K_SALE_VALUE = "sale_value_usd"
_K_CONTRACT_VALUE = "contract_value_usd"
_K_GUIDANCE_CHANGE = "guidance_change_pct"

_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")

# The marker embedded in every finding_summary so a downstream reader (and the test matrix) can
# recover the source claim status WITHOUT the agent adding a trade/score field to AgentFinding.
_CLAIM_MARKER = "claim_status="


# --------------------------------------------------------------------------- #
# Public helper -- recover the per-source claim status stamped on a finding.    #
# --------------------------------------------------------------------------- #
def claim_status_of(finding: AgentFinding) -> str:
    """Return the source claim status stamped on ``finding`` (``""`` if none).

    The agent stamps ``claim_status=<status>`` into every ``finding_summary`` (verified_fact /
    company_claim / reported_claim / inferred) so provenance is inspectable end-to-end without
    adding a field to the frozen :class:`AgentFinding`. This is a READ helper only.
    """
    summary = finding.finding_summary or ""
    i = summary.find(_CLAIM_MARKER)
    if i < 0:
        return ""
    out = []
    for ch in summary[i + len(_CLAIM_MARKER):]:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            break
    return "".join(out)


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _num_in(events: Tuple[RealityEvent, ...], key: str) -> Optional[float]:
    """First numeric reading named ``key`` across ``events`` (else None). No fabrication."""
    for event in events:
        for name, value, _unit in event.numeric_values:
            if name == key:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


def _weakest_freshness(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.freshness_label for e in events if e.freshness_label in _FRESHNESS_REAL_ORDER]
    if not present:
        return "missing"
    return min(present, key=lambda v: _FRESHNESS_REAL_ORDER.index(v))


def _weakest_confidence(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.confidence_label for e in events if e.confidence_label not in ("", "missing")]
    if not present:
        return "moderate"
    return min(present, key=lambda v: _CONFIDENCE_ORDER.index(v)
               if v in _CONFIDENCE_ORDER else len(_CONFIDENCE_ORDER))


def _best_authority(events: Tuple[RealityEvent, ...]) -> str:
    present = [e.source_authority for e in events if e.source_authority]
    if not present:
        return "convenience"
    return max(present, key=_labels.authority_rank)


def _stale_note(events: Tuple[RealityEvent, ...]) -> Optional[str]:
    stale_ids = sorted(e.event_id for e in events if e.freshness_label in _FRESHNESS_STALE)
    if stale_ids:
        return "stale news/filing data preserved (not dropped): {0}".format(", ".join(stale_ids))
    return None


def _opposes(d1: str, d2: str) -> bool:
    """True iff two direction labels are on opposite polarity (a claim-vs-fact conflict)."""
    return (
        (d1 in _POSITIVE_DIRECTIONS and d2 in _NEGATIVE_DIRECTIONS)
        or (d1 in _NEGATIVE_DIRECTIONS and d2 in _POSITIVE_DIRECTIONS)
    )


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _is_sec_filing(event: RealityEvent) -> bool:
    """True iff the event is a canonical SEC filing (8-K / S-3 / Form 4 / edgar / sec)."""
    if event.source_authority == "canonical":
        return True
    blob = "{0} {1} {2}".format(
        event.source_type or "", event.event_type or "", event.source_id or "").lower()
    return any(tok in blob for tok in ("sec", "edgar", "8-k", "8k", "s-3", "s3", "form 4",
                                       "form4", "form_4", "424b", "filing"))


def _claim_for(event: RealityEvent, finding_type: str) -> Tuple[str, str]:
    """Resolve ``(claim_status, source_authority)`` for a finding, WITHOUT laundering.

    * A company-statement finding type (guidance / customer win / partnership) is a
      ``company_claim`` (or ``reported_claim`` if a third party reported it) -- never a
      verified fact, even when furnished in an 8-K.
    * A filing-fact finding type is ``verified_fact`` ONLY when the source authority is
      ``canonical`` (an SEC filing); a lower-authority source is capped at ``company_claim``.
    """
    src_claim = (event.claim_status or "").strip()
    authority = event.source_authority or ("canonical" if _is_sec_filing(event) else "convenience")

    if finding_type in COMPANY_CLAIM_FINDINGS:
        claim = "reported_claim" if src_claim == "reported_claim" else "company_claim"
        # a company statement is at most company-IR primary authority (never canonical).
        if authority == "canonical":
            authority = "primary"
        return claim, authority

    if finding_type in FILING_FACT_FINDINGS:
        if authority == "canonical" and src_claim in ("", "verified_fact"):
            return "verified_fact", "canonical"
        # refuse to promote a non-canonical source to a verified fact.
        if src_claim == "verified_fact" and authority != "canonical":
            return "company_claim", authority
        return (src_claim or "company_claim"), authority

    return (src_claim or "inferred"), authority


# --------------------------------------------------------------------------- #
# Internal subagent verdict (NOT an output object -- a plain mutable record).    #
# --------------------------------------------------------------------------- #
class _Reading:
    """One subagent's interpretation of one input event. Pure data, never emitted."""

    __slots__ = ("subagent", "finding_type", "direction", "magnitude", "urgency", "summary",
                 "event", "claim_status", "authority", "companies", "extra_gaps", "finding_id")

    def __init__(self, subagent, finding_type, direction, magnitude, urgency, summary, event,
                 claim_status, authority, companies, extra_gaps):
        self.subagent = subagent
        self.finding_type = finding_type
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.summary = summary
        self.event = event
        self.claim_status = claim_status
        self.authority = authority
        self.companies = tuple(companies)
        self.extra_gaps = list(extra_gaps)
        subject = self.companies[0] if self.companies else "unscoped"
        self.finding_id = "finding.news_filings.{0}.{1}".format(finding_type, _slug(subject))


# --------------------------------------------------------------------------- #
# Event -> (subagent, finding_type) classification                              #
# --------------------------------------------------------------------------- #
def _classify(event: RealityEvent) -> Tuple[str, str]:
    """Map an event to ``(subagent, finding_type)`` ('' / '' if it is not ours)."""
    text = "{0} {1}".format(event.event_type or "", event.observed_fact or "").lower()
    is_filing = _is_sec_filing(event)

    # -- capital structure (always a filing fact) -------------------------------- #
    if any(t in text for t in ("s-3", "s3", "atm", "shelf", "424b")):
        return "S-3/ATM", "dilution_risk"
    if any(t in text for t in ("registered_direct", "registered direct", "private_placement",
                               "private placement", "convertible", "capital_raise",
                               "capital raise", "secondary_offering", "secondary offering",
                               "equity offering", "dilut")):
        return "S-3/ATM", "capital_raise_risk"

    # -- insider Form 4 sale ----------------------------------------------------- #
    if any(t in text for t in ("form4", "form_4", "form 4", "insider")):
        return "Insider Sale", "insider_sale"

    # -- guidance ---------------------------------------------------------------- #
    if "guidance" in text or "outlook" in text:
        return "Guidance Update", "guidance_update"

    # -- partnership ------------------------------------------------------------- #
    if any(t in text for t in ("partnership", "partner", "collaboration", "alliance",
                               "joint venture")):
        return "Partnership", "partnership_claim"

    # -- contract / customer business: a FILED contract is a fact; a PRESS-RELEASE
    #    customer win is a company_claim. Distinguish by source, not just wording. --- #
    if any(t in text for t in ("contract", "customer", "design_win", "design win",
                               "award", "order", "backlog", "purchase order", "win")):
        if is_filing:
            return "Contract Announcement", "contract_validation"
        return "Press Release", "customer_win_claim"

    # -- generic 8-K material event -> treat as a contract/validation filing fact -- #
    if is_filing and ("8-k" in text or "8k" in text):
        return "8-K", "contract_validation"

    return "", ""


# --------------------------------------------------------------------------- #
# NewsFilingsAgent                                                            #
# --------------------------------------------------------------------------- #
class NewsFilingsAgent(SensorAgent):
    """FIXTURE-backed Tattva News/Filings/Press-Release sensor. Emits ``NewsFilingFinding``s.

    Reads filing / press-release / company-announcement / reported-news events and interprets each
    into a NewsFilingFinding. SEC filing facts are CANONICAL (verified_fact); press releases and
    company announcements are company_claim; reported news is reported_claim -- never laundered up.
    A company claim that opposes a filing fact about the same subject is PRESERVED as a conflict on
    both findings. Missing fields -> explicit data gaps; stale input is marked stale, never dropped.
    Labels only; no score / rank / trade field; not an investment decision.
    """

    _AGENT_NAME = "News Filings"

    def __init__(self) -> None:
        # Reuse the built-in tattva.news_filings descriptor (single source of identity).
        self._descriptor = next(d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret filing / press-release / announcement events into NewsFilingFindings.

        Deterministic + offline: reads only the injected ``events`` (from fixtures), classifies
        each into its subagent + finding type, resolves per-source authority / claim status
        (never promoting a claim to a verified fact), preserves claim-vs-filing conflicts about
        the same subject, and surfaces missing/stale inputs as explicit gaps.
        """
        mine = tuple(e for e in events if e.discipline == _DISCIPLINE)

        readings: List[_Reading] = []
        for event in sorted(mine, key=lambda e: e.event_id):
            reading = self._read_event(event)
            if reading is not None:
                readings.append(reading)

        conflicts_by_id = self._detect_conflicts(readings)

        findings = [
            self._finding_from_reading(r, conflicts_by_id.get(r.finding_id, []))
            for r in readings
        ]
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- per-event reader ------------------------------------------------- #
    def _read_event(self, event: RealityEvent) -> Optional[_Reading]:
        subagent, finding_type = _classify(event)
        if not finding_type:
            return None

        claim, authority = _claim_for(event, finding_type)
        companies = tuple(event.affected_companies or ())
        subject = companies[0] if companies else "the issuer"

        gaps: List[str] = []
        if not companies:
            gaps.append(
                "subject company not identified on {0} (finding subject unscoped)".format(
                    event.event_id))

        direction = _TYPE_DIRECTION.get(finding_type, "")
        magnitude = "moderate"
        urgency = "watch"
        detail = ""

        if finding_type == "dilution_risk":
            urgency = "elevated"
            pct = _num_in((event,), _K_OFFERING_PCT)
            amt = _num_in((event,), _K_OFFERING_AMOUNT)
            if pct is not None:
                magnitude = "extreme" if pct >= 25 else ("major" if pct >= 10 else "moderate")
                detail = "shelf/ATM registration up to {0}% of shares".format(pct)
            elif amt is not None:
                magnitude = "major" if amt >= 1e8 else "moderate"
                detail = "shelf/ATM registration up to ${0:,.0f}".format(amt)
            else:
                detail = "shelf/ATM registration filed"
                gaps.append("offering size not disclosed on {0} (dilution magnitude "
                            "unquantified)".format(event.event_id))
        elif finding_type == "capital_raise_risk":
            urgency = "elevated"
            amt = _num_in((event,), _K_OFFERING_AMOUNT)
            if amt is not None:
                magnitude = "major" if amt >= 1e8 else "moderate"
                detail = "capital raise of ${0:,.0f}".format(amt)
            else:
                detail = "capital raise disclosed"
                gaps.append("raise size not disclosed on {0} (magnitude unquantified)".format(
                    event.event_id))
        elif finding_type == "insider_sale":
            shares = _num_in((event,), _K_SHARES_SOLD)
            value = _num_in((event,), _K_SALE_VALUE)
            if value is not None:
                magnitude = "major" if value >= 5e6 else "moderate"
                urgency = "elevated" if value >= 5e6 else "watch"
                detail = "insider sale of ${0:,.0f}".format(value)
            elif shares is not None:
                detail = "insider sale of {0:,.0f} shares".format(shares)
            else:
                detail = "insider sale reported (Form 4)"
                gaps.append("insider sale size not disclosed on {0} (magnitude "
                            "unquantified)".format(event.event_id))
        elif finding_type == "contract_validation":
            value = _num_in((event,), _K_CONTRACT_VALUE)
            if value is not None:
                magnitude = "major" if value >= 1e8 else "moderate"
                detail = "contract validated at ${0:,.0f}".format(value)
            else:
                detail = "contract / material agreement filed"
                gaps.append("contract value not disclosed on {0} (magnitude "
                            "unquantified)".format(event.event_id))
        elif finding_type == "guidance_update":
            change = _num_in((event,), _K_GUIDANCE_CHANGE)
            cut = any(t in "{0} {1}".format(event.event_type, event.observed_fact).lower()
                      for t in ("cut", "lower", "reduce", "below", "warn", "miss", "shortfall"))
            if change is not None:
                cut = cut or change < 0
                magnitude = "major" if abs(change) >= 10 else "moderate"
                detail = "guidance {0} {1}%".format("cut" if cut else "raised", abs(change))
            else:
                detail = "guidance {0}".format("cut" if cut else "updated")
                gaps.append("guidance change magnitude not disclosed on {0}".format(event.event_id))
            direction = "deteriorating" if cut else "improving"
            urgency = "elevated" if cut else "watch"
        elif finding_type == "customer_win_claim":
            value = _num_in((event,), _K_CONTRACT_VALUE)
            detail = "customer-win claim{0}".format(
                " (up to ${0:,.0f} claimed)".format(value) if value is not None else "")
            if value is None:
                gaps.append("claimed deal size not disclosed on {0} (unverified company "
                            "claim)".format(event.event_id))
        elif finding_type == "partnership_claim":
            detail = "partnership / collaboration claim"

        summary = "{0} [{1}] for {2}: {3} | claim_status={4} | source_authority={5}".format(
            finding_type, subagent, subject, detail, claim, authority)

        return _Reading(
            subagent=subagent, finding_type=finding_type, direction=direction,
            magnitude=magnitude, urgency=urgency, summary=summary, event=event,
            claim_status=claim, authority=authority, companies=companies, extra_gaps=gaps)

    # -- claim-vs-filing conflict detection ------------------------------- #
    def _detect_conflicts(self, readings: List[_Reading]) -> Dict[str, List[str]]:
        """Detect company_claim readings that OPPOSE a filing fact about the same subject.

        Returns ``finding_id -> [conflict notes]``. Both sides are always PRESERVED (this only
        annotates); a company claim is never dropped in favour of the filing, nor promoted to it.
        """
        by_company: Dict[str, List[_Reading]] = {}
        for r in readings:
            for company in (r.companies or ("__unscoped__",)):
                by_company.setdefault(company, []).append(r)

        notes: Dict[str, List[str]] = {}
        for company, group in sorted(by_company.items()):
            if company == "__unscoped__":
                continue
            claims = [r for r in group if r.claim_status in ("company_claim", "reported_claim")]
            facts = [r for r in group if r.claim_status == "verified_fact"]
            for cr in claims:
                for fr in facts:
                    if not _opposes(cr.direction, fr.direction):
                        continue
                    note = (
                        "conflict: company_claim {0} ({1}, {2}) opposes SEC filing fact {3} "
                        "({4}, {5}) for {6} -- both preserved; claim NOT promoted to "
                        "verified_fact".format(
                            cr.finding_id, cr.finding_type, cr.direction,
                            fr.finding_id, fr.finding_type, fr.direction, company))
                    notes.setdefault(cr.finding_id, []).append(note)
                    notes.setdefault(fr.finding_id, []).append(note)
        return notes

    # -- finding builder -------------------------------------------------- #
    def _finding_from_reading(self, r: _Reading, conflict_notes: List[str]) -> AgentFinding:
        evs = (r.event,)
        gaps: List[str] = list(r.extra_gaps)
        note = _stale_note(evs)
        if note:
            gaps.append(note)

        evidence_refs = tuple(sorted({ref for e in evs for ref in e.evidence_refs}))
        source_refs = tuple(sorted({ref for e in evs for ref in e.source_refs}))
        inherited_conflicts = sorted({c for e in evs for c in e.conflicts})
        conflicts = tuple(dict.fromkeys(list(conflict_notes) + inherited_conflicts))
        inherited_gaps = sorted({g for e in evs for g in e.data_gaps})
        data_gaps = tuple(dict.fromkeys(gaps + inherited_gaps))

        contradiction = "disputed" if conflict_notes else "unopposed"
        # A filing fact stands on the record; a company claim is uncorroborated by default.
        corroboration = ("uncorroborated" if r.claim_status in ("company_claim", "reported_claim")
                         else "partially_corroborated")
        half_life = "weeks" if r.finding_type in FILING_FACT_FINDINGS else "days"

        return AgentFinding(
            finding_id=r.finding_id,
            agent_id=_AGENT_ID,
            agent_layer="reality_intelligence",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=(r.event.event_id,),
            finding_type=r.finding_type,
            finding_summary=r.summary,
            affected_companies=r.companies,
            direction_label=r.direction,
            magnitude_label=r.magnitude,
            urgency_label=r.urgency,
            confidence_label=_weakest_confidence(evs),
            freshness_label=_weakest_freshness(evs),
            half_life=half_life,
            source_authority_summary=r.authority,
            corroboration_status=corroboration,
            contradiction_status=contradiction,
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            conflicts=conflicts,
            data_gaps=data_gaps,
            routing_targets=("TattvaSignalFusion",),
        )
