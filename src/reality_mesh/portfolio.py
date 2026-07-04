"""Portfolio intelligence for the Reality Mesh -- READ-ONLY (IMPLEMENTATION-018A).

Pure, deterministic views over ONE operator-recorded holdings file plus the
persisted 013B stores. The operator RECORDS what they hold as a plain local
JSON file (``<store>/portfolio/holdings.json``); this module READS that
statement and the persisted signals / theme pulses and answers "what am I
exposed to, how concentrated is it, and is rotation with or against me" --
in LABELS and VOLUME COUNTS only. It never acts:

* **Read-only.** NO external account connection, NO import from any account
  provider, NO market action, NO automatic re-weighting of anything. The
  holdings file is the operator's own statement, read and never modified.
* **Bands and labels, never stored ratios.** A position's weight is computed
  TRANSIENTLY from the recorded ``cost_basis * quantity`` against the recorded
  total, then immediately collapsed to a closed BAND label
  (``minimal`` / ``moderate`` / ``elevated`` / ``dominant``). No ratio,
  weight, percentage, or numeric metric is ever stored on a record --
  every record field is a string, a bool, an int volume count, or a tuple
  of strings, and every record is :func:`assert_no_trade_fields`-clean.
* **Correlation is a membership label.** Two holdings are ``co_exposed`` /
  ``partially_co_exposed`` / ``distinct`` by SHARED persisted-theme
  membership -- no numeric correlation exists anywhere.
* **Honest absence.** Missing holdings file -> ``(None, reason)``; malformed
  file -> a NAMED parse/shape error; a position with no recorded cost basis
  -> band ``unknown`` plus an explicit gap; a ticker no persisted record maps
  to a theme -> said, never guessed; holdings older than the latest persisted
  run -> a ``stale`` freshness label.
* **Thresholds as data.** Every band edge lives in
  :data:`PORTFOLIO_THRESHOLDS`; every state->alignment decision lives in
  :data:`STATE_ALIGNMENT`. Nothing is buried in code.

Deterministic, stdlib-only, Python 3.9. No network, no wall clock, no
scheduler; local files only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .stores import RunStore, SignalStore, ThemePulseStore
from .validation import assert_no_trade_fields

__all__ = [
    "PORTFOLIO_DIRNAME",
    "HOLDINGS_FILENAME",
    "HOLDINGS_RELPATH",
    "CONCENTRATION_BANDS",
    "BAND_UNKNOWN",
    "HOLDINGS_FRESHNESS_LABELS",
    "CORRELATION_LABELS",
    "ROTATION_ALIGNMENT_LABELS",
    "CANDIDATE_COMPARISON_LABELS",
    "PORTFOLIO_THRESHOLDS",
    "STATE_ALIGNMENT",
    "PORTFOLIO_RECORDS",
    "HoldingRecord",
    "PortfolioHoldings",
    "ExposureView",
    "ConcentrationView",
    "PairCorrelationView",
    "RotationAlignmentView",
    "CandidateComparison",
    "load_holdings",
    "ticker_theme_map",
    "band_for_position_weight",
    "band_for_theme_weight",
    "build_exposure",
    "build_concentration",
    "build_correlation_labels",
    "build_rotation_alignment",
    "compare_candidate",
]

# --------------------------------------------------------------------------- #
# File locations + closed vocabularies + thresholds-as-data                    #
# --------------------------------------------------------------------------- #

# The operator's recorded holdings statement, under the pulse store.
PORTFOLIO_DIRNAME = "portfolio"
HOLDINGS_FILENAME = "holdings.json"
HOLDINGS_RELPATH = PORTFOLIO_DIRNAME + "/" + HOLDINGS_FILENAME

# The concentration band ladder (weakest to strongest). ``unknown`` is the
# honest band when a position carries no recorded cost basis to weigh.
CONCENTRATION_BANDS: Tuple[str, ...] = ("minimal", "moderate", "elevated", "dominant")
BAND_UNKNOWN = "unknown"

# Holdings freshness relative to the LATEST persisted pulse run (pure string
# comparison of injected ISO instants -- never a wall clock).
HOLDINGS_FRESHNESS_LABELS: FrozenSet[str] = frozenset(
    {"current", "stale", "no_run_to_compare"})

# Shared-theme-membership correlation labels. NO numeric correlation exists.
CORRELATION_LABELS: FrozenSet[str] = frozenset(
    {"co_exposed", "partially_co_exposed", "distinct", "unknown"})

# Rotation alignment of one holding against one persisted theme-pulse state.
ROTATION_ALIGNMENT_LABELS: FrozenSet[str] = frozenset(
    {"aligned", "against", "no_signal"})

# Candidate-vs-holdings comparison labels. ``no_theme_signal`` is the honest
# no-persisted-mapping state, never a guess.
CANDIDATE_COMPARISON_LABELS: FrozenSet[str] = frozenset(
    {"new_theme", "adds_concentration", "diversifies", "no_theme_signal"})

# Band edges as DATA (percent of the recorded total). A weight AT an edge
# enters the higher band. Position bands use the ``position_*`` edges;
# combined per-theme exposure uses the wider ``theme_*`` edges.
PORTFOLIO_THRESHOLDS: Mapping[str, float] = {
    "position_weight_moderate_pct": 5.0,
    "position_weight_elevated_pct": 10.0,
    "position_weight_dominant_pct": 20.0,
    "theme_exposure_moderate_pct": 10.0,
    "theme_exposure_elevated_pct": 25.0,
    "theme_exposure_dominant_pct": 40.0,
}

# Persisted theme-pulse state -> rotation alignment FOR A HOLDING, as data.
# The rising arc is with the holder; the risk states (the 017A
# ``RISK_CLAIM_STATES`` set) are against; ambiguous states are honestly
# ``no_signal``.
STATE_ALIGNMENT: Mapping[str, str] = {
    "Warming": "aligned",
    "Igniting": "aligned",
    "Broadening": "aligned",
    "Crowded": "against",
    "Exhausting": "against",
    "Breaking down": "against",
    "Dormant": "no_signal",
    "Conflicted": "no_signal",
    "Data insufficient": "no_signal",
}


# --------------------------------------------------------------------------- #
# Record validation (strings / bools / int volumes / tuples -- never a metric) #
# --------------------------------------------------------------------------- #
def _forbid_metric_fields(obj) -> None:
    """No float anywhere on a portfolio record: a ratio / weight is NEVER stored."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, float):
            raise ValueError(
                "{0}.{1} is a float -- a portfolio record stores labels, "
                "counts and recorded text only, never a ratio or weight".format(
                    type(obj).__name__, f.name))
        if isinstance(value, tuple):
            for element in value:
                if isinstance(element, float):
                    raise ValueError(
                        "{0}.{1} contains a float -- a portfolio record never "
                        "stores a numeric metric".format(type(obj).__name__, f.name))


