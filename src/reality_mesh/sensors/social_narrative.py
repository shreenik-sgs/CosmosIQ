"""The X / Social Narrative sensor agent for the Reality Mesh (IMPLEMENTATION-012H).

The STRICTEST Tattva sensor, mirroring the 012D :mod:`reality_mesh.sensors.market_regime` /
012G :mod:`reality_mesh.sensors.news_filings` pattern (SensorAgent + fixture loader +
``run_checked`` + finding construction). :class:`SocialNarrativeAgent` reads FIXTURE-backed
social-mention / account-metadata / theme-ticker-mention
:class:`~reality_mesh.models.RealityEvent`s and produces ``NarrativeFinding``-family findings
(each an :class:`~reality_mesh.models.AgentFinding` in the ``narrative`` discipline). It reuses
the built-in ``tattva.narrative`` descriptor (AGENT_MAP_012 §3.3) and passes
:meth:`~reality_mesh.agents.SensorAgent.run_checked`.

X / SOCIAL CANNOT CONFIRM FACTS (ARCHITECTURE_CONTRACT_012 §C -- the non-negotiable rule):

* EVERY finding is ``source_authority_summary="rumor"`` -- NEVER ``verified_fact`` / ``canonical``.
  A social finding cannot create a high-confidence investment thesis. Findings default WEAK
  (low / very_low confidence) and ``corroboration_status="uncorroborated"``. Corroboration is a
  downstream, NON-social job (the 012C fusion may lift ``corroboration_status`` when a NON-social
  finding agrees about the same subject) but it NEVER lifts the authority: **rumor stays rumor.**
* The agent may only represent narrative velocity / attention / rumor / crowding / weak catalyst
  discovery / source-specific claims -- NEVER a fact, decision, trade, rank, or score.

ACCOUNT-TYPE -> CLAIM-STATUS FLAVOR. The account behind a post colours the *claim status* stamped
in the finding summary (via the 012G ``claim_status_of`` pattern -- NOT a new field), but NONE of
these ever become a ``verified_fact``:

* an official company / insider account -> ``company_claim`` (``CompanyClaimFinding``);
* a journalist / source account -> ``reported_claim`` (a ``NarrativeFinding``);
* an expert account -> a labelled expert narrative ``expert_narrative`` (``ExpertNarrativeFinding``);
* an unknown / anonymous account -> ``rumor`` (``RumorFinding``).

BOT / PROMOTER RISK IS VISIBLE. A promoter / bot-risk fixture yields a ``PromotionRiskFinding``
that VISIBLY flags the risk (in the summary, the conflicts, and an explicit data gap) -- it is
never silently filtered.

TEN SUBAGENTS (AGENT_MAP_012 §3.3 narrative), and the finding TYPES they emit:
**Watchlist Mention · Theme Mention · Expert Account · Journalist/Source Account ·
Company/Insider Account · Rumor Propagation · Promoter/Bot-Risk · Crowding · Catalyst Discovery ·
Narrative Change**.

HONEST GAPS. Missing account metadata / thin data -> explicit ``data_gaps`` (never fabricated);
a STALE input is marked ``freshness_label="stale"`` (never dropped) and records a data gap.

FIXTURE / MOCK ONLY. NO live X, NO scraping, NO credentials, NO network, no scheduler / streaming /
broker (there is no such affordance in this module). It emits qualitative LABELS only -- never a
number, score, rank, buy/sell/hold, order, or thesis, and none of these findings is an investment
decision.

Deterministic, stdlib-only, Python 3.9. No network on import; ids are content-derived; every
timestamp / ``now`` is an injected string (no wall-clock).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..agents import SensorAgent
from ..models import AgentFinding, RealityEvent
from ..registry import DEFAULT_DESCRIPTORS
from ..validation import assert_social_not_verified
from .market_regime import events_from_fixture  # reuse the 012D offline JSON loader
from .news_filings import claim_status_of  # reuse the in-summary claim-status stamp reader

# --------------------------------------------------------------------------- #
# Identity -- reuse the built-in tattva.narrative descriptor (AGENT_MAP_012).   #
# --------------------------------------------------------------------------- #
_AGENT_ID = "tattva.narrative"
_DISCIPLINE = "narrative"

# The ten narrative subagents (AGENT_MAP_012 §3.3 narrative), verbatim to the 012H scope.
SOCIAL_NARRATIVE_SUBAGENTS: Tuple[str, ...] = (
    "Watchlist Mention",
    "Theme Mention",
    "Expert Account",
    "Journalist/Source Account",
    "Company/Insider Account",
    "Rumor Propagation",
    "Promoter/Bot-Risk",
    "Crowding",
    "Catalyst Discovery",
    "Narrative Change",
)

# The finding TYPES this agent may produce. Each IS an AgentFinding (structural subtype
# ``NarrativeFinding``); the ``finding_type`` field carries one of these names.
SOCIAL_NARRATIVE_FINDING_TYPES: Tuple[str, ...] = (
    "NarrativeFinding",
    "ThemeNarrativeVelocityFinding",
    "RumorFinding",
    "CrowdingFinding",
    "PossibleCatalystFinding",
    "PromotionRiskFinding",
    "ExpertNarrativeFinding",
    "CompanyClaimFinding",
    "NarrativeRegimeChangeFinding",
)

# EVERY narrative finding carries this authority -- rumor, never higher (never verified_fact /
# canonical). A social source cannot confirm a fact however its account is flavoured.
_RUMOR_AUTHORITY = "rumor"

# The default (weak) posture: low / very_low confidence, uncorroborated. Social starts weak.
_DEFAULT_CONFIDENCE = "low"
_WEAKEST_CONFIDENCE = "very_low"

# finding_type -> direction_label (closed DIRECTION_LABELS). Attention / velocity read as
# rising/accelerating; a rumor has no confirmed direction (unknown); crowding + a narrative
# change read as reversing (a contrarian / regime-shift signature).
_TYPE_DIRECTION: Dict[str, str] = {
    "NarrativeFinding": "rising",
    "ThemeNarrativeVelocityFinding": "accelerating",
    "RumorFinding": "unknown",
    "CrowdingFinding": "reversing",
    "PossibleCatalystFinding": "rising",
    "PromotionRiskFinding": "unknown",
    "ExpertNarrativeFinding": "improving",
    "CompanyClaimFinding": "improving",
    "NarrativeRegimeChangeFinding": "reversing",
}

# Numeric keys the subagents read for magnitude (raw observations -> LABELS; the finding carries
# no number). A missing key is an explicit data gap, never fabricated.
_K_MENTIONS = "mention_count"
_K_VELOCITY = "mention_velocity_zscore"
_K_AUTHORS = "unique_authors"
_K_BOT = "bot_risk_pct"
_K_CROWD = "crowding_pct"

# Bearish content tokens -- flip a claim/expert/company finding's direction to a negative label.
_BEARISH_TOKENS = ("short", "bearish", "fraud", "warning", "negative", "downgrade", "sell-off")

_FRESHNESS_STALE = ("stale", "expired")
_FRESHNESS_REAL_ORDER = ("expired", "stale", "aging", "recent", "fresh")
_CONFIDENCE_ORDER = ("missing", "unknown", "very_low", "low", "moderate", "high", "very_high")

# The marker embedded in every finding_summary (reused verbatim from 012G news_filings) so a
# downstream reader can recover the account-derived claim status WITHOUT adding a field.
_CLAIM_MARKER = "claim_status="


# --------------------------------------------------------------------------- #
# Small pure helpers (labels / rollup, NO numeric output on any finding).       #
# --------------------------------------------------------------------------- #
def _num_in(event: RealityEvent, key: str) -> Optional[float]:
    """The numeric reading named ``key`` on ``event`` (else None). No fabrication."""
    for name, value, _unit in event.numeric_values:
        if name == key:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _text_of(event: RealityEvent) -> str:
    return "{0} {1} {2} {3}".format(
        event.event_type or "", event.observed_fact or "",
        event.source_id or "", event.source_type or "").lower()


def _weakest_freshness(event: RealityEvent) -> str:
    return event.freshness_label if event.freshness_label in _FRESHNESS_REAL_ORDER else "missing"


def _weakest_confidence(event: RealityEvent, floor: str) -> str:
    """The weaker of the event's own confidence and the finding ``floor`` (social starts weak)."""
    ev = event.confidence_label
    candidates = [c for c in (ev, floor) if c in _CONFIDENCE_ORDER and c != "missing"]
    if not candidates:
        return floor
    return min(candidates, key=lambda v: _CONFIDENCE_ORDER.index(v))


