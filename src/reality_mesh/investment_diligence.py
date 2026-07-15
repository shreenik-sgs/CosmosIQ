"""Operator-accepted investment-diligence theses (DILIGENCE-LINEAGE slice 2).

Slice 1/1b took a graph-connected, real-evidence-corroborated ticker up to the honest ceiling
``ineligible_missing_diligence``: it had fused-signal refs + a real opportunity-hypothesis packet,
but NO accepted diligence thesis, so it could never be ``eligible``. Slice 2 supplies that final
link -- but ONLY as a REAL, persisted, evidence-grounded, OPERATOR-accepted thesis. There is NO
auto-generation and NO auto-acceptance anywhere in this module: the engine NEVER writes a thesis on
its own. The "accepted engine" in the architecture is the HUMAN OPERATOR (Manual Review Only); this
module merely RECORDS the operator's written conclusion append-only, layered on canonical evidence.

An :class:`InvestmentDiligence` is the operator's REVIEW JUDGMENT, never a data claim:

* its source authority is ``manual`` / operator -- it is NEVER ``canonical`` (a review conclusion is
  not itself a canonical datum; laundering it as canonical is refused at construction);
* it carries a closed ``verdict`` -- only ``thesis_supported`` yields an eligibility-valid ref; a
  ``thesis_rejected`` / ``insufficient`` thesis is persisted honestly but NEVER makes a candidate
  eligible;
* it MUST name the real ``opportunity_hypothesis_ref`` it addresses and MUST cite non-empty
  ``evidence_refs`` (the real signal / event / finding ids the operator reviewed) -- a thesis
  grounded in nothing is rejected; and it MUST name the ``accepted_by`` operator;
* there is NO numeric ``score`` / ``rank`` / ``rating`` / ``sizing`` field and NO
  ``buy`` / ``sell`` / ``order`` / ``broker`` / ``trade`` / ``execution`` field anywhere -- a
  diligence thesis is a research conclusion, never a market action.

:func:`accept_diligence_thesis` is the ONLY way an eligibility-valid diligence ref is created. It
VALIDATES the full real lineage before persisting -- the ticker must be a real
``diligence_candidate`` under the run, the ``opportunity_hypothesis_ref`` must RESOLVE to the run's
real hypothesis that names the ticker, the ``evidence_refs`` must resolve in the run's stores, and
``accepted_by`` must be non-empty. It NEVER auto-fills a field. Persistence is append-only via
:class:`InvestmentDiligenceStore`; a correction is a NEW record referencing ``correction_of`` (never
a mutation). Deterministic (content-derived id + injected ``now``), stdlib-only, Python 3.9, OFFLINE.
No network / scheduler / broker; nothing reaches a live endpoint on import.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .stores import AppendOnlyStore, EventStore, FindingStore, RunStore, SignalStore
from .validation import assert_no_trade_fields

__all__ = [
    "DILIGENCE_VERDICTS",
    "ELIGIBILITY_VALID_VERDICT",
    "INVESTMENT_DILIGENCE_MODELS",
    "InvestmentDiligence",
    "InvestmentDiligenceStore",
    "accept_diligence_thesis",
    "diligence_id_for",
    "latest_diligence_for",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The operator's diligence verdict -- a closed research conclusion, never a score. Only
# ``thesis_supported`` produces an eligibility-valid diligence ref; the others are persisted
# honestly but a candidate carrying them can NEVER be eligible.
DILIGENCE_VERDICTS: Tuple[str, ...] = (
    "thesis_supported",
    "thesis_rejected",
    "insufficient",
)

# The single verdict under which the lineage may link this thesis toward ``eligible``.
ELIGIBILITY_VALID_VERDICT = "thesis_supported"

# The manual / operator source authority. A review JUDGMENT is layered on canonical evidence; it
# is itself manual and must NEVER be marked canonical (that would launder a conclusion as a datum).
_MANUAL_AUTHORITY = "manual"


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InvestmentDiligence:
    """A frozen record of ONE operator-accepted investment-diligence thesis.

    It cannot exist ungrounded: ``opportunity_hypothesis_ref`` (the real hypothesis it addresses),
    ``verdict`` (a closed conclusion), ``thesis`` (the operator's written conclusion), non-empty
    ``evidence_refs`` (the real ids the operator reviewed), and ``accepted_by`` (the operator label)
    are ALL required. Its ``source_authority`` is ``manual`` (operator) and may never be
    ``canonical``. There is NO numeric / score / rank / trade field anywhere -- it is a research
    conclusion, never a market action. Construction re-validates every invariant.
    """

    diligence_id: str = ""                 # REQUIRED, content-derived (run + ticker + hyp + accepted_at)
    ticker: str = ""                       # REQUIRED
    run_id: str = ""                       # REQUIRED -- the run whose evidence was reviewed
    opportunity_hypothesis_ref: str = ""   # REQUIRED -- the real hypothesis packet this addresses
    verdict: str = ""                      # REQUIRED, closed: DILIGENCE_VERDICTS
    thesis: str = ""                       # REQUIRED -- the operator's written conclusion
    key_risks: Tuple[str, ...] = field(default_factory=tuple)     # operator-named risks
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)  # REQUIRED non-empty, real ids
    accepted_by: str = ""                  # REQUIRED -- the operator who authored + accepted it
    accepted_at: str = ""                  # REQUIRED -- injected timestamp (no wall-clock)
    source_authority: str = _MANUAL_AUTHORITY   # manual / operator -- NEVER canonical
    schema_version: str = "diligence.1"
    correction_of: str = ""                # id of a superseded thesis ("" if not a correction)

    def __post_init__(self) -> None:
        for name in ("diligence_id", "ticker", "run_id", "opportunity_hypothesis_ref",
                     "thesis", "accepted_by", "accepted_at"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "InvestmentDiligence.{0} is required and must be non-empty -- the engine "
                    "never auto-fills it".format(name))
        if self.verdict not in DILIGENCE_VERDICTS:
            raise ValueError(
                "InvestmentDiligence.verdict {0!r} invalid (allowed: {1})".format(
                    self.verdict, list(DILIGENCE_VERDICTS)))
        if not tuple(r for r in (self.evidence_refs or ()) if str(r or "").strip()):
            raise ValueError(
                "InvestmentDiligence.evidence_refs is required and must be non-empty -- a thesis "
                "grounded in NO reviewed evidence is refused")
        if str(self.source_authority or "").strip() == "canonical":
            raise ValueError(
                "InvestmentDiligence.source_authority may never be 'canonical' -- an operator "
                "review JUDGMENT is manual, never a canonical data claim")

    @property
    def is_eligibility_valid(self) -> bool:
        """True iff this thesis's verdict is the one that may make a candidate eligible."""
        return self.verdict == ELIGIBILITY_VALID_VERDICT


# The contract (for registry / test introspection). Trade/score-clean.
INVESTMENT_DILIGENCE_MODELS = (InvestmentDiligence,)


# --------------------------------------------------------------------------- #
# Deterministic content-derived id                                              #
# --------------------------------------------------------------------------- #
def diligence_id_for(run_id: str, ticker: str, opportunity_hypothesis_ref: str,
                     accepted_at: str, *, verdict: str = "", thesis: str = "",
                     evidence_refs: Tuple[str, ...] = (), accepted_by: str = "",
                     correction_of: str = "") -> str:
    """A deterministic, content-derived diligence id (no wall-clock, order-stable).

    Derived from ``run_id`` + ``ticker`` + ``opportunity_hypothesis_ref`` + ``accepted_at`` (the
    four the spec names) plus the rest of the record content, so distinct theses -- and a later
    CORRECTION of one -- never collide on the same id, while an identical acceptance is idempotent.
    """
    token = "\x1f".join([
        str(run_id or "").strip(),
        str(ticker or "").strip().upper(),
        str(opportunity_hypothesis_ref or "").strip(),
        str(accepted_at or "").strip(),
        str(verdict or "").strip(),
        str(thesis or "").strip(),
        "\x1e".join(str(r or "").strip() for r in (evidence_refs or ())),
        str(accepted_by or "").strip(),
        str(correction_of or "").strip(),
    ])
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return "idil:{0}:{1}".format(str(ticker or "").strip().upper(), digest)


# --------------------------------------------------------------------------- #
# APPEND-ONLY store (correction-not-mutation)                                    #
# --------------------------------------------------------------------------- #
class InvestmentDiligenceStore(AppendOnlyStore):
    """The append-only log of operator-accepted :class:`InvestmentDiligence` theses.

    Composes :class:`~reality_mesh.stores.AppendOnlyStore`: NO update / delete / in-place mutation.
    A CORRECTION is a NEW record whose ``correction_of`` references the superseded thesis id -- the
    original line is byte-unchanged forever. Re-accepting a byte-identical thesis is idempotent by
    its content-derived id. No network / broker call.
    """

    filename = "investment_diligence.jsonl"
    record_cls = InvestmentDiligence
    id_field = "diligence_id"
    timestamp_field = "accepted_at"
    ticker_fields = ("ticker",)

    def accept(self, diligence: InvestmentDiligence) -> str:
        """Append ONE thesis append-only; idempotent when byte-identical already present."""
        if diligence in self.read_all():
            return diligence.diligence_id
        return self.append(diligence)


def latest_diligence_for(store_dir: str, *, run_id: str, ticker: str,
                         opportunity_hypothesis_ref: str) -> Optional[InvestmentDiligence]:
    """The newest NON-SUPERSEDED accepted thesis for a run / ticker / hypothesis, or ``None``.

    Reads the append-only store for records matching ``run_id`` + ``ticker`` +
    ``opportunity_hypothesis_ref``, drops any thesis a later record CORRECTS (``correction_of``),
    and returns the last remaining (newest) one -- regardless of its verdict (the caller decides
    what a ``thesis_rejected`` / ``insufficient`` verdict means). Never fabricates a record.
    """
    symbol = str(ticker or "").strip().upper()
    hyp = str(opportunity_hypothesis_ref or "").strip()
    records = tuple(
        r for r in InvestmentDiligenceStore(store_dir).read_all()
        if r.run_id == str(run_id or "").strip()
        and r.ticker == symbol
        and r.opportunity_hypothesis_ref == hyp)
    superseded = {str(r.correction_of).strip() for r in records if str(r.correction_of).strip()}
    live = [r for r in records if r.diligence_id not in superseded]
    return live[-1] if live else None


# --------------------------------------------------------------------------- #
# Resolvable-evidence introspection (real ids from the run's stores)            #
# --------------------------------------------------------------------------- #
def _resolvable_refs(store_dir: str, run_id: str) -> frozenset:
    """Every real ref the operator could legitimately cite for ``run_id`` (record ids + their refs).

    The union of the run's persisted signal / event / finding record ids AND the underlying
    ``source_refs`` / ``evidence_refs`` each carries -- so an operator may cite either a fused-signal
    id or the underlying SEC/evidence ref, and nothing that is not in the run's real stores resolves.
    """
    resolvable: set = set()
    signals = SignalStore(store_dir).query(run_id=run_id)
    events = EventStore(store_dir).query(run_id=run_id)
    findings = FindingStore(store_dir).query(run_id=run_id)
    for s in signals:
        resolvable.add(str(getattr(s, "signal_id", "") or ""))
        resolvable.update(str(r) for r in tuple(getattr(s, "source_refs", ()) or ()))
        resolvable.update(str(r) for r in tuple(getattr(s, "evidence_refs", ()) or ()))
    for e in events:
        resolvable.add(str(getattr(e, "event_id", "") or ""))
        resolvable.update(str(r) for r in tuple(getattr(e, "source_refs", ()) or ()))
        resolvable.update(str(r) for r in tuple(getattr(e, "evidence_refs", ()) or ()))
    for f in findings:
        resolvable.add(str(getattr(f, "finding_id", "") or ""))
        resolvable.update(str(r) for r in tuple(getattr(f, "source_refs", ()) or ()))
        resolvable.update(str(r) for r in tuple(getattr(f, "evidence_refs", ()) or ()))
    resolvable.discard("")
    return frozenset(resolvable)


# --------------------------------------------------------------------------- #
# The ONLY way to create an eligibility-valid diligence ref                      #
# --------------------------------------------------------------------------- #
def accept_diligence_thesis(
    store_dir: str,
    *,
    ticker: str,
    run_id: str,
    opportunity_hypothesis_ref: str,
    verdict: str,
    thesis: str,
    key_risks: Tuple[str, ...] = (),
    evidence_refs: Tuple[str, ...],
    accepted_by: str,
    now: str,
    correction_of: str = "",
) -> InvestmentDiligence:
    """Record ONE operator-accepted diligence thesis append-only. The ONLY path to a valid ref.

    NEVER auto-generates or auto-fills anything -- every field is the operator's. VALIDATES the full
    REAL lineage before persisting (raising ``ValueError`` -- honestly refusing -- on any gap):

    * the run exists, and the ticker is a REAL ``diligence_candidate`` under it (re-run over the
      persisted evidence, ``persist=False``);
    * ``opportunity_hypothesis_ref`` RESOLVES to the run's real hypothesis that names the ticker --
      a thesis for a ticker with NO hypothesis is REFUSED;
    * ``verdict`` is a closed member; ``thesis`` and ``accepted_by`` are non-empty;
    * ``evidence_refs`` is non-empty and every ref RESOLVES in the run's stores;
    * ``correction_of`` (if given) references an existing persisted thesis for this ticker.

    Persists the frozen :class:`InvestmentDiligence` (content-derived id, injected ``accepted_at``
    = ``now``) and returns it. A ``thesis_rejected`` / ``insufficient`` verdict is recorded honestly
    but is NOT eligibility-valid. Deterministic + offline; no network / broker.
    """
    if not str(store_dir or "").strip():
        raise ValueError("accept_diligence_thesis requires a non-empty store_dir")
    symbol = str(ticker or "").strip().upper()
    run = str(run_id or "").strip()
    hyp = str(opportunity_hypothesis_ref or "").strip()
    verdict_clean = str(verdict or "").strip()
    thesis_clean = str(thesis or "").strip()
    accepted = str(accepted_by or "").strip()
    accepted_at = str(now or "").strip()
    correction = str(correction_of or "").strip()
    evidence = tuple(str(r or "").strip() for r in (evidence_refs or ()) if str(r or "").strip())
    risks = tuple(str(r or "").strip() for r in (key_risks or ()) if str(r or "").strip())

    if not symbol:
        raise ValueError("accept_diligence_thesis requires a non-empty ticker")
    if not run:
        raise ValueError("accept_diligence_thesis requires a non-empty run_id")
    if not accepted_at:
        raise ValueError(
            "accept_diligence_thesis requires an injected 'now' -- accepted_at is never a "
            "wall-clock read")
    if verdict_clean not in DILIGENCE_VERDICTS:
        raise ValueError(
            "verdict {0!r} invalid (allowed: {1}) -- the operator states a closed conclusion".format(
                verdict_clean, list(DILIGENCE_VERDICTS)))
    if not thesis_clean:
        raise ValueError("a written thesis conclusion is required -- the operator authors it")
    if not accepted:
        raise ValueError(
            "accepted_by is required -- an accepted thesis names the operator who authored it; "
            "the engine never accepts a thesis on its own")
    if not evidence:
        raise ValueError(
            "evidence_refs is required and must be non-empty -- a thesis grounded in NO reviewed "
            "evidence is refused")

    runs = RunStore(store_dir).query(run_id=run)
    if not runs:
        raise ValueError(
            "no persisted run with run_id {0!r} -- a diligence thesis reviews a CURRENT run's "
            "evidence".format(run))

    # -- the ticker must be a REAL diligence candidate whose hypothesis RESOLVES for this run -- #
    # Composed over the persisted evidence, read-only (never re-injects a fixture, writes nothing).
    from .diligence_lineage import run_diligence_lineage
    result = run_diligence_lineage(
        store_dir, run_id=run, watchlist=(symbol,), now=accepted_at, persist=False)
    outcome = next((o for o in result.outcomes if o.ticker == symbol), None)
    if outcome is None or outcome.discovery_state != "diligence_candidate":
        raise ValueError(
            "{0} is not a diligence_candidate under run {1} (state {2!r}) -- a diligence thesis "
            "may only be accepted for a real, graph-connected, corroborated candidate".format(
                symbol, run, outcome.discovery_state if outcome else "absent"))
    if not outcome.opportunity_hypothesis_ref:
        raise ValueError(
            "{0} has NO opportunity_hypothesis_ref under run {1} -- a thesis for a ticker with no "
            "real hypothesis is refused (nothing to address)".format(symbol, run))
    if outcome.opportunity_hypothesis_ref != hyp:
        raise ValueError(
            "opportunity_hypothesis_ref {0!r} does not resolve to the run's real hypothesis for "
            "{1} (expected {2!r}) -- a free-string ref is refused".format(
                hyp, symbol, outcome.opportunity_hypothesis_ref))

    # -- every cited evidence ref must resolve in the run's real stores -- #
    resolvable = _resolvable_refs(store_dir, run)
    unresolved = [r for r in evidence if r not in resolvable]
    if unresolved:
        raise ValueError(
            "evidence_refs {0} do not resolve in run {1}'s stores -- the operator may only cite "
            "real reviewed signal / event / finding ids (or their source/evidence refs)".format(
                unresolved, run))

    # -- a correction must reference an existing persisted thesis for this ticker -- #
    if correction:
        known = {r.diligence_id for r in InvestmentDiligenceStore(store_dir).read_all()
                 if r.ticker == symbol}
        if correction not in known:
            raise ValueError(
                "correction_of {0!r} references no persisted diligence thesis for {1} -- a "
                "correction supersedes a REAL prior record".format(correction, symbol))

    diligence = InvestmentDiligence(
        diligence_id=diligence_id_for(
            run, symbol, hyp, accepted_at, verdict=verdict_clean, thesis=thesis_clean,
            evidence_refs=evidence, accepted_by=accepted, correction_of=correction),
        ticker=symbol,
        run_id=run,
        opportunity_hypothesis_ref=hyp,
        verdict=verdict_clean,
        thesis=thesis_clean,
        key_risks=risks,
        evidence_refs=evidence,
        accepted_by=accepted,
        accepted_at=accepted_at,
        source_authority=_MANUAL_AUTHORITY,
        correction_of=correction)
    InvestmentDiligenceStore(store_dir).accept(diligence)
    return diligence


# --------------------------------------------------------------------------- #
# Construction-time guard: the contract may carry NO trade / score field.        #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(InvestmentDiligence)
