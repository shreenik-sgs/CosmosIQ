"""Ingestion vertical slice -- fixtures -> evidence -> Observations -> Tattva.

IMPLEMENTATION-009E. A deterministic, fixture-backed ingestion vertical slice
that wires the EXISTING ingestion pieces together and STOPS AT TATTVA:

1. **Parse** each provided fixture with its existing adapter parser
   (SEC / FMP / yfinance) into ``NormalizedEvidenceRecord``s.
2. **Arbitrate** across sources by source authority
   (``resolve_conflicts`` + the additive ``winning_records``): a canonical SEC
   filing beats an FMP convenience row beats a yfinance fallback row for the same
   semantic fact / period / unit.
3. **Map** each WINNING record into a canonical Tattva ``Observation`` (vocabulary-
   driven: attempt to map, defer only on ``MappingDeferredError``). Financial reports
   / catalysts map to SIGNAL-bearing Observations; OHLCV / profile / ownership / quote
   / share counts map to NEUTRAL FACTUAL Observations (raw facts, no inferred signal).
   Overridden financial facts (a higher-authority source owns them) are DEFERRED,
   never mapped, never hidden.
4. **Assess** the produced Observations with the EXISTING, unchanged Reality
   Intelligence (Tattva) layer (``generate_intelligence_assessment``).

Discipline this module keeps:

* NO network access, NO API keys, NO secrets, NO scheduling / background jobs.
  Everything is a pure function of already-loaded fixture dicts and an explicit
  ``now`` -- two runs produce byte-identical ids.
* It imports ONLY ``evidence_ingestion`` + ``reality_intelligence`` + ``eios_core``.
  It NEVER imports or produces a genesis / prometheus / personal_cio /
  execution_manual object -- the slice stops at the Intelligence Assessment.
* It performs NO investment scoring or judgement of its own: all inference is the
  existing Tattva layer's; this module only orchestrates parse -> arbitrate ->
  map -> assess and reports provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eios_core.graph_refs import Ref

from reality_intelligence.intelligence_assessment import (
    IntelligenceAssessment,
    generate_intelligence_assessment,
)

from .evidence_records import NormalizedEvidenceRecord
from .mapper import map_to_observation
from .conflict import resolve_conflicts, winning_records, _record_entries
from .sec_edgar import parse_sec_submissions, parse_sec_companyfacts
from .fmp import (
    parse_fmp_income_statement,
    parse_fmp_profile,
    parse_fmp_ohlcv,
    parse_fmp_news,
    parse_fmp_ownership,
    map_fmp_record,
    MappingDeferredError,
)
from .yfinance_adapter import (
    parse_yfinance_history,
    parse_yfinance_quote,
    map_yfinance_record,
)


def _map_record(
    rec: NormalizedEvidenceRecord, *, domain: str, actor: str, now: float
) -> Tuple[Any, Tuple[str, ...]]:
    """Vocabulary-driven map: dispatch to the record's own adapter map function.

    Each adapter maps a supported record (signal-bearing OR neutral factual) to a
    canonical Tattva Observation, or raises ``MappingDeferredError`` for a category
    that still has no safe Tattva representation. SEC records map directly.
    """
    nt = str(rec.normalized_type or "")
    if nt.startswith("yf_"):
        return map_yfinance_record(rec, domain=domain, actor=actor, now=now)
    if nt.startswith("fmp_"):
        return map_fmp_record(rec, domain=domain, actor=actor, now=now)
    return map_to_observation(rec, domain=domain, actor=actor, now=now)


def _financial_key(rec: NormalizedEvidenceRecord) -> Optional[Tuple[Any, ...]]:
    """Return the single financial-fact conflict key for a financial record, else None.

    A financial record (one carrying ``financial_metric``) yields exactly one
    ``_record_entries`` key; non-financial records return None.
    """
    if not (rec.extracted_fields or {}).get("financial_metric"):
        return None
    entries = list(_record_entries(rec))
    return entries[0][0] if entries else None


# --------------------------------------------------------------------------- #
# Result structures (all frozen).                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProvenanceTraceEntry:
    """One Observation's provenance trace back to its evidence + source.

    Observation -> NormalizedEvidenceRecord -> RawEvidenceRecord -> source. The
    raw record is bound by its content-addressed ``Ref`` (the immutable-provenance
    model never hands the object downstream; it binds it by ``(id, version)``).
    """

    observation_id: str = ""
    observation_ref: Optional[Ref] = None
    normalized_record_id: str = ""
    normalized_record_ref: Optional[Ref] = None
    raw_record_ref: Optional[Ref] = None
    source_name: str = ""
    source_authority: str = ""
    source_class: str = ""
    source_provider: str = ""
    source_ref: str = ""


@dataclass(frozen=True)
class ProvenanceChain:
    """The full slice provenance: every Observation's trace + the IA that binds them."""

    traces: Tuple[ProvenanceTraceEntry, ...] = ()
    intelligence_assessment_id: Optional[str] = None
    grounding_observation_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IngestionVerticalSliceResult:
    """The deterministic outcome of one fixture-backed ingestion slice.

    Stops at the Intelligence Assessment (Tattva). Carries NO genesis / prometheus
    / personal_cio / execution_manual object and no such field.
    """

    subject: str = ""
    raw_records: Tuple[Ref, ...] = ()
    normalized_records: Tuple[NormalizedEvidenceRecord, ...] = ()
    resolved_facts: Dict[Tuple[Any, ...], Any] = field(default_factory=dict)
    conflict_warnings: Tuple[str, ...] = ()
    mapper_warnings: Tuple[str, ...] = ()
    observations: Tuple[Any, ...] = ()
    deferred_records: Tuple[NormalizedEvidenceRecord, ...] = ()
    deferred_reasons: Tuple[str, ...] = ()
    intelligence_assessment: Optional[IntelligenceAssessment] = None
    source_coverage_summary: Dict[str, Any] = field(default_factory=dict)
    authority_summary: Dict[str, int] = field(default_factory=dict)
    data_gaps: Tuple[Tuple[str, str], ...] = ()
    provenance_chain: Optional[ProvenanceChain] = None