def _require_label(obj, name: str, vocab, *, allow_empty: bool = False) -> None:
    value = getattr(obj, name, "")
    if allow_empty and value == "":
        return
    if value not in vocab:
        raise ValueError(
            "{0}.{1}: invalid label {2!r} (closed vocabulary: {3})".format(
                type(obj).__name__, name, value, sorted(vocab)))


# --------------------------------------------------------------------------- #
# The frozen record set                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HoldingRecord:
    """One recorded position, verbatim: the operator's statement, never a valuation.

    ``quantity_text`` / ``cost_basis_text`` carry the recorded values AS TEXT for
    display only -- weighing happens transiently in the builders and only a BAND
    label survives. ``liquidity_note`` is the operator's own note ("" = none
    recorded -> rendered as an honest ``unknown``).
    """

    ticker: str = ""
    quantity_text: str = ""
    cost_basis_text: str = ""            # "" when no cost basis was recorded
    account_label: str = ""              # "" when not recorded
    liquidity_note: str = ""             # "" when not recorded (-> unknown)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        if not self.ticker.strip():
            raise ValueError("HoldingRecord.ticker is required and must be non-empty")
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class PortfolioHoldings:
    """The loaded holdings statement: positions + as_of + a freshness label.

    ``freshness_label`` compares the recorded ``as_of`` to the LATEST persisted
    pulse run's start instant (string comparison of injected ISO instants):
    holdings older than the latest run are honestly ``stale``.
    """

    as_of: str = ""
    freshness_label: str = ""            # closed: HOLDINGS_FRESHNESS_LABELS
    positions: Tuple[HoldingRecord, ...] = field(default_factory=tuple)
    position_count: int = 0
    cash_recorded: bool = False
    cash_text: str = ""                  # verbatim recorded cash ("" when absent)
    source_path: str = HOLDINGS_RELPATH
    basis: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "freshness_label", HOLDINGS_FRESHNESS_LABELS)
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class ExposureView:
    """One persisted theme -> the recorded positions mapped to it + a band.

    ``exposure_band`` is the COMBINED transient weight of the mapped positions
    collapsed to a band by the ``theme_*`` thresholds; ``unknown`` (with gaps)
    when any mapped position cannot be weighed.
    """

    theme_id: str = ""
    position_tickers: Tuple[str, ...] = field(default_factory=tuple)
    position_count: int = 0
    exposure_band: str = ""              # closed: CONCENTRATION_BANDS + unknown
    basis: str = ""
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "exposure_band",
                       frozenset(CONCENTRATION_BANDS) | {BAND_UNKNOWN})
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class ConcentrationView:
    """One position's weight BAND (never the ratio itself).

    The weight is computed transiently from ``cost_basis * quantity`` against
    the recorded total and immediately collapsed to the band; no numeric field
    exists on this record.
    """

    ticker: str = ""
    weight_band: str = ""                # closed: CONCENTRATION_BANDS + unknown
    basis: str = ""
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "weight_band",
                       frozenset(CONCENTRATION_BANDS) | {BAND_UNKNOWN})
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class PairCorrelationView:
    """Two holdings' shared-theme-membership label. NO numeric correlation."""

    ticker_a: str = ""
    ticker_b: str = ""
    correlation_label: str = ""          # closed: CORRELATION_LABELS
    shared_themes: Tuple[str, ...] = field(default_factory=tuple)
    basis: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "correlation_label", CORRELATION_LABELS)
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class RotationAlignmentView:
    """One (holding, theme) row against the LATEST persisted theme-pulse state."""

    ticker: str = ""
    theme_id: str = ""                   # "" when no persisted record maps the ticker
    theme_state: str = ""                # the persisted state ("" when none persisted)
    alignment_label: str = ""            # closed: ROTATION_ALIGNMENT_LABELS
    run_id: str = ""                     # the run that persisted the state ("" when none)
    basis: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "alignment_label", ROTATION_ALIGNMENT_LABELS)
        _forbid_metric_fields(self)


