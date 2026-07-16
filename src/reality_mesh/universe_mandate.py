"""The universe MANDATE -- what the engine is directed to look for (UNIVERSE-DISCOVERY UD-5).

ADR-0011 draws the line this module sits on:

    "Discovery is steered by a mandate -- a sector, a theme, a phrase -- and a mandate is not a
    watchlist. To name a domain worth investigating states an interest and leaves the engine to find
    who matters; to name the companies states the answer and leaves the engine nothing to find."

So a mandate is DIRECTION, and direction is legitimate architectural input. A ticker is an ANSWER,
and answering is the engine's job. This module therefore contains phrases and never symbols --
:func:`validate_mandate` refuses a ticker-shaped term at import-time so the file cannot quietly rot
back into the watchlist it replaced.

WHAT A MANDATE IS FOR. ADR-0011 bounds the universe by real chokepoint occupancy -- the scarce
capacity that gates a theme's advance. The bound is only meaningful if occupancy can be established
from EVIDENCE rather than asserted. A phrase is how: a company whose own SEC filing discusses
operating at a chokepoint has grounded its own occupancy, in its own words, under its own signature.
The engine reads that filing; it does not decide the company belongs. This is why a mandate maps to
a chokepoint that ALREADY EXISTS in the value-chain map (:mod:`reality_mesh.theme_graph`) -- per
ADR-0011 a chokepoint is never invented to admit a company, so a mandate can only point at
chokepoints mapped before it.

WHAT A MANDATE IS NOT. It is not a screen, not a score, not a ranking, and confers no standing. A
phrase matching a filing means the company operates at a chokepoint -- a structural fact about the
world. It does not mean the company is good, cheap, or worth owning; those are judgments formed
downstream, by an operator, under the gates that govern judgments.

Deterministic, stdlib-only, OFFLINE: no network, no wall-clock, no I/O at import.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .theme_graph import ThemeGraph, build_seed_theme_graph

__all__ = [
    "CHOKEPOINT_MANDATE",
    "MandateEntry",
    "chokepoint_mandates",
    "mandate_for",
    "validate_mandate",
]


# The phrases that identify a company OPERATING AT each real chokepoint, keyed by the chokepoint's
# ``bottleneck_id`` in the seed value-chain map. These are search terms for SEC full-text -- the
# language a company uses about itself when it is genuinely in that business.
#
# ADDING a chokepoint here does nothing unless that chokepoint is real in the graph: an id with no
# mapped chokepoint is refused, because a mandate may not conjure a chokepoint to admit companies to.
# ``phrases``            -- SEC full-text terms: the language a company uses when it operates here.
# ``occupant_industries`` -- the FMP industries that SUPPLY this capacity. This is the half that
#   distinguishes occupying a chokepoint from merely mentioning one. Ford's 10-K says "advanced
#   driver assistance systems" because Ford SHIPS them; Ford does not gate them. An Auto -
#   Manufacturers company is a customer of bn-av-sensor, never its chokepoint. So a mention alone
#   admits nobody: a company must ALSO be in an industry that provides the scarce capacity.
#   Both halves are real metadata -- the industry is grounded by the screener query that returned
#   the company, the mention by the company's own filing. Neither is inferred.
#   These strings are FMP's OWN industry vocabulary, read from the live screener -- not invented.
CHOKEPOINT_MANDATE: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "bn-advpkg": {
        "phrases": ("chip on wafer on substrate", "advanced packaging", "2.5D packaging"),
        "occupant_industries": ("Semiconductors", "Hardware, Equipment & Parts"),
    },
    "bn-hbm": {
        "phrases": ("high bandwidth memory", "high-bandwidth memory"),
        "occupant_industries": ("Semiconductors",),
    },
    "bn-dc-power": {
        "phrases": ("data center interconnection", "grid interconnection queue",
                    "behind the meter generation"),
        "occupant_industries": ("Electrical Equipment & Parts", "Independent Power Producers",
                                "Regulated Electric", "Renewable Utilities"),
    },
    "bn-av-sensor": {
        "phrases": ("automotive lidar", "advanced driver assistance systems",
                    "automotive grade sensor"),
        # Auto - Manufacturers is deliberately ABSENT: it consumes this capacity, never gates it.
        "occupant_industries": ("Semiconductors", "Auto - Parts", "Hardware, Equipment & Parts"),
    },
    "bn-transformer": {
        "phrases": ("large power transformer", "extra high voltage transformer"),
        "occupant_industries": ("Electrical Equipment & Parts", "Industrial - Machinery"),
    },
    "bn-transceiver": {
        "phrases": ("optical transceiver", "silicon photonics", "co-packaged optics"),
        "occupant_industries": ("Communication Equipment", "Semiconductors",
                                "Hardware, Equipment & Parts"),
    },
    "bn-launch": {
        "phrases": ("orbital launch vehicle", "reusable launch vehicle", "launch cadence"),
        "occupant_industries": ("Aerospace & Defense",),
    },
    "bn-enrichment": {
        "phrases": ("uranium enrichment", "uranium conversion services",
                    "high assay low enriched uranium"),
        "occupant_industries": ("Uranium",),
    },
    "bn-reimbursement": {
        "phrases": ("de novo clearance artificial intelligence",
                    "reimbursement for artificial intelligence software"),
        "occupant_industries": ("Medical - Devices", "Medical - Healthcare Information Services",
                                "Medical - Diagnostics & Research"),
    },
    "bn-refining": {
        "phrases": ("rare earth separation", "rare earth refining", "critical minerals processing"),
        "occupant_industries": ("Other Precious Metals", "Industrial Materials",
                                "Chemicals - Specialty"),
    },
}


class MandateEntry:
    """One chokepoint and the phrases directed at it -- the unit the composer sweeps.

    Carries the REAL graph objects it was resolved against, so a caller can never sweep a chokepoint
    that does not exist. There is no score / rank / rating field here and never will be: this says
    WHERE to look, never what is worth owning.
    """

    __slots__ = ("bottleneck_id", "bottleneck_name", "theme_id", "theme_name", "phrases",
                 "occupant_industries")

    def __init__(self, *, bottleneck_id: str, bottleneck_name: str, theme_id: str,
                 theme_name: str, phrases: Tuple[str, ...],
                 occupant_industries: Tuple[str, ...] = ()) -> None:
        self.bottleneck_id = bottleneck_id
        self.bottleneck_name = bottleneck_name
        self.theme_id = theme_id
        self.theme_name = theme_name
        self.phrases = phrases
        self.occupant_industries = occupant_industries

    def __repr__(self) -> str:   # pragma: no cover - debugging aid
        return "MandateEntry({0} @ {1}, {2} phrases)".format(
            self.bottleneck_id, self.theme_id, len(self.phrases))


def _looks_like_a_ticker(term: str) -> bool:
    """True for a bare symbol (``NVDA``, ``BRK.B``) -- the shape a mandate may never contain."""
    bare = str(term or "").strip().replace(".", "").replace("-", "")
    if not bare or " " in str(term or "").strip():
        return False        # a phrase, not a symbol
    return bare.isupper() and bare.isalpha() and 1 <= len(bare) <= 5


def validate_mandate(mandate: Optional[Dict[str, Tuple[str, ...]]] = None) -> None:
    """Refuse a mandate that names companies instead of directing the search (ADR-0011).

    Raises ``ValueError`` on a ticker-shaped term or an empty phrase set. This is the guard that
    keeps the file a mandate: the practice ADR-0011 ended was a hardcoded ticker list, and the
    easiest way to resurrect it would be to paste one in here.
    """
    src = CHOKEPOINT_MANDATE if mandate is None else mandate
    for bottleneck_id, spec in src.items():
        phrases = tuple(p for p in (spec.get("phrases") or ()) if str(p or "").strip())
        industries = tuple(i for i in (spec.get("occupant_industries") or ())
                           if str(i or "").strip())
        if not phrases:
            raise ValueError(
                "mandate for {0!r} has no phrase -- a chokepoint with no phrase directs nothing; "
                "remove the key or give it a real search term".format(bottleneck_id))
        if not industries:
            raise ValueError(
                "mandate for {0!r} names no occupant industry -- without it a MENTION would admit "
                "a company, and mentioning a chokepoint is not occupying one (ADR-0011: admission "
                "requires occupancy, established by evidence)".format(bottleneck_id))
        for term in phrases + industries:
            if _looks_like_a_ticker(term):
                raise ValueError(
                    "mandate for {0!r} contains {1!r}, which is a TICKER, not a direction -- a "
                    "mandate states an interest and leaves the engine to find who matters "
                    "(ADR-0011). Name the capacity, not the company.".format(bottleneck_id, term))


def mandate_for(bottleneck_id: str) -> Tuple[str, ...]:
    """The phrases directed at one chokepoint (``()`` if none is mandated -- an honest silence)."""
    spec = CHOKEPOINT_MANDATE.get(str(bottleneck_id or "").strip(), {})
    return tuple(spec.get("phrases") or ())


def occupants_for(bottleneck_id: str) -> Tuple[str, ...]:
    """The industries that SUPPLY this chokepoint's capacity -- the occupancy half of the test."""
    spec = CHOKEPOINT_MANDATE.get(str(bottleneck_id or "").strip(), {})
    return tuple(spec.get("occupant_industries") or ())