def _stale_note(event: RealityEvent) -> Optional[str]:
    if event.freshness_label in _FRESHNESS_STALE:
        return "stale social/narrative data preserved (not dropped): {0}".format(event.event_id)
    return None


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _magnitude_from_velocity(z: Optional[float]) -> str:
    if z is None:
        return "minor"
    if z >= 4:
        return "major"
    if z >= 2:
        return "moderate"
    return "minor"


# --------------------------------------------------------------------------- #
# Event -> (subagent, finding_type, claim_flavor) classification               #
# --------------------------------------------------------------------------- #
def _classify(event: RealityEvent) -> Tuple[str, str, str]:
    """Map an event to ``(subagent, finding_type, claim_flavor)``.

    A social event fed to the narrative agent is ALWAYS classified into a weak narrative finding
    (never dropped); the claim FLAVOR (company_claim / reported_claim / expert_narrative / rumor)
    reflects the account behind the post but NEVER promotes the finding to a verified fact.
    """
    text = _text_of(event)
    bot = _num_in(event, _K_BOT)

    # -- promoter / bot risk (highest precedence -- must stay visible) -------------- #
    if (bot is not None and bot >= 50) or any(
            t in text for t in ("promoter", "bot_", "botnet", "pump", "paid_promotion",
                                "astroturf", "shill", "coordinated")):
        return "Promoter/Bot-Risk", "PromotionRiskFinding", "rumor"

    # -- account-type claims (flavor the claim status; never a verified fact) -------- #
    if any(t in text for t in ("company_account", "official_account", "insider_account",
                               "verified_company", "company_ir", "insider")):
        return "Company/Insider Account", "CompanyClaimFinding", "company_claim"
    if any(t in text for t in ("journalist", "reporter", "press_account", "source_account",
                               "media_account", "newsroom")):
        return "Journalist/Source Account", "NarrativeFinding", "reported_claim"
    if any(t in text for t in ("expert_account", "expert", "analyst_account", "kol",
                               "thought_leader")):
        return "Expert Account", "ExpertNarrativeFinding", "expert_narrative"
    if any(t in text for t in ("unknown_account", "anon_account", "anonymous", "burner",
                               "throwaway")):
        return "Rumor Propagation", "RumorFinding", "rumor"

    # -- content classes ------------------------------------------------------------ #
    if any(t in text for t in ("rumor", "unconfirmed", "speculation", "leak", "whisper")):
        return "Rumor Propagation", "RumorFinding", "rumor"
    if any(t in text for t in ("crowd", "crowded", "consensus", "everyone_long", "overcrowded",
                               "packed_trade")):
        return "Crowding", "CrowdingFinding", "rumor"
    if any(t in text for t in ("catalyst", "upcoming_event", "possible_catalyst", "watch_for")):
        return "Catalyst Discovery", "PossibleCatalystFinding", "rumor"
    if any(t in text for t in ("narrative_change", "narrative_shift", "sentiment_flip",
                               "regime_change", "tone_shift", "narrative_regime")):
        return "Narrative Change", "NarrativeRegimeChangeFinding", "rumor"

    # -- theme velocity: a theme-scoped mention/velocity spike ----------------------- #
    theme_scoped = bool(event.affected_themes) and not event.affected_companies
    if any(t in text for t in ("theme_mention", "theme_velocity", "theme_spike",
                               "theme_buzz")) or (theme_scoped and any(
            t in text for t in ("mention", "velocity", "spike", "buzz", "attention"))):
        return "Theme Mention", "ThemeNarrativeVelocityFinding", "rumor"

    # -- default: a watchlist mention / attention spike (weak narrative) ------------- #
    return "Watchlist Mention", "NarrativeFinding", "rumor"