@dataclass(frozen=True)
class CandidateComparison:
    """One candidate vs the current recorded exposure -- a label, never advice."""

    candidate_ticker: str = ""
    comparison_label: str = ""           # closed: CANDIDATE_COMPARISON_LABELS
    candidate_themes: Tuple[str, ...] = field(default_factory=tuple)
    overlapping_themes: Tuple[str, ...] = field(default_factory=tuple)
    new_themes: Tuple[str, ...] = field(default_factory=tuple)
    already_recorded: bool = False       # the candidate is already a recorded position
    basis: str = ""
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_label(self, "comparison_label", CANDIDATE_COMPARISON_LABELS)
        _forbid_metric_fields(self)


# The frozen record set (for test introspection).
PORTFOLIO_RECORDS = (
    HoldingRecord,
    PortfolioHoldings,
    ExposureView,
    ConcentrationView,
    PairCorrelationView,
    RotationAlignmentView,
    CandidateComparison,
)


# --------------------------------------------------------------------------- #
# Loading the operator's holdings statement                                    #
# --------------------------------------------------------------------------- #
def _holdings_path(store_dir: str) -> str:
    return os.path.join(str(store_dir), PORTFOLIO_DIRNAME, HOLDINGS_FILENAME)


def _latest_run_instant(store_dir: str) -> str:
    """The latest ``started_at`` across every persisted run ("" when none)."""
    latest = ""
    for run in RunStore(store_dir).read_all():
        started = str(getattr(run, "started_at", "") or "")
        if started > latest:
            latest = started
    return latest


