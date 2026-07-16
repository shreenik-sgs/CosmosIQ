"""The engine composes its own universe (UNIVERSE-DISCOVERY UD-5, ADR-0011).

This is the caller UD-1 never had. Discovery could always see -- run against real credentials it
returns grounded candidates from a filing search -- but nothing invoked it, nothing persisted it,
and acceptance refused to run unattended, so the universe stayed a hand-typed list and
``accepted_universe.jsonl`` never once existed. ADR-0011 settled why that was wrong: admitting a
company places no capital, sends no order, and is superseded by an append-only correction. It is a
belief, and "what can be undone may be done freely" (ADR-0010). This module is that freedom, used.

HOW A COMPANY EARNS ITS PLACE. For each REAL chokepoint in the value-chain map, the mandate
(:mod:`reality_mesh.universe_mandate`) directs a filing search at the capacity that gates it. A
company whose own SEC filing discusses operating there has grounded its own occupancy, in its own
words. The engine reads the filing and records what it found; it never decides the company belongs.
That is the whole mechanism, and its honesty rests on the engine adding nothing to the evidence.

WHAT AUTONOMY DOES NOT TOUCH (ADR-0011):

* **The evidence gate.** Every entry goes through the unchanged :func:`accept_universe_entry`, whose
  grounding validation is identical for both principals. What could not be accepted by a person on
  the evidence is not accepted by the engine on it.
* **The signature.** The engine signs as ITSELF -- ``accepted_by_kind="engine"``, naming its policy
  -- and can no more write a person's name than a person can claim the engine's prefix. Automating
  the decision is safe; automating the signature is not.
* **The chokepoint map.** A chokepoint is never invented to admit a company. Only chokepoints mapped
  BEFORE the sweep may be swept, so the engine cannot widen its own bound.
* **The bound.** Only chokepoint occupancy admits. A sector query returns fifty names; fifty names
  is a directory, not a universe.
* **Standing.** Admission means "worth watching", never "worth owning". No score, no rank, no rating
  -- here or anywhere downstream of here.

Deterministic given its inputs (order-stable by graph order, then mandate order, then discovery
order; ``now`` is injected, never read). Network happens ONLY inside UD-1's producers, and only when
a credential is present -- an absent credential is an honest gap, never a fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .accepted_universe import (
    ENGINE_PRINCIPAL_PREFIX,
    AcceptedUniverseEntry,
    accept_universe_entry,
    accepted_universe,
)
from .theme_graph import ThemeGraph
from .universe_discovery import (
    discover_via_fmp_screener,
    discover_via_sec_fulltext,
    merge_universe_discovery,
)
from .universe_mandate import MandateEntry, chokepoint_mandates

__all__ = [
    "DEFAULT_COMPOSE_POLICY",
    "ComposeResult",
    "compose_universe",
    "engine_principal",
]

# The policy the engine acts under, named in every record it signs. Changing the bound means
# changing this name -- so the store always says which rule admitted a company, forever.
DEFAULT_COMPOSE_POLICY = "ud5-chokepoint"


def engine_principal(policy: str = DEFAULT_COMPOSE_POLICY) -> str:
    """The engine's signature: the engine AND the policy it acted under (never a person)."""
    return "{0}{1}".format(ENGINE_PRINCIPAL_PREFIX, str(policy or "").strip()
                           or DEFAULT_COMPOSE_POLICY)


@dataclass(frozen=True)
class ComposeResult:
    """What one sweep did -- accepted, already-known, and every honest gap. No score / rank field."""

    accepted: Tuple[AcceptedUniverseEntry, ...] = field(default_factory=tuple)
    already_present: Tuple[str, ...] = field(default_factory=tuple)
    refused: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    chokepoints_swept: Tuple[str, ...] = field(default_factory=tuple)
    # Mentioned the chokepoint but is not in an industry that supplies it -- a CUSTOMER, not a
    # gatekeeper. Kept visible ("(TICKER, chokepoint)") rather than dropped: the pool the engine
    # considered and why it declined is part of the record, not swept under the rug.
    occupancy_not_established: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def tickers(self) -> Tuple[str, ...]:
        out: List[str] = []
        for entry in self.accepted:
            if entry.ticker not in out:
                out.append(entry.ticker)
        return tuple(out)


def _existing_pairs(store_dir: str) -> set:
    """(theme_id, ticker) already live in the universe -- a sweep never re-admits them."""
    return {(e.theme_id, e.ticker) for e in accepted_universe(store_dir)}