# --------------------------------------------------------------------------- #
# Internal subagent verdict (NOT an output object -- a plain mutable record).    #
# --------------------------------------------------------------------------- #
class _Reading:
    """One subagent's interpretation of one input event. Pure data, never emitted."""

    __slots__ = ("subagent", "finding_type", "claim_flavor", "direction", "magnitude", "urgency",
                 "confidence", "half_life", "summary", "event", "companies", "themes", "gaps",
                 "conflicts", "finding_id")

    def __init__(self, subagent, finding_type, claim_flavor, direction, magnitude, urgency,
                 confidence, half_life, summary, event, companies, themes, gaps, conflicts):
        self.subagent = subagent
        self.finding_type = finding_type
        self.claim_flavor = claim_flavor
        self.direction = direction
        self.magnitude = magnitude
        self.urgency = urgency
        self.confidence = confidence
        self.half_life = half_life
        self.summary = summary
        self.event = event
        self.companies = tuple(companies)
        self.themes = tuple(themes)
        self.gaps = list(gaps)
        self.conflicts = list(conflicts)
        subject = (self.companies or self.themes or ("unscoped",))[0]
        self.finding_id = "finding.narrative.{0}.{1}".format(
            _slug(finding_type), _slug(subject))


# --------------------------------------------------------------------------- #
# Assertion guard -- a narrative finding is NEVER a verified / canonical fact.   #
# --------------------------------------------------------------------------- #
def assert_narrative_not_verified(finding: AgentFinding) -> None:
    """Assert a narrative finding stays a rumor -- never a verified_fact / canonical.

    Raises ``AssertionError`` if the finding's authority is anything other than ``rumor`` or its
    stamped claim status is ``verified_fact`` / ``canonical``. This is the finding-side twin of
    the event-side :func:`~reality_mesh.validation.assert_social_not_verified` guard.
    """
    if finding.source_authority_summary != _RUMOR_AUTHORITY:
        raise AssertionError(
            "invariant violated: narrative finding {0!r} authority {1!r} (must be rumor)".format(
                finding.finding_id, finding.source_authority_summary))
    if claim_status_of(finding) in ("verified_fact", "canonical"):
        raise AssertionError(
            "invariant violated: narrative finding {0!r} marked verified_fact/canonical".format(
                finding.finding_id))