def _as_text(value: Any) -> str:
    """A recorded scalar rendered verbatim-ish (ints without a trailing .0)."""
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def load_holdings(store_dir: str) -> Tuple[Optional[PortfolioHoldings], str]:
    """Load the operator's recorded holdings statement, honestly.

    Returns ``(PortfolioHoldings, "")`` on success. Missing file ->
    ``(None, reason)``; malformed JSON or a bad shape -> ``(None, named error)``.
    Nothing is guessed and nothing is fabricated to fill the gap. Staleness is
    a LABEL computed against the latest persisted run instant (string
    comparison of recorded ISO instants -- no wall clock exists here).
    """
    path = _holdings_path(store_dir)
    if not os.path.isfile(path):
        return None, ("no holdings recorded -- expected at <store>/{0}; every "
                      "portfolio surface stays honestly empty until the operator "
                      "records one".format(HOLDINGS_RELPATH))
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except ValueError as exc:
        return None, ("the holdings file could not be parsed ({0}) -- nothing is "
                      "guessed".format(exc))
    if not isinstance(raw, dict):
        return None, "the holdings file must be a JSON object; got {0}".format(
            type(raw).__name__)
    as_of = str(raw.get("as_of", "") or "").strip()
    if not as_of:
        return None, ("the holdings file carries no 'as_of' instant -- an undated "
                      "statement cannot be labeled fresh or stale, so it is refused")
    entries = raw.get("positions")
    if not isinstance(entries, list):
        return None, "the holdings file must carry 'positions' as a JSON list"
    positions: List[HoldingRecord] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return None, "positions[{0}] is not a JSON object".format(index)
        ticker = str(entry.get("ticker", "") or "").strip().upper()
        if not ticker:
            return None, "positions[{0}] carries no 'ticker'".format(index)
        if entry.get("quantity") is None:
            return None, "positions[{0}] ({1}) carries no 'quantity'".format(
                index, ticker)
        positions.append(HoldingRecord(
            ticker=ticker,
            quantity_text=_as_text(entry.get("quantity")),
            cost_basis_text=_as_text(entry.get("cost_basis")),
            account_label=str(entry.get("account_label", "") or ""),
            liquidity_note=str(entry.get("liquidity_note", "") or ""),
        ))
    latest = _latest_run_instant(store_dir)
    if not latest:
        freshness = "no_run_to_compare"
        basis = ("no pulse run is persisted yet, so freshness cannot be compared "
                 "-- an honest unknown, not a claim")
    elif as_of >= latest:
        freshness = "current"
        basis = ("recorded as_of {0} is not older than the latest persisted run "
                 "instant {1}".format(as_of, latest))
    else:
        freshness = "stale"
        basis = ("recorded as_of {0} predates the latest persisted run instant {1} "
                 "-- the statement is STALE relative to the persisted evidence; "
                 "re-record it to refresh".format(as_of, latest))
    cash = raw.get("cash")
    return PortfolioHoldings(
        as_of=as_of,
        freshness_label=freshness,
        positions=tuple(positions),
        position_count=len(positions),
        cash_recorded=cash is not None,
        cash_text=_as_text(cash),
        source_path=HOLDINGS_RELPATH,
        basis=basis,
    ), ""