def compose_universe(store_dir: str, *, now: str,
                     env: Optional[Dict[str, str]] = None,
                     graph: Optional[ThemeGraph] = None,
                     sec_transport: Optional[Dict[str, Any]] = None,
                     fmp_transport: Optional[Any] = None,
                     policy: str = DEFAULT_COMPOSE_POLICY,
                     mandates: Optional[Tuple[MandateEntry, ...]] = None) -> ComposeResult:
    """Sweep every mandated chokepoint and admit what the filings ground. Returns what it did.

    For each real chokepoint carrying a mandate, each phrase is searched; a candidate that yields a
    ticker and real grounding refs is accepted under that chokepoint's theme, signed by the engine.
    A candidate already in the universe is skipped rather than duplicated. A candidate the evidence
    gate refuses is recorded in ``refused`` with the reason -- surfaced, never silently dropped, and
    never forced through. Discovery's own gaps (an unmappable filing hit, an absent credential) pass
    through to ``data_gaps`` untouched.

    ``now`` is injected (no wall-clock). ``env`` supplies credential PRESENCE to UD-1; without it the
    producers take an honest credential gap and this sweep admits nothing -- it does not fall back.
    """
    if not str(now or "").strip():
        raise ValueError("compose_universe requires an injected `now` -- the engine reads no clock")

    entries = mandates if mandates is not None else chokepoint_mandates(graph)
    signature = engine_principal(policy)

    accepted: List[AcceptedUniverseEntry] = []
    already: List[str] = []
    refused: List[str] = []
    gaps: List[str] = []
    swept: List[str] = []

    seen = _existing_pairs(store_dir)

    not_occupant: List[str] = []

    for mandate in entries:
        swept.append(mandate.bottleneck_id)

        # -- the OCCUPANCY half: who is in an industry that SUPPLIES this capacity? -------- #
        # The industry is grounded by the query that returned the company, not inferred from it.
        # Without this set the sweep would admit anyone who merely NAMED the chokepoint.
        occupant_pool: set = set()
        for industry in mandate.occupant_industries:
            try:
                screened = discover_via_fmp_screener(
                    industry=industry, limit=1000, env=env, now=now, transport=fmp_transport)
            except Exception as exc:
                gaps.append(
                    "occupancy screen failed for industry {0!r} at chokepoint {1} ({2}) -- honest "
                    "gap; without it this chokepoint admits nobody rather than admitting "
                    "everybody".format(industry, mandate.bottleneck_id, type(exc).__name__))
                continue
            gaps.extend(str(g) for g in (screened.data_gaps or ()))
            for row in screened.candidates:
                symbol = str(row.ticker or "").strip().upper()
                if symbol:
                    occupant_pool.add(symbol)
        if not occupant_pool:
            gaps.append(
                "no occupancy pool for chokepoint {0} -- admitting nothing here (a mention alone "
                "is not occupancy)".format(mandate.bottleneck_id))
            continue

        results = []
        for phrase in mandate.phrases:
            try:
                results.append(discover_via_sec_fulltext(
                    phrase, env=env, now=now, transport=sec_transport))
            except Exception as exc:      # a producer failure is a GAP, never a fabricated result
                gaps.append(
                    "discovery failed for {0!r} at chokepoint {1} ({2}) -- honest gap, nothing "
                    "invented".format(phrase, mandate.bottleneck_id, type(exc).__name__))
        if not results:
            continue
        merged = merge_universe_discovery(*results)
        gaps.extend(str(g) for g in (merged.data_gaps or ()))

        for candidate in merged.candidates:
            ticker = str(candidate.ticker or "").strip().upper()
            if not ticker:
                continue      # UD-1 already recorded the unmappable hit as a gap; never guess one
            # -- the BOUND (ADR-0011): occupancy, not mention. A company that names the chokepoint
            # but supplies none of its capacity is a customer of it. Ford ships ADAS; Ford does not
            # gate ADAS. Declined, and recorded so the decline is auditable.
            if ticker not in occupant_pool:
                not_occupant.append("{0} @ {1}".format(ticker, mandate.bottleneck_id))
                continue
            pair = (mandate.theme_id, ticker)
            if pair in seen:
                already.append(ticker)
                continue
            try:
                entry = accept_universe_entry(
                    store_dir,
                    ticker=ticker,
                    theme_id=mandate.theme_id,
                    theme_label=mandate.theme_name,
                    accepted_by=signature,
                    accepted_by_kind="engine",
                    now=now,
                    grounding_refs=tuple(candidate.source_refs or ()),
                    origin="evidence_discovery",
                    note=("admitted at chokepoint {0} ({1}) -- the company's own filing places it "
                          "there; monitored input, never a recommendation".format(
                              mandate.bottleneck_id, mandate.bottleneck_name)),
                    env=env)
            except ValueError as exc:
                # The evidence gate said no. It says no to the engine exactly as it would to a
                # person -- that is the point. Surface it; never force it.
                refused.append("{0} @ {1}: {2}".format(ticker, mandate.bottleneck_id, str(exc)[:120]))
                continue
            seen.add(pair)
            accepted.append(entry)

    return ComposeResult(
        accepted=tuple(accepted),
        already_present=tuple(already),
        refused=tuple(refused),
        data_gaps=tuple(gaps),
        chokepoints_swept=tuple(swept),
        occupancy_not_established=tuple(not_occupant))