# --------------------------------------------------------------------------- #
# SocialNarrativeAgent                                                         #
# --------------------------------------------------------------------------- #
class SocialNarrativeAgent(SensorAgent):
    """FIXTURE-backed Tattva X/Social Narrative sensor. Emits weak ``NarrativeFinding``s only.

    Reads social-mention / account-metadata / theme-mention events and interprets each into a
    weak narrative finding: attention / velocity / rumor / crowding / weak catalyst / an
    account-flavoured claim -- ALWAYS at ``rumor`` authority, low/very_low confidence, and
    uncorroborated. NO finding is ever a verified fact; bot/promoter risk is made visible;
    missing metadata / stale input surface as explicit gaps. Labels only; no score / rank / trade
    field; not an investment decision.
    """

    _AGENT_NAME = "Narrative"

    def __init__(self) -> None:
        # Reuse the built-in tattva.narrative descriptor (single source of identity).
        self._descriptor = next(d for d in DEFAULT_DESCRIPTORS if d.agent_id == _AGENT_ID)

    @property
    def descriptor(self):
        return self._descriptor

    # -- run ------------------------------------------------------------- #
    def run(self, context, events: Tuple[RealityEvent, ...]) -> Tuple[AgentFinding, ...]:
        """Interpret social-mention / account / theme-mention events into narrative findings.

        Deterministic + offline: reads only the injected ``events`` (from fixtures), classifies
        each into its subagent + weak finding type, stamps the account-derived claim flavor
        (never a verified fact), keeps authority at ``rumor``, makes bot/promoter risk visible,
        and surfaces missing/stale inputs as explicit gaps.
        """
        mine = tuple(e for e in events if e.discipline == _DISCIPLINE)

        readings: List[_Reading] = []
        for event in sorted(mine, key=lambda e: e.event_id):
            # Event-side guard: a rumor/X-social event can never enter as a verified_fact.
            assert_social_not_verified(event)
            readings.append(self._read_event(event))

        findings = [self._finding_from_reading(r) for r in readings]
        for f in findings:
            assert_narrative_not_verified(f)   # finding-side guard: rumor, never verified
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    # -- per-event reader ------------------------------------------------- #
    def _read_event(self, event: RealityEvent) -> _Reading:
        subagent, finding_type, claim_flavor = _classify(event)
        companies = tuple(event.affected_companies or ())
        themes = tuple(event.affected_themes or ())
        subject = (companies or themes or ("the tape",))[0]

        gaps: List[str] = []
        conflicts: List[str] = []

        if not companies and not themes:
            gaps.append(
                "subject (company/theme) not identified on {0} (narrative finding "
                "unscoped)".format(event.event_id))

        direction = _TYPE_DIRECTION.get(finding_type, "unknown")
        # Bearish content flips a claim/expert/company finding to a negative label.
        text = _text_of(event)
        if finding_type in ("CompanyClaimFinding", "ExpertNarrativeFinding") and any(
                t in text for t in _BEARISH_TOKENS):
            direction = "deteriorating"
        if finding_type == "NarrativeFinding" and claim_flavor == "reported_claim" and any(
                t in text for t in _BEARISH_TOKENS):
            direction = "falling"

        velocity = _num_in(event, _K_VELOCITY)
        mentions = _num_in(event, _K_MENTIONS)
        authors = _num_in(event, _K_AUTHORS)
        crowd = _num_in(event, _K_CROWD)
        bot = _num_in(event, _K_BOT)

        magnitude = "minor"
        urgency = "watch"
        confidence = _DEFAULT_CONFIDENCE
        half_life = "hours"
        detail = ""

        if finding_type == "PromotionRiskFinding":
            confidence = _WEAKEST_CONFIDENCE
            urgency = "elevated"
            magnitude = "major" if (bot is not None and bot >= 75) else "moderate"
            pct = "{0:.0f}%".format(bot) if bot is not None else "elevated (unquantified)"
            detail = "PROMOTER/BOT RISK on {0}: coordinated/inauthentic amplification " \
                     "(bot-risk {1})".format(subject, pct)
            conflicts.append(
                "PROMOTER/BOT RISK: narrative on {0} shows promoter/bot amplification "
                "(bot-risk {1}) -- attention is likely inauthentic; NOT evidence of a "
                "fact".format(subject, pct))
            gaps.append(
                "promoter/bot risk reduces reliability of the {0} narrative -- treat mention "
                "velocity as suspect, not corroboration".format(subject))
            if bot is None:
                gaps.append("bot-risk magnitude not quantified on {0}".format(event.event_id))
        elif finding_type == "ThemeNarrativeVelocityFinding":
            magnitude = _magnitude_from_velocity(velocity)
            detail = "theme narrative velocity spike for '{0}' (attention rising, NOT a " \
                     "confirmed rotation)".format(subject)
            if velocity is None:
                gaps.append("theme mention velocity (z-score) not disclosed on {0}".format(
                    event.event_id))
            if authors is None:
                gaps.append("unique-author breadth not disclosed on {0} (velocity may be a "
                            "single-account artefact)".format(event.event_id))
        elif finding_type == "RumorFinding":
            confidence = _WEAKEST_CONFIDENCE
            detail = "unverified rumor about {0} (uncorroborated; NOT a fact)".format(subject)
            gaps.append(
                "rumor about {0} is uncorroborated -- requires primary/canonical confirmation "
                "before any use".format(subject))
        elif finding_type == "CrowdingFinding":
            urgency = "elevated"
            half_life = "days"
            if crowd is not None:
                magnitude = "major" if crowd >= 70 else "moderate"
                detail = "narrative crowding on {0}: consensus/positioning heavy ({1:.0f}%)".format(
                    subject, crowd)
            else:
                magnitude = "moderate"
                detail = "narrative crowding on {0}: consensus heavy (contrarian risk)".format(
                    subject)
                gaps.append("crowding intensity not quantified on {0}".format(event.event_id))
        elif finding_type == "PossibleCatalystFinding":
            detail = "possible weak catalyst discovered for {0} via social chatter " \
                     "(unconfirmed lead, needs verification)".format(subject)
            gaps.append(
                "possible catalyst for {0} is a social lead only -- unverified; a discovery "
                "hint, not a confirmed catalyst".format(subject))
        elif finding_type == "ExpertNarrativeFinding":
            half_life = "days"
            detail = "expert-account narrative on {0} (labelled expert view; still rumor " \
                     "authority, NOT verified)".format(subject)
        elif finding_type == "CompanyClaimFinding":
            half_life = "days"
            detail = "company/insider-account claim on {0} (a company statement on social; " \
                     "company_claim, NOT an independently verified fact)".format(subject)
            gaps.append(
                "company/insider social account claim on {0} is unverified (could be "
                "impersonation/hack) -- company_claim only".format(subject))
        elif claim_flavor == "reported_claim":  # journalist / source account -> NarrativeFinding
            detail = "journalist/source-account report on {0} (reported_claim; not " \
                     "independently verified)".format(subject)
        elif finding_type == "NarrativeRegimeChangeFinding":
            urgency = "elevated"
            half_life = "days"
            detail = "narrative regime change around {0} (tone/sentiment shift, NOT a " \
                     "confirmed fundamental change)".format(subject)
        else:  # generic NarrativeFinding -- watchlist mention / attention spike
            magnitude = _magnitude_from_velocity(velocity)
            detail = "mention/attention spike for {0} (narrative velocity; attention, NOT a " \
                     "fact)".format(subject)
            if velocity is None and mentions is None:
                gaps.append("mention velocity/count not disclosed on {0}".format(event.event_id))
            if authors is None:
                gaps.append("unique-author breadth not disclosed on {0} (velocity may be a "
                            "single-account artefact)".format(event.event_id))

        summary = (
            "{0} [{1}] for {2}: {3} | claim_status={4} | source_authority=rumor | "
            "WEAK/uncorroborated (X/social never confirms a fact)".format(
                finding_type, subagent, subject, detail, claim_flavor))

        return _Reading(
            subagent=subagent, finding_type=finding_type, claim_flavor=claim_flavor,
            direction=direction, magnitude=magnitude, urgency=urgency,
            confidence=_weakest_confidence(event, confidence), half_life=half_life,
            summary=summary, event=event, companies=companies, themes=themes,
            gaps=gaps, conflicts=conflicts)

    # -- finding builder -------------------------------------------------- #
    def _finding_from_reading(self, r: _Reading) -> AgentFinding:
        evs = (r.event,)
        gaps: List[str] = list(r.gaps)
        note = _stale_note(r.event)
        if note:
            gaps.append(note)

        evidence_refs = tuple(sorted({ref for e in evs for ref in e.evidence_refs}))
        source_refs = tuple(sorted({ref for e in evs for ref in e.source_refs}))
        inherited_conflicts = sorted({c for e in evs for c in e.conflicts})
        conflicts = tuple(dict.fromkeys(list(r.conflicts) + inherited_conflicts))
        inherited_gaps = sorted({g for e in evs for g in e.data_gaps})
        data_gaps = tuple(dict.fromkeys(gaps + inherited_gaps))

        return AgentFinding(
            finding_id=r.finding_id,
            agent_id=_AGENT_ID,
            agent_layer="Tattva",
            agent_name=self._AGENT_NAME,
            discipline=_DISCIPLINE,
            input_events=(r.event.event_id,),
            finding_type=r.finding_type,
            finding_summary=r.summary,
            affected_companies=r.companies,
            affected_themes=r.themes,
            direction_label=r.direction,
            magnitude_label=r.magnitude,
            urgency_label=r.urgency,
            confidence_label=_weakest_confidence(r.event, r.confidence),
            freshness_label=_weakest_freshness(r.event),
            half_life=r.half_life,
            source_authority_summary=_RUMOR_AUTHORITY,   # ALWAYS rumor -- never verified/canonical
            corroboration_status="uncorroborated",       # social starts uncorroborated
            contradiction_status="unopposed",
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            conflicts=conflicts,
            data_gaps=data_gaps,
            routing_targets=("TattvaSignalFusion",),
        )