def chokepoint_mandates(graph: Optional[ThemeGraph] = None) -> Tuple[MandateEntry, ...]:
    """Every REAL chokepoint that carries a mandate, order-stable by the graph's own order.

    Resolves against the value-chain map, so only a chokepoint that genuinely exists can be swept: a
    mandate key with no matching chokepoint is silently absent rather than conjuring one (ADR-0011 --
    "a chokepoint SHALL NOT be invented to admit a company"). A real chokepoint with NO mandate is
    likewise absent: it is an honest gap in direction, not a licence to sweep it blindly.
    """
    validate_mandate()
    g = graph if graph is not None else build_seed_theme_graph()
    chain_to_theme = {v.value_chain_id: v.theme_ref for v in g.value_chains}
    theme_name = {t.theme_id: t.name for t in g.themes}
    out: List[MandateEntry] = []
    for bottleneck in g.bottlenecks:
        if not getattr(bottleneck, "is_chokepoint", False):
            continue        # a bottleneck that does not gate is not the bound ADR-0011 set
        phrases = mandate_for(bottleneck.bottleneck_id)
        if not phrases:
            continue
        theme_id = chain_to_theme.get(bottleneck.value_chain_ref, "")
        if not theme_id:
            continue        # unmapped chain -> no honest theme to file an entry under
        out.append(MandateEntry(
            bottleneck_id=bottleneck.bottleneck_id,
            bottleneck_name=bottleneck.name,
            theme_id=theme_id,
            theme_name=theme_name.get(theme_id, theme_id),
            phrases=phrases,
            occupant_industries=occupants_for(bottleneck.bottleneck_id)))
    return tuple(out)
