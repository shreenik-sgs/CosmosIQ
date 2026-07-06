"""Manual Position Ledger for the Reality Mesh (IMPLEMENTATION-UX-2).

A BOOKKEEPING journal of trades the operator ALREADY EXECUTED in THEIR OWN brokerage.
It records what HAPPENED -- factual fills the operator enters by hand -- so Portfolio
Intelligence (018) can read REAL holdings and the 017 / 022F learning loop can compare a
recommendation to what the operator actually did.

THIS IS NOT ORDER SUBMISSION AND NOT A BROKER CONNECTION. Read this three times:

* **Record-only.** This module NEVER connects to a broker, NEVER submits / places / routes /
  cancels an order, and has NO imperative buy/sell action anywhere. It only writes a local
  JSONL line. There is NO network import, NO subprocess, NO broker/order/submit/place/route
  function or token. An offline socket kill-switch proves :func:`record_fill` reaches nothing.
* **Past tense, never an instruction.** ``side`` is a CLOSED PAST-TENSE vocabulary --
  ``bought`` / ``sold`` (WHAT HAPPENED), never ``buy`` / ``sell`` (an instruction to act).
* **Quantity + price are the operator's recorded FACTS, not a CosmosIQ score.** This is the ONE
  place a numeric quantity + price legitimately live: they are the operator's own bookkeeping
  data, NOT a system-generated score / rank / rating / investability. So this model does NOT use
  :func:`~reality_mesh.validation.assert_no_trade_fields` (which bans quantity / shares / amount
  for the LABEL-ONLY intelligence outputs -- a different thing). Instead it carries a CUSTOM
  guard, :func:`assert_no_execution_fields`, that bans a
  ``broker`` / ``order`` / ``submit`` / ``place`` / ``route`` / ``auto_trade`` / ``buy`` / ``sell``
  FIELD NAME but ALLOWS ``quantity`` / ``price`` / ``side`` / ``trade_date`` as factual data. The
  module defines NO ``*score`` / ``*rank`` / ``*rating`` function -- quantity / price are recorded
  facts, never a metric CosmosIQ computed.
* **Append-only; correction-not-mutation.** A fill line, once written, is never edited or
  removed. There is NO update / delete API. A CORRECTION / reversal is a NEW fill record whose
  ``correction_of`` names the fill it supersedes -- the prior line stays byte-unchanged forever.
* **Deterministic.** ``fill_id`` is content-derived (a sha256 over the recorded facts, EXCLUDING
  the injected ``recorded_at`` so re-recording the same fill is idempotent + byte-identical).
  Every timestamp is an injected string -- no wall clock in any id / replay path.

Composes the 013B :class:`~reality_mesh.stores.AppendOnlyStore` (inheriting its deterministic
envelope, credential-key write refusal, and no update / delete affordance), FEEDS the 018
:mod:`~reality_mesh.portfolio` holdings shape, and HOOKS the 017 / 022F learning loop -- without
modifying any of them.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no daemon, no broker on
import; local files only.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional, Tuple

from .stores import (
    SCHEMA_VERSION as ENVELOPE_SCHEMA_VERSION,
    CREDENTIAL_KEY_TOKENS,
    AppendOnlyStore,
    _payload_dict,
    _scan_bad_key,
)

__all__ = [
    "SCHEMA_VERSION",
    "SIDE_BOUGHT",
    "SIDE_SOLD",
    "FILL_SIDES",
    "EXECUTION_FIELD_TOKENS",
    "PositionFill",
    "Holding",
    "LedgerOutcomeLink",
    "PositionLedgerStore",
    "LEDGER_MODELS",
    "assert_no_execution_fields",
    "fill_id_for",
    "record_fill",
    "compute_holdings",
    "holdings_for_portfolio_intelligence",
    "outcomes_for_learning",
]

# The ledger's own record schema version (independent of the 013B envelope version).
SCHEMA_VERSION = "UX2.1"

# The CLOSED, PAST-TENSE side vocabulary: what HAPPENED, never an instruction to act.
SIDE_BOUGHT = "bought"
SIDE_SOLD = "sold"
FILL_SIDES: Tuple[str, ...] = (SIDE_BOUGHT, SIDE_SOLD)

# FIELD-NAME tokens that would mark an EXECUTION / broker affordance. A ledger record field whose
# NAME contains any of these (case-insensitive) is refused -- a bookkeeping fill records what
# happened, it never carries a directive to act. NOTE: quantity / price / side / trade_date are
# DELIBERATELY absent from this set -- they are the operator's recorded FACTS, allowed here (this
# is why the ledger does NOT reuse assert_no_trade_fields, which bans quantity for label-only
# intelligence records).
EXECUTION_FIELD_TOKENS: Tuple[str, ...] = (
    "broker", "order", "submit", "place", "route", "auto_trade", "buy", "sell",
)


# --------------------------------------------------------------------------- #
# The custom execution-field guard (NOT assert_no_trade_fields)                 #
# --------------------------------------------------------------------------- #
def assert_no_execution_fields(cls: type) -> None:
    """Raise ``ValueError`` if ``cls`` declares any EXECUTION / broker field name.

    Bans a ``broker`` / ``order`` / ``submit`` / ``place`` / ``route`` / ``auto_trade`` /
    ``buy`` / ``sell`` field name, but ALLOWS ``quantity`` / ``price`` / ``side`` /
    ``trade_date`` -- those are the operator's recorded bookkeeping FACTS, not a directive to
    act and not a CosmosIQ score. This is the ledger's analogue of
    :func:`~reality_mesh.validation.assert_no_trade_fields`, tuned to permit the factual trade
    data that legitimately lives here while still forbidding an order-submission affordance.
    """
    for f in fields(cls):
        low = f.name.lower()
        for token in EXECUTION_FIELD_TOKENS:
            if token in low:
                raise ValueError(
                    "{0}.{1} carries an execution/broker field token {2!r} -- the position "
                    "ledger is a RECORD of executed trades, never an order-submission "
                    "affordance".format(cls.__name__, f.name, token))


def _is_number(value: Any) -> bool:
    """True for a real int/float (never a bool -- a bool is not a recorded quantity/price)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _canon_num(value: Any) -> str:
    """A canonical string for a recorded number (integral floats collapse to the int form).

    Keeps the content-derived id stable whether the operator recorded ``100`` or ``100.0``.
    """
    number = float(value)
    if number == int(number):
        return str(int(number))
    return repr(number)


