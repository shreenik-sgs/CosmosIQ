"""The Financial Inflection sensor agent for the Reality Mesh (IMPLEMENTATION-021B).

The one clearly-buildable deferred Tattva sensor, unlocked once SEC shadow validation was
observed (020H/020I). :class:`FinancialInflectionAgent` synthesizes FINANCIAL-INFLECTION
``FinancialInflectionFinding``s (each an :class:`~reality_mesh.models.AgentFinding` in the
``financial_inflection`` discipline) from TWO honest input sources -- and NOTHING else:

* **020B SEC filing EVENTS** (a real source contract). The 020B
  :class:`~reality_mesh.adapters.sec_edgar_live.SecEdgarLiveAdapter` already lands canonical
  filing facts in the ``news_filings`` discipline; this sensor reads the financial-inflection
  subset by EVENT TYPE (the same documents, a financial lens -- the 014F cross-discipline
  pattern used by Bottleneck/Leadership Evidence):

    - ``S-3`` / ``S-1`` / ``424B`` shelf/offering -> a ``dilution_inflection`` (CANONICAL).
    - ``8-K`` Item 2.02 results of operations -> a ``guidance_inflection`` (CANONICAL; a raise
      reads ``improving``, a cut ``deteriorating``).
    - ``8-K`` Item 4.02 non-reliance -> a ``restatement_inflection`` (CANONICAL).
    - ``Form 4`` insider transaction -> an ``insider_inflection`` (CANONICAL).

  A filing fact is ``source_authority_summary=canonical`` + claim status ``verified_fact`` (the
  filing exists and states the fact) and carries HIGHER confidence.

* **LOCAL fundamental-snapshot fixtures** (revenue-growth / margin / leverage / FCF / capex
  DELTAS), stamped in the ``financial_inflection`` discipline. Their source authority is
  ``company_claim`` (company IR -> ``primary``) or a provider read (``reported_claim`` ->
  ``convenience``) -- NEVER canonical, NEVER a verified fact. A snapshot inflection carries
  LOWER confidence and is marked "not independently verified".

AUTHORITY DISCIPLINE (ARCHITECTURE_CONTRACT_012 §C -- NO verified-fact laundering; the sacred
source-authority ladder ``canonical > primary > convenience > ... > rumor``):

* a filing-fact finding is ``verified_fact`` ONLY when the source authority is ``canonical``;
  the builder refuses to promote a lower-authority source up to a verified fact.
* a company / provider snapshot stays ``company_claim`` / ``reported_claim`` -- a
  ``provider_reported`` (convenience) read NEVER outranks a canonical SEC filing.
* an X/social or rumor-authority input NEVER drives a financial inflection: it is EXCLUDED
  (never read into a signal) and the exclusion is surfaced as an explicit, non-verified
  ``financial_read_incomplete`` gap. There is no path in this module that stamps a social
  input as a ``verified_fact`` or lets it reach a critical severity.

HONEST GAPS, NEVER A FABRICATED NUMBER. An ABSENT financial input is an explicit ``data_gaps``
note (never a guessed value); a snapshot event with no readable metric yields an explicit
``financial_read_incomplete`` finding carrying the gaps; a STALE input marks the finding stale
(never dropped).

ALERT ELIGIBILITY (020E policy, documented in AGENT_COVERAGE_MATRIX_012): a filing-fact-backed
inflection is review_required-eligible (up to ``elevated`` urgency); a company_claim / provider
snapshot inflection stays a lower-severity watch; a social/rumor input is capped at a narrative
watch and can NEVER produce a critical production-action -- and it never reaches this sensor at
all.

FIXTURE / LOCAL-FILE ONLY. The agent NEVER fetches live data, opens a socket, schedules,
streams, or touches a broker (there is no such affordance in this module). It emits qualitative
LABELS only -- never a number, score, rank, buy/sell/hold, order, or thesis.

Deterministic, stdlib-only, Python 3.9, OFFLINE. No network on import; ids are content-derived;
no wall-clock anywhere. No scheduler / broker / score.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Optional, Tuple

from .. import labels as _labels
from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS

__all__ = [
    "FINANCIAL_INFLECTION_FINDING_TYPES",
    "FINANCIAL_INFLECTION_SUBAGENTS",
    "FILING_FACT_INFLECTIONS",
    "SNAPSHOT_INFLECTIONS",
    "FINANCIAL_INFLECTION_FILING_EVENT_TYPES",
    "SNAPSHOT_METRIC_KEYS",
    "FinancialInflectionAgent",
    "has_financial_inflection_events",
]

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.financial_inflection descriptor.        #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.financial_inflection"
_DISCIPLINE = "financial_inflection"

# The six discipline-scoped subagents (AGENT_MAP_012 §3.3), verbatim from the registry.
FINANCIAL_INFLECTION_SUBAGENTS: Tuple[str, ...] = (
    "Revenue Acceleration",
    "Margin",
    "Cash/Debt",
    "Dilution",
    "Capex",
    "Free Cash Flow",
)

# The finding types this agent may produce -- financial-condition LABELS, never a trade.
FINANCIAL_INFLECTION_FINDING_TYPES: Tuple[str, ...] = (
    "dilution_inflection",
    "guidance_inflection",
    "restatement_inflection",
    "insider_inflection",
    "revenue_acceleration",
    "revenue_deceleration",
    "margin_inflection",
    "leverage_inflection",
    "free_cash_flow_inflection",
    "capex_inflection",
    "financial_read_incomplete",
)

# Finding types that assert a FILING FACT -- verified_fact ONLY from a canonical SEC filing.
FILING_FACT_INFLECTIONS: Tuple[str, ...] = (
    "dilution_inflection", "guidance_inflection", "restatement_inflection",
    "insider_inflection")

# Finding types that are a LOCAL fundamental-snapshot read -- company/provider claim, never a fact.
SNAPSHOT_INFLECTIONS: Tuple[str, ...] = (
    "revenue_acceleration", "revenue_deceleration", "margin_inflection",
    "leverage_inflection", "free_cash_flow_inflection", "capex_inflection")

# 020B SEC filing event_types (from sec_edgar_live) this sensor reads as financial inflections.
# event_type -> (subagent, finding_type). The default 8-K material-agreement / contract types
# are DELIBERATELY excluded, so a pulse carrying only those (the bundled default) does NOT
# trigger this sensor -- the default pulse output stays byte-identical.
FINANCIAL_INFLECTION_FILING_EVENT_TYPES: Dict[str, Tuple[str, str]] = {
    "sec_s-1_registration": ("Dilution", "dilution_inflection"),
    "sec_s-3_shelf_registration": ("Dilution", "dilution_inflection"),
    "sec_424b_prospectus_offering": ("Dilution", "dilution_inflection"),
    "sec_8-k_results_of_operations": ("Revenue Acceleration", "guidance_inflection"),
    "sec_8-k_restatement": ("Free Cash Flow", "restatement_inflection"),
    "sec_form_4_insider_transaction": ("Cash/Debt", "insider_inflection"),
}

# finding_type -> direction_label (closed DIRECTION_LABELS). guidance_inflection /
# insider_inflection / margin / leverage / fcf / capex follow their reading and are resolved at
# runtime, not here.
_TYPE_DIRECTION: Dict[str, str] = {
    "dilution_inflection": "deteriorating",
    "restatement_inflection": "deteriorating",
    "revenue_acceleration": "accelerating",
    "revenue_deceleration": "decelerating",
    "financial_read_incomplete": "neutral",
}

# Local fundamental-snapshot metric keys (DELTAS on numeric_values). A missing key is an
# explicit gap -- the inflection is NEVER computed from nothing, and a number is NEVER guessed.
_K_REVENUE_GROWTH_DELTA = "revenue_growth_delta_pct"   # change in the revenue GROWTH rate (pp)
_K_GROSS_MARGIN_DELTA = "gross_margin_delta_pct"
_K_OP_MARGIN_DELTA = "operating_margin_delta_pct"
_K_NET_LEVERAGE_DELTA = "net_leverage_delta_turns"     # change in net-debt/EBITDA (turns)
_K_NET_DEBT_CHANGE = "net_debt_change_pct"
_K_FCF_DELTA = "fcf_delta_pct"
_K_CAPEX_CHANGE = "capex_change_pct"

# The metrics a fundamental snapshot is expected to carry (for the explicit missing-input gap).
SNAPSHOT_METRIC_KEYS: Tuple[str, ...] = (
    _K_REVENUE_GROWTH_DELTA, _K_GROSS_MARGIN_DELTA, _K_OP_MARGIN_DELTA,
    _K_NET_LEVERAGE_DELTA, _K_NET_DEBT_CHANGE, _K_FCF_DELTA, _K_CAPEX_CHANGE)

# Optional filing-fact magnitude keys (raw observations -> LABELS; the finding carries no number).
_K_OFFERING_PCT = "offering_pct_of_shares"
_K_OFFERING_AMOUNT = "offering_amount_usd"
_K_GUIDANCE_CHANGE = "guidance_change_pct"
_K_SALE_VALUE = "sale_value_usd"
_K_INSIDER_BUY = "insider_purchase_value_usd"

# Thresholds (simple comparisons on supplied DELTAS; labels come out, never numbers).
REVENUE_ACCEL_DELTA_PCT_MIN = 3.0       # revenue-growth rate moved >= 3pp -> accel/decel
REVENUE_ACCEL_MAJOR_PCT = 8.0
MARGIN_DELTA_PCT_MIN = 1.0              # margin moved >= 1pp -> a margin turn
MARGIN_MAJOR_PCT = 3.0
LEVERAGE_DELTA_TURNS_MIN = 0.5         # net-debt/EBITDA moved >= 0.5x -> a leverage shift
NET_DEBT_CHANGE_PCT_MIN = 10.0
FCF_DELTA_PCT_MIN = 5.0
CAPEX_CHANGE_PCT_MIN = 15.0

_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")

# The 012G stamping marker: the per-source claim status travels in the summary so provenance is
# inspectable end-to-end (reality_mesh.sensors.news_filings.claim_status_of reads it back)
# WITHOUT adding a field to the frozen AgentFinding.
_CLAIM_MARKER = "claim_status="
_NOT_VERIFIED = "not independently verified"


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _sha8(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _num_in(event: RealityEvent, key: str) -> Optional[float]:
    """First numeric reading named ``key`` on ``event`` (else None). No fabrication."""
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


def _weakest_confidence(events: Tuple[RealityEvent, ...], cap: str = "") -> str:
    present = [e.confidence_label for e in events if e.confidence_label not in ("", "missing")]
    base = "moderate" if not present else min(
        present, key=lambda v: _CONFIDENCE_ORDER.index(v)
        if v in _CONFIDENCE_ORDER else len(_CONFIDENCE_ORDER))
    if cap and cap in _CONFIDENCE_ORDER:
        # A snapshot read is capped at a lower confidence (company/provider, not verified).
        if _CONFIDENCE_ORDER.index(base) > _CONFIDENCE_ORDER.index(cap):
            return cap
    return base


def _stale_note(events: Tuple[RealityEvent, ...]) -> Optional[str]:
    stale_ids = sorted(e.event_id for e in events if e.freshness_label in _FRESHNESS_STALE)
    if stale_ids:
        return "stale financial data preserved (not dropped): {0}".format(", ".join(stale_ids))
    return None


def _is_financial_filing_event(event: RealityEvent) -> bool:
    """True iff ``event`` is a 020B SEC filing event this sensor reads as an inflection."""
    return (event.discipline == "news_filings"
            and event.event_type in FINANCIAL_INFLECTION_FILING_EVENT_TYPES)


def has_financial_inflection_events(events: Iterable[RealityEvent]) -> bool:
    """True iff ``events`` carry anything the Financial Inflection agent can read.

    Used by ``run_pulse`` as the agent's conditional gate (the 014D/014F pattern): the agent
    joins a pulse ONLY when a ``financial_inflection`` fundamental-snapshot event exists OR a
    020B SEC filing event is a financial-inflection type (dilution / guidance / restatement /
    insider). The bundled default pulse carries neither (its only 8-K is a material-agreement
    contract), so the default pulse output stays byte-identical.
    """
    for event in events:
        if event.discipline == _DISCIPLINE:
            return True
        if _is_financial_filing_event(event):
            return True
    return False


# --------------------------------------------------------------------------- #
# Internal per-reading verdict (pure data, never an output object).             #
# --------------------------------------------------------------------------- #
class _Reading:
    """One financial-inflection interpretation of one input event. Never emitted."""

    __slots__ = ("subagent", "finding_type", "direction", "magnitude", "urgency", "detail",
                 "claim", "authority", "extra_gaps")

    def __init__(self, subagent, finding_type, direction, magnitude, urgency, detail,
                 claim, authority, extra_gaps=()):
        self.subagent = subagent
        self.finding_type = finding_type
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.detail = detail
        self.claim = claim
        self.authority = authority
        self.extra_gaps = tuple(extra_gaps)


# --------------------------------------------------------------------------- #
# Claim / authority resolution -- NEVER laundering (contract §C).                #
# --------------------------------------------------------------------------- #
def _resolve_filing(event: RealityEvent, finding_type: str) -> Tuple[str, str]:
    """Resolve ``(claim_status, source_authority)`` for a SEC filing-fact inflection.

    A filing fact is ``verified_fact`` at ``canonical`` authority ONLY when the source itself is
    canonical (an SEC filing). A non-canonical source is capped at ``company_claim`` -- the
    builder refuses to launder it up to a verified fact.
    """
    src_claim = (event.claim_status or "").strip()
    authority = event.source_authority or "convenience"
    if authority == "canonical" and src_claim in ("", "verified_fact"):
        return "verified_fact", "canonical"
    if src_claim == "verified_fact" and authority != "canonical":
        return "company_claim", authority
    return (src_claim or "company_claim"), authority


def _resolve_snapshot(event: RealityEvent) -> Tuple[str, str]:
    """Resolve ``(claim_status, source_authority)`` for a LOCAL fundamental snapshot.

    A company statement stays ``company_claim`` (company IR -> ``primary``); a provider read
    stays ``reported_claim`` (``provider_reported`` -> ``convenience``). It is NEVER canonical
    and NEVER a verified fact -- a ``provider_reported`` read cannot outrank a canonical SEC
    filing. A manual/analyst datum stays what it is (and is never canonical).
    """
    claim = (event.claim_status or "").strip() or "company_claim"
    if claim == "verified_fact":
        claim = "company_claim"          # a local snapshot is never a verified fact
    authority = event.source_authority or ""
    if authority in ("", "canonical"):
        authority = "primary" if claim == "company_claim" else "convenience"
    if authority == "canonical":
        authority = "primary"            # a snapshot is capped below canonical -- never outranks SEC
    return claim, authority


# --------------------------------------------------------------------------- #
# FinancialInflectionAgent                                                     #
# --------------------------------------------------------------------------- #
class FinancialInflectionAgent(SensorAgent):
    """Tattva Financial Inflection sensor. Emits ``FinancialInflectionFinding``s (labels only).

    Reads 020B SEC filing EVENTS (canonical facts) + LOCAL fundamental-snapshot fixtures
    (company/provider claims). SEC filing facts are verified_fact/canonical + higher confidence;
    snapshots stay company_claim/provider + lower confidence, marked not-verified; a social/rumor
    input NEVER drives an inflection. Missing input -> explicit gap (never a fabricated number);
    stale input marked stale, never dropped. Labels only; no score / rank / trade field.
    """

    _AGENT_NAME = "Financial Inflection"

    def __init__(self) -> None:
        # Reuse the built-in tattva.financial_inflection descriptor (single source of identity).
        self._descriptor = next(d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret SEC filing events + fundamental snapshots into FinancialInflectionFindings.

        Deterministic + offline: reads only the injected ``events``. SEC filing events (canonical)
        become verified_fact inflections; fundamental-snapshot events (financial_inflection
        discipline) become company/provider-claim inflections. A social/rumor snapshot is
        EXCLUDED (surfaced as a non-verified gap, never a driver). A snapshot with no readable
        metric surfaces an explicit ``financial_read_incomplete`` gap. Sorted by finding_id.
        """
        filings = [e for e in events if _is_financial_filing_event(e)]
        snapshots = [e for e in events if e.discipline == _DISCIPLINE]
        if not filings and not snapshots:
            return ()

        findings: List[AgentFinding] = []

        for event in sorted(filings, key=lambda e: e.event_id):
            reading = self._read_filing(event)
            if reading is not None:
                findings.append(self._build_finding(event, reading))

        for event in sorted(snapshots, key=lambda e: e.event_id):
            # SOCIAL / RUMOR guard: a narrative / rumor-authority input NEVER drives a financial
            # inflection. It is excluded and the exclusion is SURFACED as an explicit,
            # non-verified incomplete-read gap (never laundered into a verified fact).
            if (_labels.is_social_source(source_type=event.source_type, discipline=event.discipline)
                    or _labels.is_social_source_type(event.source_type)
                    or event.source_authority == "rumor"
                    or event.claim_status == "rumor"):
                findings.append(self._incomplete_finding(
                    event,
                    ["social/rumor input {0} EXCLUDED from financial_inflection -- a weak "
                     "narrative source never drives a financial signal (never a verified_fact, "
                     "never a production-action)".format(event.event_id)],
                    authority=event.source_authority or "rumor"))
                continue
            readings, gaps = self._read_snapshot(event)
            for reading in readings:
                findings.append(self._build_finding(event, reading))
            if not readings:
                findings.append(self._incomplete_finding(event, gaps, authority=""))

        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- SEC filing-fact reader (canonical) ------------------------------- #
    def _read_filing(self, event: RealityEvent) -> Optional[_Reading]:
        subagent, finding_type = FINANCIAL_INFLECTION_FILING_EVENT_TYPES[event.event_type]
        claim, authority = _resolve_filing(event, finding_type)
        gaps: List[str] = []
        direction = _TYPE_DIRECTION.get(finding_type, "")
        magnitude = "moderate"
        urgency = "elevated"        # filing-fact inflections are review_required-eligible

        if finding_type == "dilution_inflection":
            pct = _num_in(event, _K_OFFERING_PCT)
            amt = _num_in(event, _K_OFFERING_AMOUNT)
            if pct is not None:
                magnitude = "extreme" if pct >= 25 else ("major" if pct >= 10 else "moderate")
                detail = "SEC shelf/offering registration up to {0}% of shares".format(pct)
            elif amt is not None:
                magnitude = "major" if amt >= 1e8 else "moderate"
                detail = "SEC shelf/offering registration up to ${0:,.0f}".format(amt)
            else:
                detail = "SEC shelf/offering registration filed"
                gaps.append("offering size not disclosed on {0} (dilution magnitude "
                            "unquantified -- gap, not a guessed number)".format(event.event_id))
        elif finding_type == "guidance_inflection":
            change = _num_in(event, _K_GUIDANCE_CHANGE)
            text = "{0} {1}".format(event.event_type or "", event.observed_fact or "").lower()
            cut = any(t in text for t in ("cut", "lower", "reduce", "below", "warn", "miss",
                                          "shortfall", "decel"))
            if change is not None:
                cut = cut or change < 0
                magnitude = "major" if abs(change) >= 10 else "moderate"
                detail = "8-K Item 2.02 results -- guidance {0} {1}%".format(
                    "cut" if cut else "raised", abs(change))
            else:
                detail = "8-K Item 2.02 results -- guidance {0}".format("cut" if cut else "update")
                gaps.append("guidance change magnitude not disclosed on {0} (unquantified -- "
                            "gap, not fabricated)".format(event.event_id))
            direction = "deteriorating" if cut else "improving"
            urgency = "elevated" if cut else "watch"
        elif finding_type == "restatement_inflection":
            detail = "8-K Item 4.02 non-reliance -- prior financials restated (accounting-quality "
            detail += "inflection)"
        else:  # insider_inflection (Form 4)
            sale = _num_in(event, _K_SALE_VALUE)
            buy = _num_in(event, _K_INSIDER_BUY)
            if buy is not None and (sale is None or buy >= sale):
                direction = "improving"
                magnitude = "major" if buy >= 5e6 else "moderate"
                urgency = "watch"
                detail = "Form 4 insider PURCHASE of ${0:,.0f} (capital-structure signal)".format(buy)
            elif sale is not None:
                direction = "deteriorating"
                magnitude = "major" if sale >= 5e6 else "moderate"
                urgency = "elevated" if sale >= 5e6 else "watch"
                detail = "Form 4 insider SALE of ${0:,.0f} (capital-structure signal)".format(sale)
            else:
                direction = "deteriorating"
                urgency = "watch"
                detail = "Form 4 insider transaction reported (capital-structure signal)"
                gaps.append("insider transaction size not disclosed on {0} (magnitude "
                            "unquantified -- gap, not fabricated)".format(event.event_id))

        return _Reading(subagent, finding_type, direction, magnitude, urgency, detail,
                        claim, authority, gaps)

    # -- LOCAL fundamental-snapshot reader (company/provider claim) ------- #
    def _read_snapshot(self, event: RealityEvent) -> Tuple[List[_Reading], List[str]]:
        claim, authority = _resolve_snapshot(event)
        readings: List[_Reading] = []
        present = {name for name, _v, _u in event.numeric_values}
        verified_tail = " ({0}, {1})".format(claim, _NOT_VERIFIED)

        rev = _num_in(event, _K_REVENUE_GROWTH_DELTA)
        if rev is not None and abs(rev) >= REVENUE_ACCEL_DELTA_PCT_MIN:
            accel = rev > 0
            mag = "major" if abs(rev) >= REVENUE_ACCEL_MAJOR_PCT else "moderate"
            readings.append(_Reading(
                "Revenue Acceleration",
                "revenue_acceleration" if accel else "revenue_deceleration",
                "accelerating" if accel else "decelerating", mag, "watch",
                "revenue-growth rate {0} {1}pp{2}".format(
                    "accelerated" if accel else "decelerated", abs(rev), verified_tail),
                claim, authority))

        margin = _num_in(event, _K_OP_MARGIN_DELTA)
        margin_key = _K_OP_MARGIN_DELTA
        if margin is None:
            margin = _num_in(event, _K_GROSS_MARGIN_DELTA)
            margin_key = _K_GROSS_MARGIN_DELTA
        if margin is not None and abs(margin) >= MARGIN_DELTA_PCT_MIN:
            up = margin > 0
            mag = "major" if abs(margin) >= MARGIN_MAJOR_PCT else "moderate"
            readings.append(_Reading(
                "Margin", "margin_inflection", "improving" if up else "deteriorating", mag,
                "watch",
                "{0} margin {1} {2}pp{3}".format(
                    "operating" if margin_key == _K_OP_MARGIN_DELTA else "gross",
                    "expanded" if up else "contracted", abs(margin), verified_tail),
                claim, authority))

        lev = _num_in(event, _K_NET_LEVERAGE_DELTA)
        if lev is not None and abs(lev) >= LEVERAGE_DELTA_TURNS_MIN:
            up = lev > 0
            mag = "major" if abs(lev) >= 1.0 else "moderate"
            readings.append(_Reading(
                "Cash/Debt", "leverage_inflection", "deteriorating" if up else "improving", mag,
                "watch",
                "net leverage {0} {1}x turns{2}".format(
                    "rose" if up else "fell", abs(lev), verified_tail),
                claim, authority))
        else:
            debt = _num_in(event, _K_NET_DEBT_CHANGE)
            if debt is not None and abs(debt) >= NET_DEBT_CHANGE_PCT_MIN:
                up = debt > 0
                mag = "major" if abs(debt) >= 25 else "moderate"
                readings.append(_Reading(
                    "Cash/Debt", "leverage_inflection", "deteriorating" if up else "improving",
                    mag, "watch",
                    "net debt {0} {1}%{2}".format(
                        "rose" if up else "fell", abs(debt), verified_tail),
                    claim, authority))

        fcf = _num_in(event, _K_FCF_DELTA)
        if fcf is not None and abs(fcf) >= FCF_DELTA_PCT_MIN:
            up = fcf > 0
            mag = "major" if abs(fcf) >= 20 else "moderate"
            readings.append(_Reading(
                "Free Cash Flow", "free_cash_flow_inflection",
                "improving" if up else "deteriorating", mag, "watch",
                "free cash flow {0} {1}%{2}".format(
                    "improved" if up else "deteriorated", abs(fcf), verified_tail),
                claim, authority))

        capex = _num_in(event, _K_CAPEX_CHANGE)
        if capex is not None and abs(capex) >= CAPEX_CHANGE_PCT_MIN:
            up = capex > 0
            readings.append(_Reading(
                "Capex", "capex_inflection", "rising" if up else "falling", "moderate", "watch",
                "capex {0} {1}%{2}".format(
                    "rose" if up else "fell", abs(capex), verified_tail),
                claim, authority))

        # No readable metric at all -> an explicit gap (never a fabricated inflection).
        gaps: List[str] = []
        if not readings:
            missing = sorted(k for k in SNAPSHOT_METRIC_KEYS if k not in present)
            gaps.append(
                "fundamental snapshot {0} carried no readable inflection metric (absent: {1}) -- "
                "explicit gap, never a fabricated number".format(
                    event.event_id, ", ".join(missing) if missing else "all metrics"))
        return readings, gaps

    # -- finding builders ------------------------------------------------- #
    def _incomplete_finding(self, event: RealityEvent, gaps: List[str],
                            authority: str) -> AgentFinding:
        """Build the explicit ``financial_read_incomplete`` gap carrier (never a fabricated read)."""
        reading = _Reading(
            "", "financial_read_incomplete", "neutral", "minor", "watch",
            "financial inflection read incomplete", "inferred",
            authority or "convenience", gaps)
        return self._build_finding(event, reading, confidence_override="very_low")

    def _build_finding(self, event: RealityEvent, r: _Reading,
                       confidence_override: str = "") -> AgentFinding:
        companies = tuple(event.affected_companies or ())
        subject = companies[0] if companies else "unscoped"

        gaps: List[str] = list(r.extra_gaps)
        if not companies:
            gaps.append(
                "subject company not identified on {0} (finding subject unscoped -- surfaced, "
                "never guessed)".format(event.event_id))
        note = _stale_note((event,))
        if note:
            gaps.append(note)
        inherited_gaps = sorted(event.data_gaps)
        data_gaps = tuple(dict.fromkeys(gaps + inherited_gaps))

        # A canonical filing fact is higher-confidence; a snapshot / incomplete read is capped
        # lower (company/provider claim, not independently verified).
        if confidence_override:
            confidence = confidence_override
        elif r.claim == "verified_fact" and r.authority == "canonical":
            confidence = _weakest_confidence((event,))
        else:
            confidence = _weakest_confidence((event,), cap="low")

        corroboration = ("partially_corroborated"
                         if (r.claim == "verified_fact" and r.authority == "canonical")
                         else "uncorroborated")
        half_life = "weeks" if r.finding_type in ("dilution_inflection", "insider_inflection") \
            else "quarters"

        # The 012G stamping pattern: the source claim status + authority travel in the summary so
        # provenance is inspectable end-to-end (claim_status_of reads it back). A claim is NEVER
        # upgraded to a verified fact here.
        summary = "{0} [{1}] for {2}: {3} | {4}{5} | source_authority={6}".format(
            r.finding_type, r.subagent or "overall", subject, r.detail,
            _CLAIM_MARKER, r.claim, r.authority)

        finding_id = "finding.{0}.{1}.{2}.{3}".format(
            _DISCIPLINE, r.finding_type, _slug(subject), _sha8(event.event_id))

        return AgentFinding(
            finding_id=finding_id,
            agent_id=_AGENT_ID,
            agent_layer="reality_intelligence",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=(event.event_id,),
            finding_type=r.finding_type,
            finding_summary=summary,
            affected_companies=companies,
            affected_themes=tuple(event.affected_themes or ()),
            affected_sectors=tuple(event.affected_sectors or ()),
            direction_label=r.direction,
            magnitude_label=r.magnitude,
            urgency_label=r.urgency,
            confidence_label=confidence,
            freshness_label=_weakest_freshness((event,)),
            half_life=half_life,
            source_authority_summary=r.authority,
            corroboration_status=corroboration,
            contradiction_status="unopposed",
            evidence_refs=tuple(sorted(event.evidence_refs)),
            source_refs=tuple(sorted(event.source_refs)),
            conflicts=tuple(sorted(event.conflicts)),
            data_gaps=data_gaps,
            routing_targets=("TattvaSignalFusion",),
        )
