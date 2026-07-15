"""Operator-accepted investment UNIVERSE entries (UNIVERSE-DISCOVERY UD-3).

UD-1 (:mod:`reality_mesh.universe_discovery`) surfaces REAL, provenanced
:class:`~reality_mesh.universe_discovery.DiscoveredUniverseCandidate`s from the FMP screener
(convenience) and SEC EDGAR full-text search (canonical). UD-2 (the isolated, edge-only AI Research
Assistant, in a separate package this module NEVER imports) proposes UNVERIFIED AI leads that sit
DELIBERATELY OUTSIDE the evidence ladder. UD-3 is the final human link: the OPERATOR accepts a
ticker into the working universe -- but ONLY when it is GROUNDED against a REAL source.

HONESTY IS THE INVARIANT. This module mirrors the diligence-acceptance discipline
(:mod:`reality_mesh.investment_diligence`) one layer up:

* an :class:`AcceptedUniverseEntry` is the OPERATOR's decision, never a data claim -- the engine
  NEVER auto-accepts and NEVER auto-fills a field;
* it CANNOT exist ungrounded: an unverified AI suggestion (``ai_suggestion`` / unverified) with NO
  real grounding is REFUSED at construction AND at acceptance -- a lead may enter the universe only
  once it is GROUNDED against SEC / FMP (or, for a purely operator-attested entry, an explicit
  operator-supplied evidence ref);
* its ``source_authority`` is HONEST -- ``canonical`` only when SEC-grounded, ``convenience`` when
  screener-grounded, ``manual`` when operator-attested; it is NEVER ``ai_suggestion`` and NEVER
  laundered up to ``canonical`` off a convenience/AI basis;
* there is NO score / rank / rating and NO buy / sell / order / broker / trade field anywhere
  (``assert_no_trade_fields``-clean).

:func:`ground_universe_candidate` runs UD-1's OWN producers (screener and/or SEC full-text) to
confirm a ticker resolves to a REAL company for a theme, returning the real matching candidate(s) +
provenance or an honest gap. :func:`accept_universe_entry` is the ONLY producer of an accepted
entry: it validates the grounding, derives the honest authority, and persists append-only. A
CORRECTION is a NEW record referencing ``correction_of`` (never a mutation).

This slice is the ACCEPTANCE store + grounding + operator action ONLY. It does NOT build the theme
graph, does NOT wire the pulse, and does NOT touch lineage (UD-4). It NEVER imports the edge-only AI
assistant package -- for grounding, reality_mesh calls its OWN UD-1 discovery. Deterministic
(content-derived id + injected ``now``), stdlib-only, Python 3.9, OFFLINE. No network on import; the
lazy UD-1 grounding transport is mock-injected in tests (the real path is never exercised).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .labels import authority_rank
from .stores import AppendOnlyStore
from .universe_discovery import (
    DiscoveredUniverseCandidate,
    discover_via_fmp_screener,
    discover_via_sec_fulltext,
)
from .validation import assert_no_trade_fields

__all__ = [
    "ACCEPTED_UNIVERSE_SCHEMA_VERSION",
    "ACCEPTED_UNIVERSE_MODELS",
    "UNIVERSE_VERDICTS",
    "UNIVERSE_ORIGINS",
    "UNIVERSE_AUTHORITIES",
    "AI_SUGGESTION_AUTHORITY",
    "AcceptedUniverseEntry",
    "AcceptedUniverseStore",
    "UniverseGrounding",
    "accept_universe_entry",
    "accepted_universe",
    "entry_id_for",
    "ground_universe_candidate",
]

ACCEPTED_UNIVERSE_SCHEMA_VERSION = "accepted-universe.1"

# The operator's verdict on a candidate -- a closed decision, never a score. Only ``accepted``
# entries enter the working universe; a ``rejected`` entry is persisted honestly (an audit trail of
# the operator's decision) but is never returned by :func:`accepted_universe`.
UNIVERSE_VERDICTS: Tuple[str, ...] = ("accepted", "rejected")

# How an accepted entry ORIGINATED -- records HOW the lead reached the operator, and (crucially) that
# an AI suggestion was GROUNDED against a real source rather than taken on faith.
UNIVERSE_ORIGINS: Tuple[str, ...] = (
    "evidence_discovery",     # surfaced by UD-1 (real screener / SEC filing) directly
    "ai_suggestion_grounded",  # started as a UD-2 AI lead, then GROUNDED against SEC / FMP
    "operator_manual",        # operator-attested with an explicit operator-supplied evidence ref
)

# The ONLY honest authorities an accepted entry may carry. It INHERITS the grounding authority:
# canonical (SEC-grounded) / convenience (screener-grounded) / manual (operator-attested). It is
# NEVER ``ai_suggestion`` (the UD-2 non-authority) and NEVER canonical unless SEC-grounded.
UNIVERSE_AUTHORITIES: Tuple[str, ...] = ("canonical", "convenience", "manual")

# The UD-2 non-authority -- named here ONLY so it can be provably REFUSED. An entry may never carry
# it (a suggestion is grounded first; the grounding's authority is what the entry inherits).
AI_SUGGESTION_AUTHORITY = "ai_suggestion"

# Real UD-1 provenance ref shapes. A grounding ref is "real" only if it matches one of these -- the
# same tokens UD-1 stamps on a DiscoveredUniverseCandidate (sec_fulltext / fmp_screener). Any other
# string (e.g. an ``ai:suggestion`` id) is NOT real grounding.
_SEC_REF_PREFIXES = ("sec:fts/", "sec:cik/")
_FMP_REF_PREFIX = "fmp:screener/"


# --------------------------------------------------------------------------- #
# The typed accepted-entry contract (frozen, validated, trade/score-clean)      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AcceptedUniverseEntry:
    """One frozen record of ONE OPERATOR-accepted (or rejected) universe entry.

    It cannot exist ungrounded / dishonest: ``ticker`` / ``theme_id`` / ``theme_label`` /
    ``accepted_by`` / ``accepted_at`` are required; ``source_refs`` (the REAL grounding provenance)
    must be non-empty; ``source_authority`` must be one of :data:`UNIVERSE_AUTHORITIES` and may
    NEVER be ``ai_suggestion``; ``grounded_by`` (how it was grounded) is required; ``origin`` /
    ``verdict`` are closed. There is NO score / rank / rating field and NO trade affordance anywhere.
    Construction re-validates every invariant, so a bad record cannot be forged past the type.
    """

    entry_id: str = ""                 # REQUIRED, content-derived (from theme_id + ticker)
    ticker: str = ""                   # REQUIRED -- the accepted symbol
    theme_id: str = ""                 # REQUIRED -- the theme the operator files it under
    theme_label: str = ""              # REQUIRED -- the human-facing theme name
    source_refs: Tuple[str, ...] = field(default_factory=tuple)  # REQUIRED -- REAL grounding refs
    source_authority: str = ""         # canonical / convenience / manual -- NEVER ai_suggestion
    grounded_by: str = ""              # REQUIRED -- the UD-1 method+candidate id or operator ref
    origin: str = ""                   # closed: UNIVERSE_ORIGINS
    accepted_by: str = ""              # REQUIRED -- the operator who accepted it
    accepted_at: str = ""              # REQUIRED -- injected timestamp (no wall-clock)
    verdict: str = "accepted"          # closed: UNIVERSE_VERDICTS
    note: str = ""                     # operator note (optional)
    schema_version: str = ACCEPTED_UNIVERSE_SCHEMA_VERSION
    correction_of: str = ""            # id of a superseded entry ("" if not a correction)

    def __post_init__(self) -> None:
        for name in ("entry_id", "ticker", "theme_id", "theme_label", "grounded_by",
                     "accepted_by", "accepted_at"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "AcceptedUniverseEntry.{0} is required and must be non-empty -- the engine "
                    "never auto-fills it".format(name))
        if self.verdict not in UNIVERSE_VERDICTS:
            raise ValueError(
                "AcceptedUniverseEntry.verdict {0!r} invalid (allowed: {1})".format(
                    self.verdict, list(UNIVERSE_VERDICTS)))
        if self.origin not in UNIVERSE_ORIGINS:
            raise ValueError(
                "AcceptedUniverseEntry.origin {0!r} invalid (allowed: {1})".format(
                    self.origin, list(UNIVERSE_ORIGINS)))
        if self.source_authority == AI_SUGGESTION_AUTHORITY:
            raise ValueError(
                "AcceptedUniverseEntry.source_authority may never be 'ai_suggestion' -- an "
                "accepted entry inherits its GROUNDING authority (canonical / convenience / "
                "manual); an unverified AI lead cannot enter the universe as an authority")
        if self.source_authority not in UNIVERSE_AUTHORITIES:
            raise ValueError(
                "AcceptedUniverseEntry.source_authority {0!r} invalid -- an accepted entry is "
                "canonical (SEC-grounded) / convenience (screener-grounded) / manual "
                "(operator-attested)".format(self.source_authority))
        if not tuple(r for r in (self.source_refs or ()) if str(r or "").strip()):
            raise ValueError(
                "AcceptedUniverseEntry.source_refs is required and must be non-empty -- an entry "
                "with NO grounding provenance would be ungrounded (fabricated)")


# The contract (for registry / test introspection). Trade/score-clean.
ACCEPTED_UNIVERSE_MODELS = (AcceptedUniverseEntry,)


# --------------------------------------------------------------------------- #
# Deterministic content-derived id                                              #
# --------------------------------------------------------------------------- #
def entry_id_for(theme_id: str, ticker: str, *, accepted_at: str = "", verdict: str = "",
                 source_authority: str = "", grounded_by: str = "", accepted_by: str = "",
                 origin: str = "", note: str = "", correction_of: str = "") -> str:
    """A deterministic, content-derived entry id (no wall-clock, order-stable).

    The human-readable prefix is built from ``ticker`` + ``theme_id`` (the two the spec names); the
    digest folds in the rest of the record content so distinct acceptances -- and a later CORRECTION
    of one -- never collide on the same id, while a byte-identical re-acceptance is idempotent.
    """
    tk = str(ticker or "").strip().upper()
    theme = str(theme_id or "").strip()
    token = "\x1f".join([
        theme, tk,
        str(accepted_at or "").strip(),
        str(verdict or "").strip(),
        str(source_authority or "").strip(),
        str(grounded_by or "").strip(),
        str(accepted_by or "").strip(),
        str(origin or "").strip(),
        str(note or "").strip(),
        str(correction_of or "").strip(),
    ])
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return "auni:{0}:{1}".format(tk, digest)


# --------------------------------------------------------------------------- #
# APPEND-ONLY store (correction-not-mutation)                                    #
# --------------------------------------------------------------------------- #
class AcceptedUniverseStore(AppendOnlyStore):
    """The append-only log of operator-accepted :class:`AcceptedUniverseEntry` records.

    Composes :class:`~reality_mesh.stores.AppendOnlyStore`: NO update / delete / in-place mutation,
    and the base's credential / trade-field write refusal applies. A CORRECTION is a NEW record
    whose ``correction_of`` references the superseded entry id -- the original line is byte-unchanged
    forever. Re-accepting a byte-identical entry is idempotent by its content-derived id.
    """

    filename = "accepted_universe.jsonl"
    record_cls = AcceptedUniverseEntry
    id_field = "entry_id"
    timestamp_field = "accepted_at"
    ticker_fields = ("ticker",)
    theme_fields = ("theme_id", "theme_label")

    def accept(self, entry: AcceptedUniverseEntry) -> str:
        """Append ONE entry append-only; idempotent when byte-identical already present."""
        if entry in self.read_all():
            return entry.entry_id
        return self.append(entry)


def accepted_universe(store_dir: str) -> Tuple[AcceptedUniverseEntry, ...]:
    """The newest NON-SUPERSEDED ACCEPTED entries -- the current working universe.

    Reads the append-only store, drops any entry a later record CORRECTS (``correction_of``),
    collapses to the newest live record per (theme_id, ticker), and returns only those whose newest
    live verdict is ``accepted``. A ticker whose newest live record is a ``rejected`` correction is
    honestly excluded. Never fabricates a record; deterministic; offline.
    """
    records = AcceptedUniverseStore(store_dir).read_all()
    superseded = {str(r.correction_of).strip() for r in records if str(r.correction_of).strip()}
    live = [r for r in records if r.entry_id not in superseded]
    newest: Dict[Tuple[str, str], AcceptedUniverseEntry] = {}
    order = []
    for r in live:
        key = (r.theme_id, r.ticker)
        if key not in newest:
            order.append(key)
        newest[key] = r                                    # append order -> newest wins per key
    return tuple(newest[k] for k in order if newest[k].verdict == "accepted")


# --------------------------------------------------------------------------- #
# Grounding -- run UD-1's OWN producers to confirm a ticker is a REAL company    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UniverseGrounding:
    """The result of grounding ONE ticker/theme against UD-1: real match(es) + provenance, or a gap.

    ``grounded`` is True iff a REAL UD-1 producer surfaced the requested ticker for the theme.
    ``candidates`` are the matching :class:`DiscoveredUniverseCandidate`s (real, provenanced);
    ``source_refs`` is the union of their provenance; ``source_authority`` is the HIGHEST authority
    among them (canonical > convenience); ``grounded_by`` names the winning method + candidate id.
    A miss is an honest gap (``grounded`` False, empty refs, ``data_gaps`` explaining why) -- never
    a fabricated match. Trade/score-clean.
    """

    ticker: str = ""
    theme_hint: str = ""
    grounded: bool = False
    candidates: Tuple[DiscoveredUniverseCandidate, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_authority: str = ""
    grounded_by: str = ""
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    checked_at: str = ""


def ground_universe_candidate(*, ticker: str, theme_hint: str,
                              env: Optional[Dict[str, str]] = None,
                              transport: Optional[Dict[str, Any]] = None,
                              now: str = "") -> UniverseGrounding:
    """Ground ONE ticker/theme by running UD-1's OWN producers. The GROUNDING primitive.

    Runs SEC EDGAR full-text search (canonical) over ``theme_hint`` and the FMP company screener
    (convenience) over it, then keeps ONLY the surfaced candidates whose ticker == ``ticker`` -- so
    the result confirms the ticker is a REAL company a real source surfaced for the theme. ``env``
    supplies credential PRESENCE (value never echoed / stored); ``transport`` injects mock UD-1
    transports (a ``{"sec": <sec bundle>, "fmp": <screen callable>}`` dict) so tests run OFFLINE and
    the real network path is NEVER exercised. A miss is an honest gap, never a fabricated match.
    Deterministic (injected ``now``); reality_mesh calls its OWN UD-1 -- it NEVER imports the AI
    assistant. No graph / pulse / lineage touched.
    """
    symbol = str(ticker or "").strip().upper()
    theme = str(theme_hint or "").strip()
    if not symbol:
        raise ValueError("ground_universe_candidate requires a non-empty ticker")

    transport = dict(transport or {})
    sec_transport = transport.get("sec")
    fmp_transport = transport.get("fmp")

    gaps = []
    matches = []

    if theme:
        sec_result = discover_via_sec_fulltext(
            theme, transport=sec_transport, env=env, now=now)
        gaps.extend(sec_result.data_gaps)
        matches.extend(c for c in sec_result.candidates if c.ticker == symbol)

    fmp_result = discover_via_fmp_screener(
        sector=theme, transport=fmp_transport, env=env, now=now)
    gaps.extend(fmp_result.data_gaps)
    matches.extend(c for c in fmp_result.candidates if c.ticker == symbol)

    if not matches:
        gaps.append(
            "universe grounding for {0!r} (theme {1!r}) found no real UD-1 match -- honest gap, "
            "nothing fabricated; the ticker is not confirmed against SEC / FMP for this "
            "theme".format(symbol, theme))
        return UniverseGrounding(
            ticker=symbol, theme_hint=theme, grounded=False,
            data_gaps=tuple(dict.fromkeys(gaps)), checked_at=str(now or ""))

    best = max(matches, key=lambda c: authority_rank(c.source_authority))
    refs = tuple(dict.fromkeys(r for c in matches for r in c.source_refs))
    grounded_by = "{0}:{1}".format(best.discovery_method, best.candidate_id)
    return UniverseGrounding(
        ticker=symbol, theme_hint=theme, grounded=True,
        candidates=tuple(matches), source_refs=refs,
        source_authority=best.source_authority, grounded_by=grounded_by,
        data_gaps=tuple(dict.fromkeys(gaps)), checked_at=str(now or ""))


# --------------------------------------------------------------------------- #
# Grounding-ref classification helpers                                          #
# --------------------------------------------------------------------------- #
def _is_sec_ref(ref: str) -> bool:
    return any(ref.startswith(p) for p in _SEC_REF_PREFIXES)


def _is_fmp_ref(ref: str) -> bool:
    return ref.startswith(_FMP_REF_PREFIX)


def _is_real_ud1_ref(ref: str) -> bool:
    """True iff ``ref`` is a REAL UD-1 provenance ref shape (sec:fts/ , sec:cik/ , fmp:screener/)."""
    return _is_sec_ref(ref) or _is_fmp_ref(ref)


def _authority_from_refs(refs: Tuple[str, ...]) -> str:
    """The honest authority implied by real UD-1 refs: SEC -> canonical, screener -> convenience.

    Returns "" when NO ref is a real UD-1 shape (i.e. there is no real grounding here).
    """
    if any(_is_sec_ref(r) for r in refs):
        return "canonical"
    if any(_is_fmp_ref(r) for r in refs):
        return "convenience"
    return ""


# --------------------------------------------------------------------------- #
# The ONLY producer of an accepted entry                                         #
# --------------------------------------------------------------------------- #
def accept_universe_entry(store_dir: str, *, ticker: str, theme_id: str, theme_label: str,
                          accepted_by: str, now: str, grounding_refs: Tuple[str, ...] = (),
                          origin: str = "evidence_discovery", verdict: str = "accepted",
                          note: str = "", correction_of: str = "",
                          env: Optional[Dict[str, str]] = None,
                          transport: Optional[Dict[str, Any]] = None) -> AcceptedUniverseEntry:
    """Record ONE operator-accepted universe entry append-only. The ONLY path to an accepted entry.

    NEVER auto-generates or auto-fills anything -- the operator supplies the theme, their name, and
    the note. VALIDATES the grounding before persisting (raising ``ValueError`` -- honestly refusing
    -- on any gap):

    * ``accepted_by`` and an injected ``now`` are non-empty; ``ticker`` / ``theme_id`` /
      ``theme_label`` are non-empty; ``origin`` / ``verdict`` are closed members;
    * the entry is GROUNDED. For ``origin="operator_manual"`` the operator MUST supply an explicit
      evidence ref in ``grounding_refs`` (authority ``manual``). Otherwise the grounding must be
      REAL UD-1 provenance: either ``grounding_refs`` already carry real UD-1-shaped refs
      (``sec:fts/`` / ``sec:cik/`` / ``fmp:screener/``), OR the ticker is grounded live via
      :func:`ground_universe_candidate` (mock transport in tests). An entry whose ONLY basis is an
      unverified AI suggestion with NO real grounding is REFUSED -- it cannot enter the universe.
    * ``source_authority`` is DERIVED from the grounding (SEC -> canonical, screener -> convenience,
      operator -> manual) -- never taken on faith, never ``ai_suggestion``, never canonical unless
      SEC-grounded;
    * ``correction_of`` (if given) must reference an existing persisted entry for this ticker.

    Persists the frozen :class:`AcceptedUniverseEntry` (content-derived id, injected ``accepted_at``
    = ``now``) and returns it. ``env`` / ``transport`` are passed to the lazy UD-1 grounding call
    (offline in tests; the real network path is never exercised on import or here). No broker /
    order / trade path. Does NOT touch the theme graph / pulse / lineage (UD-4).
    """
    if not str(store_dir or "").strip():
        raise ValueError("accept_universe_entry requires a non-empty store_dir")
    symbol = str(ticker or "").strip().upper()
    theme = str(theme_id or "").strip()
    label = str(theme_label or "").strip()
    accepted = str(accepted_by or "").strip()
    accepted_at = str(now or "").strip()
    origin_clean = str(origin or "").strip()
    verdict_clean = str(verdict or "").strip()
    note_clean = str(note or "").strip()
    correction = str(correction_of or "").strip()
    supplied_refs = tuple(
        str(r or "").strip() for r in (grounding_refs or ()) if str(r or "").strip())

    if not symbol:
        raise ValueError("accept_universe_entry requires a non-empty ticker")
    if not theme:
        raise ValueError("accept_universe_entry requires a non-empty theme_id")
    if not label:
        raise ValueError("accept_universe_entry requires a non-empty theme_label")
    if not accepted:
        raise ValueError(
            "accepted_by is required -- an accepted entry names the operator who accepted it; "
            "the engine never accepts on its own")
    if not accepted_at:
        raise ValueError(
            "accept_universe_entry requires an injected 'now' -- accepted_at is never a "
            "wall-clock read")
    if origin_clean not in UNIVERSE_ORIGINS:
        raise ValueError(
            "origin {0!r} invalid (allowed: {1})".format(origin_clean, list(UNIVERSE_ORIGINS)))
    if verdict_clean not in UNIVERSE_VERDICTS:
        raise ValueError(
            "verdict {0!r} invalid (allowed: {1})".format(verdict_clean, list(UNIVERSE_VERDICTS)))

    # -- determine the grounding: real UD-1 provenance, or an operator-attested evidence ref -- #
    if origin_clean == "operator_manual":
        # An operator ATTESTS the entry with their own explicit evidence ref. Authority is manual;
        # it is NEVER laundered up to canonical/convenience even if a real UD-1 ref is also present.
        if not supplied_refs:
            raise ValueError(
                "origin 'operator_manual' requires an explicit operator-supplied evidence ref in "
                "grounding_refs -- an operator-attested entry may not be ungrounded")
        source_refs = supplied_refs
        source_authority = "manual"
        grounded_by = "operator_evidence:{0}".format(supplied_refs[0])
    else:
        real_supplied = tuple(r for r in supplied_refs if _is_real_ud1_ref(r))
        if real_supplied:
            source_refs = real_supplied
            source_authority = _authority_from_refs(real_supplied)
            grounded_by = "ud1_refs:{0}".format(real_supplied[0])
        else:
            grounding = ground_universe_candidate(
                ticker=symbol, theme_hint=(label or theme), env=env,
                transport=transport, now=accepted_at)
            if not grounding.grounded:
                raise ValueError(
                    "refusing to accept {0} into the universe -- it is NOT grounded against any "
                    "real UD-1 source (SEC / FMP). An unverified AI suggestion cannot enter the "
                    "universe without grounding; supply real grounding_refs, or ground the ticker "
                    "against SEC / FMP first, or use origin='operator_manual' with an explicit "
                    "operator evidence ref. Nothing written.".format(symbol))
            source_refs = grounding.source_refs
            source_authority = grounding.source_authority
            grounded_by = grounding.grounded_by

    # A defensive re-assertion of the honesty invariant before we build the record.
    if source_authority not in UNIVERSE_AUTHORITIES:
        raise ValueError(
            "grounding produced a non-honest authority {0!r} -- refusing (nothing written)".format(
                source_authority))

    # -- a correction must reference an existing persisted entry for this ticker -- #
    if correction:
        known = {r.entry_id for r in AcceptedUniverseStore(store_dir).read_all()
                 if r.ticker == symbol}
        if correction not in known:
            raise ValueError(
                "correction_of {0!r} references no persisted universe entry for {1} -- a "
                "correction supersedes a REAL prior record".format(correction, symbol))

    entry = AcceptedUniverseEntry(
        entry_id=entry_id_for(
            theme, symbol, accepted_at=accepted_at, verdict=verdict_clean,
            source_authority=source_authority, grounded_by=grounded_by, accepted_by=accepted,
            origin=origin_clean, note=note_clean, correction_of=correction),
        ticker=symbol,
        theme_id=theme,
        theme_label=label,
        source_refs=tuple(source_refs),
        source_authority=source_authority,
        grounded_by=grounded_by,
        origin=origin_clean,
        accepted_by=accepted,
        accepted_at=accepted_at,
        verdict=verdict_clean,
        note=note_clean,
        correction_of=correction)
    AcceptedUniverseStore(store_dir).accept(entry)
    return entry


# --------------------------------------------------------------------------- #
# Construction-time guards: the contracts carry NO trade / score field.          #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(AcceptedUniverseEntry)
assert_no_trade_fields(UniverseGrounding)