# --------------------------------------------------------------------------- #
# The typed fill record                                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PositionFill:
    """One EXECUTED fill the operator recorded by hand -- bookkeeping, never an order.

    ``quantity`` and ``price`` are the operator's OWN recorded FACTS (a quantity of shares and a
    fill price they actually transacted at THEIR broker), NOT a CosmosIQ-generated score / rank /
    rating / investability. ``side`` is PAST TENSE -- ``bought`` / ``sold`` (what happened) --
    never an instruction. ``recommendation_ref`` optionally links the fill to a 022A / 022F
    recommendation so the learning loop can compare the recommendation to the operator's action.
    ``correction_of`` (optional) names the ``fill_id`` this record CORRECTS / reverses -- a
    correction is a NEW record, never a mutation of the prior line.
    """

    fill_id: str = ""                       # REQUIRED, content-derived (deterministic)
    ticker: str = ""                        # REQUIRED
    side: str = ""                          # closed PAST-TENSE vocabulary: FILL_SIDES
    quantity: Any = 0                       # operator-recorded FACT: number > 0 (int or float)
    price: Any = 0                          # operator-recorded FACT: fill price >= 0
    trade_date: str = ""                    # REQUIRED -- the date the trade happened (recorded)
    recommendation_ref: str = ""            # optional link to a 022A/022F recommendation
    note: str = ""                          # optional operator note
    recorded_at: str = ""                   # REQUIRED injected instant the fill was JOURNALED
    schema_version: str = SCHEMA_VERSION
    correction_of: str = ""                 # optional: the fill_id this corrects/reverses

    def __post_init__(self) -> None:
        assert_no_execution_fields(type(self))
        # -- required ids / text -- #
        for name in ("fill_id", "ticker", "trade_date", "recorded_at"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "PositionFill.{0} is required and must be non-empty".format(name))
        # -- side: closed PAST-TENSE vocabulary -- #
        if self.side not in FILL_SIDES:
            raise ValueError(
                "PositionFill.side {0!r} invalid -- must be one of {1} (PAST TENSE: what "
                "happened, never an instruction 'buy'/'sell'/'order')".format(
                    self.side, list(FILL_SIDES)))
        # -- quantity / price: the operator's recorded FACTS -- #
        if not _is_number(self.quantity) or self.quantity <= 0:
            raise ValueError(
                "PositionFill.quantity must be a recorded number > 0 (the operator's own "
                "share count); got {0!r}".format(self.quantity))
        if not _is_number(self.price) or self.price < 0:
            raise ValueError(
                "PositionFill.price must be a recorded number >= 0 (the operator's own fill "
                "price); got {0!r}".format(self.price))
        for name in ("recommendation_ref", "note", "correction_of", "schema_version"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(
                    "PositionFill.{0} must be a string".format(name))

    @property
    def signed_quantity(self) -> float:
        """+quantity when ``bought``, -quantity when ``sold`` (a transient fact, never stored)."""
        return float(self.quantity) if self.side == SIDE_BOUGHT else -float(self.quantity)

    @property
    def is_correction(self) -> bool:
        return bool(self.correction_of.strip())


@dataclass(frozen=True)
class Holding:
    """A net position aggregated from the recorded fills -- the operator's own bookkeeping.

    ``net_quantity`` is bought minus sold (honoring corrections); ``average_cost_basis`` is the
    weighted average of the RECORDED buy prices (``None`` when nothing was bought -- never
    fabricated); ``realized_proceeds`` sums recorded sell price x quantity. A position whose
    ``net_quantity`` is 0 is a CLOSED position (kept for history, not an active holding).
    """

    ticker: str = ""
    net_quantity: Any = 0
    average_cost_basis: Optional[float] = None   # None = nothing bought (never fabricated)
    realized_proceeds: float = 0.0
    total_fills: int = 0
    last_trade_date: str = ""
    linked_recommendation_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_execution_fields(type(self))
        if not self.ticker.strip():
            raise ValueError("Holding.ticker is required and must be non-empty")

    @property
    def is_closed(self) -> bool:
        """A net-zero position: fully exited, kept for history, not an active holding."""
        return float(self.net_quantity) == 0.0


@dataclass(frozen=True)
class LedgerOutcomeLink:
    """A fill's link to a recommendation for the 017/022F loop -- LABELS + REFS only.

    Carries the ``recommendation_ref`` + ``ticker`` + PAST-TENSE ``side`` + ``trade_date`` so the
    learning layer can compare the recommendation to the operator's ACTION. It DELIBERATELY omits
    quantity / price -- the learning layer stays label-only (no numeric return / score ever
    crosses into it).
    """

    recommendation_ref: str = ""
    ticker: str = ""
    side: str = ""
    trade_date: str = ""

    def __post_init__(self) -> None:
        assert_no_execution_fields(type(self))
        for name in ("recommendation_ref", "ticker", "trade_date"):
            if not getattr(self, name).strip():
                raise ValueError(
                    "LedgerOutcomeLink.{0} is required and must be non-empty".format(name))
        if self.side not in FILL_SIDES:
            raise ValueError(
                "LedgerOutcomeLink.side {0!r} invalid (closed vocabulary: {1})".format(
                    self.side, list(FILL_SIDES)))


# The frozen record set (for registry / test introspection).
LEDGER_MODELS = (PositionFill, Holding, LedgerOutcomeLink)


# --------------------------------------------------------------------------- #
# Deterministic content-derived id                                             #
# --------------------------------------------------------------------------- #
def fill_id_for(*, ticker: str, side: str, quantity: Any, price: Any, trade_date: str,
                recommendation_ref: str = "", note: str = "", correction_of: str = "") -> str:
    """A deterministic ``fill_id`` from the recorded facts (EXCLUDING the injected instant).

    Excluding ``recorded_at`` makes re-recording the exact same fill idempotent + byte-identical.
    """
    canonical = "|".join((
        str(ticker or "").strip().upper(),
        str(side or "").strip(),
        _canon_num(quantity) if _is_number(quantity) else str(quantity),
        _canon_num(price) if _is_number(price) else str(price),
        str(trade_date or "").strip(),
        str(recommendation_ref or "").strip(),
        str(note or "").strip(),
        str(correction_of or "").strip(),
    ))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return "fill:{0}".format(digest)


# --------------------------------------------------------------------------- #
# The append-only ledger store                                                 #
# --------------------------------------------------------------------------- #
class PositionLedgerStore(AppendOnlyStore):
    """Append-only manual position ledger (``position_ledger.jsonl``).

    Composes the 013B base -- inheriting the deterministic envelope, the read/query surface, and
    the NO update / delete affordance. It KEEPS the base's credential-key write refusal, and adds
    the CUSTOM execution-field refusal (no broker/order/submit/place/route/auto_trade/buy/sell
    KEY). It deliberately does NOT apply the base's label-only trade/score KEY ban, because
    ``quantity`` / ``price`` / ``trade_date`` are the operator's recorded FACTS that legitimately
    live in THIS store (and only this store). It NEVER makes a network / broker call -- it only
    writes a local JSONL line.
    """

    filename = "position_ledger.jsonl"
    record_cls = PositionFill
    id_field = "fill_id"
    timestamp_field = "recorded_at"
    ticker_fields = ("ticker",)

    def append(self, item: Any, *, run_id: str = "", timestamp: str = "",
               record_id: str = "") -> str:
        """Append ONE fill and return its ``fill_id``. Append-only -- never mutates a prior line.

        Wraps the payload in the same 013B replay envelope, KEEPS the credential-key refusal, and
        applies the CUSTOM execution-field refusal -- while ALLOWING the factual quantity / price /
        trade_date keys the base's label-only ban would otherwise reject.
        """
        payload = _payload_dict(item)
        rid = record_id or str(getattr(item, self.id_field, "")) \
            or str(payload.get(self.id_field, ""))
        if not str(rid).strip():
            raise ValueError(
                "PositionLedgerStore.append: could not resolve a stable fill_id")
        resolved_ts = timestamp or str(payload.get(self.timestamp_field, ""))
        record = {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "record_id": rid,
            "run_id": run_id,
            "timestamp": resolved_ts,
            "record_type": self.record_type,
            "payload": payload,
        }
        bad_secret = _scan_bad_key(record, CREDENTIAL_KEY_TOKENS)
        if bad_secret is not None:
            raise ValueError(
                "refusing to persist a credential-like key {0!r} -- the ledger never writes a "
                "secret".format(bad_secret))
        bad_exec = _scan_bad_key(record, EXECUTION_FIELD_TOKENS)
        if bad_exec is not None:
            raise ValueError(
                "refusing to persist an execution/broker key {0!r} -- the ledger RECORDS "
                "executed trades, it never carries an order-submission affordance".format(
                    bad_exec))
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return str(rid)


# --------------------------------------------------------------------------- #
# Recording a fill (append-only; correction-not-mutation; idempotent)          #
# --------------------------------------------------------------------------- #
def record_fill(store_dir: str, *, ticker: str, side: str, quantity: Any, price: Any,
                trade_date: str, recommendation_ref: str = "", note: str = "", now: str,
                correction_of: str = "") -> PositionFill:
    """Validate + persist ONE executed fill, append-only. Return the :class:`PositionFill`.

    This is BOOKKEEPING -- it records a trade the operator ALREADY executed at their own broker.
    It NEVER submits / places / routes an order and NEVER touches a broker or the network; it
    writes exactly one local JSONL line. The ``fill_id`` is content-derived, so re-recording the
    identical fill appends NOTHING (the store stays byte-identical -- idempotent). A CORRECTION /
    reversal is recorded as a NEW fill with ``correction_of`` set to the ``fill_id`` it supersedes;
    the prior line is never mutated.
    """
    if not str(now).strip():
        raise ValueError("record_fill requires an injected 'now' instant")
    symbol = str(ticker or "").strip().upper()
    fid = fill_id_for(
        ticker=symbol, side=side, quantity=quantity, price=price, trade_date=trade_date,
        recommendation_ref=recommendation_ref, note=note, correction_of=correction_of)
    entry = PositionFill(
        fill_id=fid,
        ticker=symbol,
        side=side,
        quantity=quantity,
        price=price,
        trade_date=str(trade_date),
        recommendation_ref=str(recommendation_ref or ""),
        note=str(note or ""),
        recorded_at=str(now),
        schema_version=SCHEMA_VERSION,
        correction_of=str(correction_of or ""))

    store = PositionLedgerStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    if entry.fill_id in existing:
        # already recorded: return the persisted fill, append nothing (byte-identical).
        for prior in store.read_all():
            if prior.fill_id == entry.fill_id:
                return prior
        return entry
    store.append(entry, timestamp=entry.recorded_at)
    return entry


# --------------------------------------------------------------------------- #
# Aggregation into net holdings                                                 #
# --------------------------------------------------------------------------- #
def _all_fills(store_dir: str) -> Tuple[PositionFill, ...]:
    return PositionLedgerStore(store_dir).read_all()


def _effective_fills(store_dir: str) -> Tuple[PositionFill, ...]:
    """The fills that COUNT: a fill named by a later ``correction_of`` is voided (superseded).

    Correction-not-mutation on the READ side: the superseded line stays byte-unchanged on disk,
    but it drops out of the net; the correcting fill takes effect with its own recorded facts.
    """
    fills = _all_fills(store_dir)
    voided = {f.correction_of for f in fills if f.correction_of.strip()}
    return tuple(f for f in fills if f.fill_id not in voided)


def compute_holdings(store_dir: str) -> Tuple[Holding, ...]:
    """Aggregate every recorded fill into net positions (sorted by ticker).

    Per ticker: ``net_quantity`` = bought minus sold (honoring corrections); ``average_cost_basis``
    = the weighted average of the RECORDED buy prices (``None`` when nothing was bought -- a price
    is NEVER fabricated); ``realized_proceeds`` = sum of recorded sell price x quantity. A ticker
    whose net quantity is 0 is a CLOSED position -- kept for history, not an active holding.
    """
    fills = _effective_fills(store_dir)
    by_ticker: Dict[str, List[PositionFill]] = {}
    for fill in fills:
        by_ticker.setdefault(fill.ticker, []).append(fill)

    holdings: List[Holding] = []
    for ticker in sorted(by_ticker):
        group = by_ticker[ticker]
        net = 0.0
        buy_qty = 0.0
        buy_cost = 0.0
        realized = 0.0
        refs: List[str] = []
        last_date = ""
        for fill in group:
            net += fill.signed_quantity
            if fill.side == SIDE_BOUGHT:
                buy_qty += float(fill.quantity)
                buy_cost += float(fill.quantity) * float(fill.price)
            else:
                realized += float(fill.quantity) * float(fill.price)
            if fill.recommendation_ref.strip():
                refs.append(fill.recommendation_ref.strip())
            if fill.trade_date > last_date:
                last_date = fill.trade_date
        avg_cost = (buy_cost / buy_qty) if buy_qty > 0 else None
        holdings.append(Holding(
            ticker=ticker,
            net_quantity=_as_int_if_whole(net),
            average_cost_basis=avg_cost,
            realized_proceeds=realized,
            total_fills=len(group),
            last_trade_date=last_date,
            linked_recommendation_refs=tuple(sorted(set(refs))),
        ))
    return tuple(holdings)


def _as_int_if_whole(value: float):
    """Collapse a whole float to an int so a share count reads ``150``, not ``150.0``."""
    return int(value) if float(value) == int(value) else value


# --------------------------------------------------------------------------- #
# Bridge into 018 Portfolio Intelligence (the holdings statement shape)         #
# --------------------------------------------------------------------------- #
def holdings_for_portfolio_intelligence(store_dir: str) -> Dict[str, Any]:
    """Map the ACTIVE ledger holdings into the 018 holdings-statement shape.

    Returns a dict in exactly the shape :func:`reality_mesh.portfolio.load_holdings` /
    ``build_concentration`` / ``build_exposure`` already consume (``as_of`` + ``positions`` of
    ``{ticker, quantity, cost_basis}``), so Portfolio Intelligence can read REAL ledger holdings
    instead of the static ``PORTFOLIO_RECORDS`` sample -- WITHOUT changing 018's interface. Only
    active positions (net quantity > 0) are included; closed (net-zero) positions are history.
    ``as_of`` is the latest recorded ``trade_date`` across the active holdings (a recorded fact,
    never a wall clock); the caller persists this dict to ``<store>/portfolio/holdings.json`` to
    feed 018.
    """
    positions: List[Dict[str, Any]] = []
    as_of = ""
    for holding in compute_holdings(store_dir):
        if holding.is_closed or float(holding.net_quantity) <= 0:
            continue
        position: Dict[str, Any] = {
            "ticker": holding.ticker,
            "quantity": holding.net_quantity,
        }
        if holding.average_cost_basis is not None:
            position["cost_basis"] = holding.average_cost_basis
        positions.append(position)
        if holding.last_trade_date > as_of:
            as_of = holding.last_trade_date
    return {"as_of": as_of, "positions": positions}


# --------------------------------------------------------------------------- #
# The 017 / 022F learning-loop hook (labels + refs only)                        #
# --------------------------------------------------------------------------- #
def outcomes_for_learning(store_dir: str) -> Tuple[LedgerOutcomeLink, ...]:
    """Expose each recommendation-linked fill as a LABEL + REF row for the learning loop.

    For every effective fill carrying a ``recommendation_ref``, surface
    ``(recommendation_ref, ticker, side, trade_date)`` so the 017 / 022F loop can compare the
    recommendation to the operator's ACTUAL action + later observations. Labels + refs ONLY -- no
    numeric quantity / price / return / score crosses into the learning layer (it stays
    label-only). Order-stable.
    """
    links: List[LedgerOutcomeLink] = []
    for fill in _effective_fills(store_dir):
        if fill.recommendation_ref.strip():
            links.append(LedgerOutcomeLink(
                recommendation_ref=fill.recommendation_ref.strip(),
                ticker=fill.ticker,
                side=fill.side,
                trade_date=fill.trade_date))
    return tuple(sorted(
        links, key=lambda l: (l.recommendation_ref, l.ticker, l.trade_date, l.side)))


# --------------------------------------------------------------------------- #
# Construction-time guard: the models carry NO execution / broker field.        #
# --------------------------------------------------------------------------- #
for _model in LEDGER_MODELS:
    assert_no_execution_fields(_model)