# --------------------------------------------------------------------------- #
# Orchestration.                                                              #
# --------------------------------------------------------------------------- #


def run_fixture_ingestion_slice(
    *,
    subject: str,
    domain: str,
    sec_submissions: Optional[Dict[str, Any]] = None,
    sec_companyfacts: Optional[Dict[str, Any]] = None,
    fmp_income_statement: Any = None,
    fmp_profile: Any = None,
    fmp_ohlcv: Any = None,
    fmp_news: Any = None,
    fmp_ownership: Any = None,
    yf_history: Any = None,
    yf_quote: Any = None,
    actor: str = "evidence-ingestion",
    now: float,
    yf_quote_as_of: str = "",
    retrieved_at: str = "",
) -> IngestionVerticalSliceResult:
    """Run the fixtures -> evidence -> Observations -> Tattva slice, deterministically.

    Each ``*_json`` / fixture argument is an already-loaded payload (a test loads a
    local JSON fixture via ``open()``; NOTHING is fetched here). ``now`` is explicit
    epoch-seconds so every content-addressed id is reproducible. ``yf_quote_as_of``
    is the period the yfinance quote's ``sharesOutstanding`` refers to, so it can
    share a period with the SEC / FMP shares fact and arbitrate against them (and
    lose). The slice STOPS at the Intelligence Assessment.
    """
    # --- 1. Parse each provided fixture with its existing parser --------------
    parsed: List[Tuple[str, Any]] = []
    if sec_submissions is not None:
        parsed.append(("SEC EDGAR",
                       parse_sec_submissions(sec_submissions, now=now,
                                             retrieved_at=retrieved_at, actor=actor)))
    if sec_companyfacts is not None:
        parsed.append(("SEC EDGAR",
                       parse_sec_companyfacts(sec_companyfacts, now=now,
                                              retrieved_at=retrieved_at, actor=actor)))
    if fmp_income_statement is not None:
        parsed.append(("FMP",
                       parse_fmp_income_statement(fmp_income_statement, now=now,
                                                  retrieved_at=retrieved_at, actor=actor)))
    if fmp_profile is not None:
        parsed.append(("FMP",
                       parse_fmp_profile(fmp_profile, now=now,
                                         retrieved_at=retrieved_at, actor=actor)))
    if fmp_ohlcv is not None:
        parsed.append(("FMP",
                       parse_fmp_ohlcv(fmp_ohlcv, now=now,
                                       retrieved_at=retrieved_at, actor=actor)))
    if fmp_news is not None:
        parsed.append(("FMP",
                       parse_fmp_news(fmp_news, now=now,
                                      retrieved_at=retrieved_at, actor=actor)))
    if fmp_ownership is not None:
        parsed.append(("FMP",
                       parse_fmp_ownership(fmp_ownership, now=now,
                                           retrieved_at=retrieved_at, actor=actor)))
    if yf_history is not None:
        parsed.append(("yfinance",
                       parse_yfinance_history(yf_history, now=now,
                                              retrieved_at=retrieved_at, actor=actor)))
    if yf_quote is not None:
        parsed.append(("yfinance",
                       parse_yfinance_quote(yf_quote, now=now, as_of=yf_quote_as_of,
                                            retrieved_at=retrieved_at, actor=actor)))

    all_normalized: List[NormalizedEvidenceRecord] = []
    adapter_warnings: List[str] = []
    coverage_gaps: List[Tuple[str, str]] = []
    source_coverage: Dict[str, Dict[str, Any]] = {}

    for source_label, result in parsed:
        for w in (result.warnings or ()):
            adapter_warnings.append("{0}: {1}".format(source_label, w))
            low = w.lower()
            if "missing" in low or "absent" in low or "coverage" in low:
                coverage_gaps.append(("coverage_gap", "{0}: {1}".format(source_label, w)))
        for e in (result.errors or ()):
            adapter_warnings.append("{0} error: {1}".format(source_label, e))
        for rec in (result.records or ()):
            all_normalized.append(rec)

    all_normalized_t = tuple(all_normalized)

    # --- 2. Conflict resolution / arbitration --------------------------------
    resolved_facts, conflict_warnings = resolve_conflicts(all_normalized_t)
    winners = winning_records(all_normalized_t)

    # --- 3. Map SUPPORTED + WINNING records into Observations ----------------
    observations: List[Any] = []
    deferred_records: List[NormalizedEvidenceRecord] = []
    deferred_reasons: List[str] = []
    data_gaps: List[Tuple[str, str]] = list(coverage_gaps)
    mapper_warnings: List[str] = list(adapter_warnings)
    traces: List[ProvenanceTraceEntry] = []

    for rec in all_normalized_t:
        src = rec.source
        src_name = src.source_name if src is not None else ""
        nt = str(rec.normalized_type or "")

        # (a) Financial fact that LOST arbitration -- overridden by a
        #     higher-authority source. Do NOT map; record it as overridden. This
        #     holds for BOTH signal-bearing financial facts and the neutral factual
        #     share-count fact (shares_outstanding), which still arbitrates.
        fkey = _financial_key(rec)
        if fkey is not None:
            winner = winners.get(fkey)
            if winner is not None and winner is not rec:
                win_src = winner.source.source_name if winner.source else "?"
                reason = "overridden by higher-authority {0} ({1})".format(
                    win_src, winner.source_authority)
                deferred_records.append(rec)
                deferred_reasons.append(reason)
                data_gaps.append((
                    "overridden_financial_fact",
                    "{0} [{1}]: {2}".format(rec.normalized_type, src_name, reason),
                ))
                continue

        # (b) Vocabulary-driven map-or-defer. Attempt to map; a record whose category
        #     still has no safe Tattva representation raises MappingDeferredError and
        #     is kept as evidence with its real reason (NEVER hidden). Formerly-deferred
        #     OHLCV / profile / ownership / quote now map to NEUTRAL factual Observations.
        try:
            obs, warns = _map_record(rec, domain=domain, actor=actor, now=now)
        except MappingDeferredError as exc:
            reason = str(exc)
            deferred_records.append(rec)
            deferred_reasons.append(reason)
            data_gaps.append((
                "tattva_vocabulary_deferred",
                "{0} [{1}]: {2}".format(nt, src_name, reason),
            ))
            continue

        observations.append(obs)
        for w in warns:
            mapper_warnings.append("map[{0}]: {1}".format(rec.normalized_type, w))
        traces.append(ProvenanceTraceEntry(
            observation_id=obs.id,
            observation_ref=obs.ref("Observation"),
            normalized_record_id=rec.id,
            normalized_record_ref=rec.ref("NormalizedEvidenceRecord"),
            raw_record_ref=rec.source_record_ref,
            source_name=src_name,
            source_authority=rec.source_authority,
            source_class=rec.source_class,
            source_provider=(src.provider if src is not None else ""),
            source_ref=(src.source_ref if src is not None else ""),
        ))

    observations_t = tuple(observations)

    # --- 4. Tattva assessment (existing layer, unchanged) --------------------
    intelligence_assessment: Optional[IntelligenceAssessment] = None
    if observations_t:
        intelligence_assessment = generate_intelligence_assessment(
            observations_t, domain=domain, actor=actor, now=now)

    # --- Summaries -----------------------------------------------------------
    for rec in all_normalized_t:
        src = rec.source
        name = src.source_name if src is not None else "?"
        bucket = source_coverage.setdefault(
            name, {"records": 0, "observations": 0, "deferred": 0, "overridden": 0})
        bucket["records"] += 1

    obs_norm_ids = {t.normalized_record_id for t in traces}
    overridden_ids = set()
    for rec, reason in zip(deferred_records, deferred_reasons):
        if reason.startswith("overridden"):
            overridden_ids.add(rec.id)
    for rec in all_normalized_t:
        src = rec.source
        name = src.source_name if src is not None else "?"
        bucket = source_coverage[name]
        if rec.id in obs_norm_ids:
            bucket["observations"] += 1
        elif rec.id in overridden_ids:
            bucket["overridden"] += 1
        else:
            bucket["deferred"] += 1

    authority_summary: Dict[str, int] = {}
    for rec in all_normalized_t:
        authority_summary[rec.source_authority] = (
            authority_summary.get(rec.source_authority, 0) + 1)

    provenance_chain = ProvenanceChain(
        traces=tuple(traces),
        intelligence_assessment_id=(
            intelligence_assessment.id if intelligence_assessment is not None else None),
        grounding_observation_ids=tuple(o.id for o in observations_t),
    )

    return IngestionVerticalSliceResult(
        subject=subject,
        raw_records=tuple(r.source_record_ref for r in all_normalized_t),
        normalized_records=all_normalized_t,
        resolved_facts=resolved_facts,
        conflict_warnings=tuple(conflict_warnings),
        mapper_warnings=tuple(mapper_warnings),
        observations=observations_t,
        deferred_records=tuple(deferred_records),
        deferred_reasons=tuple(deferred_reasons),
        intelligence_assessment=intelligence_assessment,
        source_coverage_summary=source_coverage,
        authority_summary=authority_summary,
        data_gaps=tuple(data_gaps),
        provenance_chain=provenance_chain,
    )