# --------------------------------------------------------------------------- #
# Transient weighing (numbers live ONLY inside this section, never on records)  #
# --------------------------------------------------------------------------- #
def _raw_positions(store_dir: str) -> List[Dict[str, Any]]:
    """The raw recorded position dicts ([] when the file is absent/unloadable)."""
    path = _holdings_path(store_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except ValueError:
        return []
    if not isinstance(raw, dict) or not isinstance(raw.get("positions"), list):
        return []
    return [e for e in raw["positions"] if isinstance(e, dict)]


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _transient_weights(store_dir: str):
    """(ticker -> transient weight pct | None, gaps). NOTHING here is stored.

    A position's transient value is ``cost_basis * quantity``; the total is the
    sum of every weighable position plus recorded cash. A position missing a
    numeric cost basis or quantity weighs ``None`` (band ``unknown``) with an
    explicit gap.
    """
    entries = _raw_positions(store_dir)
    values: Dict[str, Optional[float]] = {}
    gaps: List[str] = []
    total = 0.0
    path = _holdings_path(store_dir)
    cash = None
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            cash = _number(raw.get("cash")) if isinstance(raw, dict) else None
        except ValueError:
            cash = None
    for entry in entries:
        ticker = str(entry.get("ticker", "") or "").strip().upper()
        if not ticker:
            continue
        quantity = _number(entry.get("quantity"))
        cost_basis = _number(entry.get("cost_basis"))
        if quantity is None or cost_basis is None:
            values[ticker] = None
            gaps.append("position {0} carries no numeric cost basis and quantity "
                        "pair -- its weight band is honestly unknown".format(ticker))
            continue
        value = quantity * cost_basis
        values[ticker] = value
        total += value
    if cash is not None:
        total += cash
    if total <= 0:
        weights: Dict[str, Optional[float]] = {t: None for t in values}
        if values:
            gaps.append("the recorded total is not positive -- no weight band "
                        "can be computed")
        return weights, gaps
    weights = {
        ticker: (None if value is None else value / total * 100.0)
        for ticker, value in values.items()
    }
    return weights, gaps


def band_for_position_weight(weight_pct: float) -> str:
    """Collapse ONE transient position weight percent to its band (data-driven).

    A weight AT a threshold enters the higher band. The input is transient; only
    the returned label may be stored or rendered.
    """
    t = PORTFOLIO_THRESHOLDS
    if weight_pct >= t["position_weight_dominant_pct"]:
        return "dominant"
    if weight_pct >= t["position_weight_elevated_pct"]:
        return "elevated"
    if weight_pct >= t["position_weight_moderate_pct"]:
        return "moderate"
    return "minimal"


def band_for_theme_weight(weight_pct: float) -> str:
    """Collapse ONE transient combined theme weight percent to its band."""
    t = PORTFOLIO_THRESHOLDS
    if weight_pct >= t["theme_exposure_dominant_pct"]:
        return "dominant"
    if weight_pct >= t["theme_exposure_elevated_pct"]:
        return "elevated"
    if weight_pct >= t["theme_exposure_moderate_pct"]:
        return "moderate"
    return "minimal"


# --------------------------------------------------------------------------- #
# The persisted ticker -> theme mapping (signals + theme pulses, never guessed) #
# --------------------------------------------------------------------------- #
def _norm_theme(text: Any) -> str:
    """Case / hyphen / underscore-insensitive theme key (mirrors the 013B stores)."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def ticker_theme_map(store_dir: str) -> Dict[str, Tuple[str, ...]]:
    """ticker -> the persisted theme ids that name it, from the 013B stores ONLY.

    A ticker maps to a theme when a persisted signal names both
    (``affected_companies`` x ``affected_themes``) or a persisted theme pulse
    lists it as a beneficiary / risk candidate. First-seen display form wins per
    normalized theme; nothing is inferred beyond the persisted records.
    """
    display: Dict[str, str] = {}
    mapping: Dict[str, Dict[str, bool]] = {}

    def _add(ticker: Any, theme: Any) -> None:
        symbol = str(ticker or "").strip().upper()
        key = _norm_theme(theme)
        if not symbol or not key:
            return
        if key not in display:
            display[key] = str(theme)
        mapping.setdefault(symbol, {})[key] = True

    for signal in SignalStore(store_dir).read_all():
        for ticker in tuple(getattr(signal, "affected_companies", ()) or ()):
            for theme in tuple(getattr(signal, "affected_themes", ()) or ()):
                _add(ticker, theme)
    for pulse in ThemePulseStore(store_dir).read_all():
        theme = getattr(pulse, "theme_id", "") or getattr(pulse, "theme_name", "")
        for ticker in tuple(getattr(pulse, "beneficiary_candidates", ()) or ()):
            _add(ticker, theme)
        for ticker in tuple(getattr(pulse, "risk_candidates", ()) or ()):
            _add(ticker, theme)
    return {
        symbol: tuple(sorted(display[key] for key in keys))
        for symbol, keys in mapping.items()
    }


def _latest_pulse_states(store_dir: str) -> Dict[str, Tuple[str, str, str]]:
    """normalized theme -> (display theme_id, latest persisted state, run_id)."""
    latest: Dict[str, Tuple[str, str, str]] = {}
    store = ThemePulseStore(store_dir)
    envelopes = store.read_records()
    typed = store.read_all()
    for envelope, pulse in zip(envelopes, typed):
        key = _norm_theme(getattr(pulse, "theme_id", ""))
        if not key:
            continue
        latest[key] = (str(pulse.theme_id), str(pulse.state),
                       str(envelope.get("run_id", "") or ""))
    return latest


def _held_tickers(store_dir: str) -> Tuple[str, ...]:
    loaded, _reason = load_holdings(store_dir)
    if loaded is None:
        return ()
    return tuple(p.ticker for p in loaded.positions)


# --------------------------------------------------------------------------- #
# Builders (each pure: the holdings file + the stores in, frozen labels out)    #
# --------------------------------------------------------------------------- #
def build_exposure(store_dir: str) -> Tuple[ExposureView, ...]:
    """Exposure by persisted theme: which recorded positions map to each theme.

    Empty when no holdings are recorded (the caller states the absence).
    Themes appear in sorted display order; a theme's band is the COMBINED
    transient weight of its mapped positions (``unknown`` + gaps when any of
    them cannot be weighed).
    """
    tickers = _held_tickers(store_dir)
    if not tickers:
        return ()
    mapping = ticker_theme_map(store_dir)
    weights, weight_gaps = _transient_weights(store_dir)
    by_theme: Dict[str, List[str]] = {}
    for ticker in tickers:
        for theme in mapping.get(ticker, ()):
            by_theme.setdefault(theme, []).append(ticker)
    views = []
    for theme in sorted(by_theme):
        members = sorted(set(by_theme[theme]))
        gaps = [g for g in weight_gaps
                if any(g.startswith("position {0} ".format(t)) for t in members)]
        member_weights = [weights.get(t) for t in members]
        if any(w is None for w in member_weights) or not member_weights:
            band = BAND_UNKNOWN
            if not gaps:
                gaps.append("a mapped position cannot be weighed -- the combined "
                            "exposure band is honestly unknown")
        else:
            band = band_for_theme_weight(sum(member_weights))
        views.append(ExposureView(
            theme_id=theme,
            position_tickers=tuple(members),
            position_count=len(members),
            exposure_band=band,
            basis=("persisted signals / theme pulses name {0} together with this "
                   "theme; the combined recorded weight collapses to the band by "
                   "the published theme thresholds -- the band is the only value "
                   "kept".format(", ".join(members))),
            data_gaps=tuple(gaps),
        ))
    return tuple(views)


def build_concentration(store_dir: str) -> Tuple[ConcentrationView, ...]:
    """One weight BAND per recorded position; the ratio itself is never kept.

    Empty when no holdings are recorded. A position with no numeric
    ``cost_basis`` / ``quantity`` (or a non-positive recorded total) is
    honestly ``unknown`` with an explicit gap.
    """
    tickers = _held_tickers(store_dir)
    if not tickers:
        return ()
    weights, weight_gaps = _transient_weights(store_dir)
    views = []
    for ticker in tickers:
        weight = weights.get(ticker)
        gaps = tuple(g for g in weight_gaps
                     if g.startswith("position {0} ".format(ticker))
                     or g.startswith("the recorded total"))
        if weight is None:
            band = BAND_UNKNOWN
            basis = ("no transient weight could be computed for this position; "
                     "the band is honestly unknown, never estimated")
        else:
            band = band_for_position_weight(weight)
            basis = ("recorded cost basis times quantity, measured transiently "
                     "against the recorded total and collapsed to the band by the "
                     "published position thresholds; the band is the only value "
                     "kept -- no ratio is stored or rendered")
        views.append(ConcentrationView(
            ticker=ticker, weight_band=band, basis=basis, data_gaps=gaps))
    return tuple(views)


def build_correlation_labels(store_dir: str) -> Tuple[PairCorrelationView, ...]:
    """Shared-theme-membership labels for every pair of recorded positions.

    ``co_exposed`` -- identical persisted theme sets; ``partially_co_exposed``
    -- some shared themes; ``distinct`` -- none shared; ``unknown`` -- at least
    one side has NO persisted theme mapping (honest, never guessed). No numeric
    correlation is computed anywhere.
    """
    tickers = sorted(set(_held_tickers(store_dir)))
    if len(tickers) < 2:
        return ()
    mapping = ticker_theme_map(store_dir)
    views = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            themes_a = frozenset(_norm_theme(t) for t in mapping.get(a, ()))
            themes_b = frozenset(_norm_theme(t) for t in mapping.get(b, ()))
            display = {
                _norm_theme(t): t
                for t in tuple(mapping.get(a, ())) + tuple(mapping.get(b, ()))}
            shared = themes_a & themes_b
            if not themes_a or not themes_b:
                label = "unknown"
                basis = ("at least one side has no persisted theme mapping -- the "
                         "relationship is honestly unknown, never guessed")
            elif not shared:
                label = "distinct"
                basis = "no persisted theme names both positions"
            elif themes_a == themes_b:
                label = "co_exposed"
                basis = ("the persisted theme sets are identical -- these positions "
                         "move with the same persisted themes")
            else:
                label = "partially_co_exposed"
                basis = "some, not all, persisted themes name both positions"
            views.append(PairCorrelationView(
                ticker_a=a, ticker_b=b, correlation_label=label,
                shared_themes=tuple(sorted(display[k] for k in shared)),
                basis=basis))
    return tuple(views)


def build_rotation_alignment(store_dir: str) -> Tuple[RotationAlignmentView, ...]:
    """One row per (recorded position, mapped theme) against the LATEST persisted
    theme-pulse state; ``no_signal`` rows for unmapped / unpulsed cases.

    Empty when no holdings are recorded. The state->alignment decision is the
    :data:`STATE_ALIGNMENT` data, never a computation.
    """
    tickers = _held_tickers(store_dir)
    if not tickers:
        return ()
    mapping = ticker_theme_map(store_dir)
    states = _latest_pulse_states(store_dir)
    views = []
    for ticker in tickers:
        themes = mapping.get(ticker, ())
        if not themes:
            views.append(RotationAlignmentView(
                ticker=ticker, theme_id="", theme_state="",
                alignment_label="no_signal", run_id="",
                basis=("no persisted signal or theme pulse maps this position to "
                       "any theme -- no rotation signal exists for it")))
            continue
        for theme in themes:
            entry = states.get(_norm_theme(theme))
            if entry is None:
                views.append(RotationAlignmentView(
                    ticker=ticker, theme_id=theme, theme_state="",
                    alignment_label="no_signal", run_id="",
                    basis=("the persisted records map this position to the theme, "
                           "but no theme pulse is persisted for it")))
                continue
            display, state, run_id = entry
            views.append(RotationAlignmentView(
                ticker=ticker, theme_id=display, theme_state=state,
                alignment_label=STATE_ALIGNMENT.get(state, "no_signal"),
                run_id=run_id,
                basis=("the latest persisted pulse for this theme (run {0}) "
                       "carries state {1}; alignment follows the published "
                       "state-to-alignment table".format(run_id or "unknown",
                                                         state))))
    return tuple(views)


def compare_candidate(store_dir: str, ticker: str,
                      candidate_themes: Tuple[str, ...] = ()) -> CandidateComparison:
    """One candidate vs the current recorded exposure -- a LABEL, never advice.

    ``candidate_themes`` may be supplied (e.g. from journaled diligence inputs);
    otherwise the persisted mapping is used. Raises ``ValueError`` (with the
    honest load reason) when no holdings are recorded -- the caller states the
    absence instead of comparing against nothing.
    """
    loaded, reason = load_holdings(store_dir)
    if loaded is None:
        raise ValueError(reason)
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        raise ValueError("compare_candidate requires a candidate ticker")
    mapping = ticker_theme_map(store_dir)
    themes = tuple(candidate_themes) or mapping.get(symbol, ())
    theme_keys = {_norm_theme(t): t for t in themes}
    already = symbol in {p.ticker for p in loaded.positions}
    recorded_theme_keys: Dict[str, str] = {}
    for position in loaded.positions:
        for theme in mapping.get(position.ticker, ()):
            recorded_theme_keys.setdefault(_norm_theme(theme), theme)
    overlap = tuple(sorted(
        theme_keys[k] for k in theme_keys if k in recorded_theme_keys))
    new = tuple(sorted(
        theme_keys[k] for k in theme_keys if k not in recorded_theme_keys))
    gaps: Tuple[str, ...] = ()
    if already:
        label = "adds_concentration"
        basis = ("the candidate is already a recorded position -- more of it "
                 "concentrates the existing exposure")
    elif not themes:
        label = "no_theme_signal"
        basis = ("no persisted record and no supplied input maps this candidate "
                 "to any theme -- the comparison is honestly indeterminate")
        gaps = ("no theme mapping exists for the candidate; record diligence "
                "inputs or run a pulse that names it",)
    elif not overlap:
        label = "new_theme"
        basis = ("every candidate theme is absent from the current recorded "
                 "exposure -- the candidate introduces new theme exposure")
    elif not new:
        label = "adds_concentration"
        basis = ("every candidate theme is already present in the current "
                 "recorded exposure -- the candidate concentrates what is held")
    else:
        label = "diversifies"
        basis = ("the candidate shares some themes with the current exposure and "
                 "adds others -- it partially overlaps and partially extends")
    return CandidateComparison(
        candidate_ticker=symbol,
        comparison_label=label,
        candidate_themes=tuple(sorted(themes)),
        overlapping_themes=overlap,
        new_themes=new,
        already_recorded=already,
        basis=basis,
        data_gaps=gaps,
    )
