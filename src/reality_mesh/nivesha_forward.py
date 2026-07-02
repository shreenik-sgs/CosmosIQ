"""Nivesha Forward Scenario Engine / adapter -- an INPUT SIDECAR (IMPLEMENTATION-012I).

Extends the Reality Mesh (012A-012H) with evidence-backed FORWARD-SCENARIO objects and a
Nivesha-ready INPUT adapter. Governed by ``HANDOFF_CONTRACT_012`` / ``ARCHITECTURE_CONTRACT_012``
/ ``AGENT_MAP_012 §3.6`` / ``TEST_MATRIX_012 §F``.

A forward scenario here is an evidence-backed INPUT (an assumption a company / analyst / an
operator supplied), NEVER a thesis or a decision. This module deliberately produces:

* **no thesis, no buy / sell / hold, no order / trade / broker affordance**;
* **no numeric investability metric, no ``score`` / ``rank`` / ``rating``** -- forward
  quality lives in the closed provenance labels (source_authority / claim_status), never a
  number;
* **nothing fabricated.** A forward assumption Nivesha could use but no evidence supports
  becomes an explicit DATA GAP, never an invented value.

The discipline mirrors the accepted 011D handoff adapter
(:mod:`diligence_enrichment.nivesha_adapter`):

* A **manual** assumption stays ``manual`` / analyst -- NEVER canonical.
* A **company-guidance** assumption stays ``company_claim`` -- NEVER ``verified_fact``.
* A ``target_price`` assumption is REJECTED unless it is explicitly source-backed OR
  manually labelled -- so an unlabelled price target can never slip in as evidence.
* The adapter maps ONLY evidence-established forward inputs into Nivesha's bare
  ``DiligenceInputs`` (leaving ``None`` / the dataclass default wherever an assumption is
  not established), and keeps ALL provenance / authority / claim_status / gaps in the
  returned :class:`ForwardSidecarMapping` sidecar. Provenance is never laundered into the
  bare inputs, and a ``target_price`` is NEVER pushed into a Nivesha price field. Nivesha's
  own accepted reasoning is what produces any thesis -- insufficient inputs give Nivesha's
  honest LIMITED thesis, not a padded one.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Imports the Nivesha input TYPES only
(``prometheus.diligence_inputs``) at module scope -- it never imports or modifies Nivesha's
reasoning. The optional :func:`run_nivesha_thesis_on_forward_sidecar` helper imports the
accepted ``generate_investment_thesis`` LAZILY so importing this module stays inert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from prometheus.diligence_inputs import CandidateInput, DiligenceInputs

from . import labels as _labels


# --------------------------------------------------------------------------- #
# Closed vocabularies for the forward-scenario objects                          #
# --------------------------------------------------------------------------- #

# The forward-assumption names Nivesha's forward-revenue / scenario engine reasons over
# (AGENT_MAP_012 §3.6: NRE / design wins / pre-production contracts / backlog / ramp /
# pipeline conversion / capacity / future margin / operating leverage / dilution).
# ``target_price`` is special: it is only accepted when explicitly source-backed or manual.
FORWARD_INPUT_NAMES: Tuple[str, ...] = (
    "nre_revenue",
    "design_wins",
    "pre_production_contracts",
    "backlog",
    "production_ramp",
    "pipeline_conversion",
    "capacity_expansion",
    "future_gross_margin",
    "operating_leverage",
    "dilution_risk",
    "future_share_count",
    "target_price",
)

# The forward assumptions we EXPECT a full forward view to establish. ``target_price`` is
# excluded -- its absence is never itself a gap (it is optional and guard-railed), so a
# packet with no price target is not penalised for honesty.
_EXPECTED_ASSUMPTIONS: Tuple[str, ...] = tuple(
    n for n in FORWARD_INPUT_NAMES if n != "target_price")

# The scenario cases the forward engine assembles (HANDOFF/AGENT_MAP: base / upside /
# downside / delay / dilution) plus ``failure`` (thesis-breaker case for the red team).
SCENARIO_LABELS: Tuple[str, ...] = (
    "base", "upside", "downside", "delay", "dilution", "failure",
)

# The ONLY forward assumptions that have a genuine, non-laundering home on Nivesha's bare
# ``CandidateInput``. ``backlog`` is a real forward-revenue magnitude; ``dilution_risk`` is a
# real capital-structure label. Everything else (NRE, design wins, ramp, future margin,
# future share count, target price, ...) is a forward PROJECTION with no honest slot on the
# CURRENT-state candidate, so it stays sidecar-only -- never laundered into a present fact.
_NIVESHA_MAPPABLE: Tuple[str, ...] = ("backlog", "dilution_risk")

_DILUTION_LABELS: Tuple[str, ...] = ("none", "low", "moderate", "high")


# --------------------------------------------------------------------------- #
# 1. ForwardScenarioInput -- one evidence-backed forward assumption             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ForwardScenarioInput:
    """One forward assumption, evidence-backed and label-only (never a decision).

    ``value_or_label`` is the raw datum (a number) OR a qualitative label -- there is NO
    score / rank / rating anywhere. ``source_authority`` and ``claim_status`` are closed
    provenance labels carried verbatim; ``evidence_refs`` names the origin. Validation
    (``__post_init__``) enforces the boundary invariants:

    * a **manual** assumption is never canonical (authority coerced to ``manual`` when blank,
      rejected if ``canonical``);
    * a **company-guidance** assumption is ``company_claim``, never ``verified_fact``;
    * a ``target_price`` assumption is REJECTED unless it is source-backed (a real authority
      + evidence_refs) OR explicitly ``is_manual`` labelled.
    """
    name: str = ""
    value_or_label: Optional[object] = None
    source_authority: str = ""              # closed: SOURCE_AUTHORITIES ("" = gap)
    claim_status: str = ""                  # closed: CLAIM_STATUSES ("" = gap)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    is_manual: bool = False
    is_company_guidance: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if self.name not in FORWARD_INPUT_NAMES:
            raise ValueError(
                "ForwardScenarioInput.name {0!r} not an allowed forward input (allowed: {1})"
                .format(self.name, list(FORWARD_INPUT_NAMES)))
        if not _labels.is_member(_labels.SOURCE_AUTHORITIES, self.source_authority):
            raise ValueError(
                "ForwardScenarioInput.source_authority {0!r} invalid".format(
                    self.source_authority))
        if not _labels.is_member(_labels.CLAIM_STATUSES, self.claim_status):
            raise ValueError(
                "ForwardScenarioInput.claim_status {0!r} invalid".format(self.claim_status))

        # --- manual stays manual, never canonical ------------------------------ #
        if self.is_manual:
            if self.source_authority == "":
                object.__setattr__(self, "source_authority", "manual")
            if self.claim_status == "":
                object.__setattr__(self, "claim_status", "manual")
            if self.source_authority == "canonical":
                raise ValueError(
                    "ForwardScenarioInput: a manual assumption may never be canonical")
            if self.claim_status not in ("manual", "analyst_estimate"):
                raise ValueError(
                    "ForwardScenarioInput: a manual assumption must be manual/analyst_estimate,"
                    " got {0!r}".format(self.claim_status))

        # --- company guidance stays company_claim, never verified_fact --------- #
        if self.is_company_guidance:
            if self.claim_status == "":
                object.__setattr__(self, "claim_status", "company_claim")
            if self.claim_status == "verified_fact":
                raise ValueError(
                    "ForwardScenarioInput: company guidance may never be a verified_fact")

        # --- a manual/analyst datum may never be marked canonical (belt+braces) - #
        if self.source_authority == "canonical" and self.claim_status in (
                "manual", "analyst_estimate"):
            raise ValueError(
                "ForwardScenarioInput: a manual/analyst datum may never be canonical")

        # --- no unlabelled target price --------------------------------------- #
        if self.name == "target_price" and not self._target_price_permitted():
            raise ValueError(
                "ForwardScenarioInput: a target_price is rejected unless it is source-backed"
                " (a real source_authority + evidence_refs) or explicitly is_manual")

    def _target_price_permitted(self) -> bool:
        """A target price is allowed only if manually labelled OR genuinely source-backed."""
        if self.is_manual:
            return True
        source_backed = bool(self.evidence_refs) and self.source_authority not in ("", "rumor")
        return source_backed

    @property
    def present(self) -> bool:
        return self.value_or_label is not None and self.value_or_label != ""


# --------------------------------------------------------------------------- #
# 2. ForwardScenarioCase -- one scenario + its inputs + its data gaps            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ForwardScenarioCase:
    """One forward scenario case (base/upside/downside/delay/dilution/failure).

    ``inputs`` are the evidence-backed forward assumptions established for this case;
    ``data_gaps`` are the expected assumptions that stayed UNFILLED -- an explicit,
    honest gap, never a fabricated value. There is NO thesis / score / decision here.
    """
    label: str = ""
    inputs: Tuple[ForwardScenarioInput, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if self.label not in SCENARIO_LABELS:
            raise ValueError(
                "ForwardScenarioCase.label {0!r} not a scenario label (allowed: {1})".format(
                    self.label, list(SCENARIO_LABELS)))
        for inp in self.inputs:
            if not isinstance(inp, ForwardScenarioInput):
                raise ValueError(
                    "ForwardScenarioCase.inputs must be ForwardScenarioInput objects")

    def input_names(self) -> Tuple[str, ...]:
        return tuple(inp.name for inp in self.inputs)


# --------------------------------------------------------------------------- #
# 3. ForwardScenarioPacket -- per company/ticker forward-input package           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ForwardScenarioPacket:
    """The per-ticker forward-scenario INPUT package handed to Nivesha as a sidecar.

    Carries the scenario ``cases`` + preserved ``evidence_refs`` / ``source_refs`` +
    aggregate ``data_gaps`` + ``conflicts`` + ``provenance_refs``. It is an INPUT: there is
    NO thesis, NO score / rank, NO buy / sell / hold, NO order anywhere on it.
    """
    ticker: str = ""
    company: str = ""
    hypothesis_ref: str = ""
    cases: Tuple[ForwardScenarioCase, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    conflicts: Tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"       # closed: CONFIDENCE_LABELS
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or self.ticker.strip() == "":
            raise ValueError("ForwardScenarioPacket.ticker is required and must be non-empty")
        if not _labels.is_member(_labels.CONFIDENCE_LABELS, self.confidence_label):
            raise ValueError(
                "ForwardScenarioPacket.confidence_label {0!r} invalid".format(
                    self.confidence_label))
        for case in self.cases:
            if not isinstance(case, ForwardScenarioCase):
                raise ValueError(
                    "ForwardScenarioPacket.cases must be ForwardScenarioCase objects")

    def case(self, label: str) -> Optional[ForwardScenarioCase]:
        for c in self.cases:
            if c.label == label:
                return c
        return None

    def scenario_labels(self) -> Tuple[str, ...]:
        return tuple(c.label for c in self.cases)


# --------------------------------------------------------------------------- #
# 4. Provenance sidecar for the Nivesha-ready adapter                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ForwardMappedField:
    """One Nivesha candidate field populated from a forward assumption, WITH provenance.

    Records which forward assumption / scenario the value came from and its authority /
    claim_status / evidence_refs. This is provenance, NEVER a score or a ranking key.
    """
    candidate_field: str = ""
    value: Optional[object] = None
    forward_name: str = ""
    scenario_label: str = ""
    authority: str = ""
    claim_status: str = ""
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


@dataclass(frozen=True)
class ForwardSidecarMapping:
    """The provenance + gap sidecar returned next to the adapted ``DiligenceInputs``.

    ``mapped_fields`` records every candidate field the adapter populated from an
    evidence-established forward assumption and where it came from. ``gaps`` lists every
    forward assumption that stayed UNESTABLISHED -- the honest insufficient representation,
    never a fabricated value. ``preserved_*`` carry the packet's own gaps / evidence through
    unchanged. There is NO thesis, strength, score, rank, or buy / sell / hold anywhere.
    """
    ticker: str = ""
    mapped_fields: Tuple[ForwardMappedField, ...] = field(default_factory=tuple)
    gaps: Tuple[str, ...] = field(default_factory=tuple)
    preserved_data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    preserved_evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    scenario_labels: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


# --------------------------------------------------------------------------- #
# Builder: assemble scenario cases from evidence, gaps for everything unfilled   #
# --------------------------------------------------------------------------- #
def _dedupe(items) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(x for x in items if x))


def build_forward_scenario_packet(
    *,
    ticker: str = "",
    company: str = "",
    hypothesis: Any = None,
    enrichment: Any = None,
    inputs: Optional[Dict[str, Tuple[ForwardScenarioInput, ...]]] = None,
    conflicts: Tuple[str, ...] = (),
    confidence_label: str = "missing",
    note: str = "",
) -> ForwardScenarioPacket:
    """Assemble a :class:`ForwardScenarioPacket` from evidence.

    ``inputs`` maps a scenario label -> the tuple of evidence-backed
    :class:`ForwardScenarioInput` established for it (fixture-supplied). A case is built for
    EVERY scenario label in :data:`SCENARIO_LABELS`; every EXPECTED forward assumption a case
    does not establish becomes an explicit per-case DATA GAP (never a fabricated value).
    ``evidence_refs`` / ``source_refs`` / ``provenance_refs`` are gathered from the reality-
    mesh ``hypothesis`` (an :class:`~reality_mesh.models.OpportunityHypothesisPacket`) and the
    011 ``enrichment`` bundle, and the aggregate gaps roll up onto the packet.

    Produces an INPUT packet only -- no thesis, no score, no decision.
    """
    inputs = dict(inputs or {})
    ticker = (ticker or getattr(hypothesis, "ticker", "") or "").strip().upper()
    if not ticker and enrichment is not None:
        ticker = (getattr(enrichment, "ticker", "") or "").strip().upper()
    if not ticker:
        raise ValueError("build_forward_scenario_packet requires a ticker")

    # Gather preserved evidence / provenance from the reality-mesh hypothesis + 011 bundle.
    evidence_refs: List[str] = []
    source_refs: List[str] = []
    provenance_refs: List[str] = []
    hyp_ref = ""
    if hypothesis is not None:
        hyp_ref = getattr(hypothesis, "hypothesis_id", "") or ""
        evidence_refs += list(getattr(hypothesis, "evidence_refs", ()) or ())
        evidence_refs += list(getattr(hypothesis, "supporting_evidence_refs", ()) or ())
        source_refs += list(getattr(hypothesis, "source_refs", ()) or ())
    if enrichment is not None:
        provenance_refs += list(getattr(enrichment, "provenance_refs", ()) or ())
        for area_name in ("market", "value_chain", "ir", "tam_estimate"):
            area = getattr(enrichment, area_name, None)
            source_refs += list(getattr(area, "source_refs", ()) or ())

    cases: List[ForwardScenarioCase] = []
    aggregate_gaps: List[str] = []
    for label in SCENARIO_LABELS:
        case_inputs = tuple(inputs.get(label, ()))
        established = {inp.name for inp in case_inputs if inp.present}
        # carry each input's evidence refs up onto the packet.
        for inp in case_inputs:
            evidence_refs += list(inp.evidence_refs)
        case_gaps = tuple(
            "{0}: {1} not established -- forward assumption missing (data gap)".format(
                label, name)
            for name in _EXPECTED_ASSUMPTIONS if name not in established)
        aggregate_gaps += list(case_gaps)
        cases.append(ForwardScenarioCase(
            label=label, inputs=case_inputs, data_gaps=case_gaps))

    return ForwardScenarioPacket(
        ticker=ticker,
        company=company,
        hypothesis_ref=hyp_ref,
        cases=tuple(cases),
        evidence_refs=_dedupe(evidence_refs),
        source_refs=_dedupe(source_refs),
        data_gaps=_dedupe(aggregate_gaps),
        conflicts=_dedupe(conflicts),
        provenance_refs=_dedupe(provenance_refs),
        confidence_label=confidence_label,
        note=note or "forward-scenario INPUT sidecar; no thesis / score / decision",
    )


# --------------------------------------------------------------------------- #
# Adapter: map ONLY evidence-established forward inputs into Nivesha bare inputs  #
# --------------------------------------------------------------------------- #
def _base_candidate(base_inputs, ticker: str):
    """Pick the operator-supplied manual candidate for ``ticker`` (or the first), if any."""
    if base_inputs is None or not base_inputs.candidates:
        return None
    up = (ticker or "").upper()
    for c in base_inputs.candidates:
        if (c.ticker or "").upper() == up:
            return c
    return base_inputs.candidates[0]


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mappable_from_base_case(packet: ForwardScenarioPacket):
    """The evidence-established, Nivesha-mappable forward inputs from the BASE case.

    The base case is the canonical forward projection. Only ``backlog`` (a magnitude) and
    ``dilution_risk`` (a label) have an honest home on Nivesha's CURRENT-state candidate;
    everything else is a projection kept sidecar-only. Returns ``{forward_name: input}``.
    """
    base = packet.case("base")
    if base is None:
        return {}
    established = {}
    for inp in base.inputs:
        if inp.name in _NIVESHA_MAPPABLE and inp.present:
            established[inp.name] = inp
    return established


def to_nivesha_forward_sidecar(
    packet: ForwardScenarioPacket, *,
    base_inputs: Optional[DiligenceInputs] = None,
) -> Tuple[DiligenceInputs, ForwardSidecarMapping]:
    """Map a forward packet into Nivesha-compatible ``DiligenceInputs`` + a provenance sidecar.

    Only the evidence-ESTABLISHED, non-laundering forward inputs (``backlog`` magnitude and
    ``dilution_risk`` label from the base case) overlay Nivesha's bare candidate; every other
    forward assumption stays absent (``None`` / the dataclass default) and is recorded as an
    explicit GAP. A ``target_price`` is NEVER pushed into a Nivesha price field -- it rides in
    the sidecar only. All provenance / authority / claim_status / evidence_refs travel in the
    returned :class:`ForwardSidecarMapping`, never laundered into the bare inputs. A manual
    assumption stays ``manual``; company guidance stays ``company_claim``.

    Returns ``(DiligenceInputs, ForwardSidecarMapping)``. Produces NO thesis / score / rank /
    buy / sell / hold.
    """
    ticker = (packet.ticker or "").strip().upper()
    base_cand = _base_candidate(base_inputs, ticker)

    # Start from the operator's manual candidate (if any); everything else stays at Nivesha's
    # own absent representation -- never invented.
    values: Dict[str, Any] = {}
    if base_cand is not None:
        for f in CandidateInput.__dataclass_fields__:
            values[f] = getattr(base_cand, f)
    values["ticker"] = ticker
    if not values.get("name"):
        values["name"] = ticker

    mapped: List[ForwardMappedField] = []
    gaps: List[str] = []

    established = _mappable_from_base_case(packet)

    # --- backlog: forward-revenue magnitude -> CandidateInput.backlog ---------- #
    if "backlog" in established:
        inp = established["backlog"]
        val = _float_or_none(inp.value_or_label)
        if val is not None:
            # a manual/analyst datum may never masquerade as canonical.
            if inp.source_authority == "canonical" and inp.claim_status in (
                    "manual", "analyst_estimate"):
                raise ValueError("forward backlog: manual/analyst marked canonical")
            values["backlog"] = val
            mapped.append(ForwardMappedField(
                candidate_field="backlog", value=val, forward_name="backlog",
                scenario_label="base", authority=inp.source_authority,
                claim_status=inp.claim_status, evidence_refs=tuple(inp.evidence_refs),
                note=inp.note))

    # --- dilution_risk: capital-structure label -> CandidateInput.dilution_risk  #
    if "dilution_risk" in established:
        inp = established["dilution_risk"]
        label = str(inp.value_or_label)
        if label in _DILUTION_LABELS and label != "none":
            values["dilution_risk"] = label
            mapped.append(ForwardMappedField(
                candidate_field="dilution_risk", value=label, forward_name="dilution_risk",
                scenario_label="base", authority=inp.source_authority,
                claim_status=inp.claim_status, evidence_refs=tuple(inp.evidence_refs),
                note=inp.note))

    # --- honest gaps: every EXPECTED forward assumption not established --------- #
    established_names = set(established.keys())
    for name in _EXPECTED_ASSUMPTIONS:
        if name in established_names:
            continue
        if name in _NIVESHA_MAPPABLE:
            gaps.append(
                "{0}: absent -- forward assumption not established (mappable but unfilled)"
                .format(name))
        else:
            gaps.append(
                "{0}: absent -- forward projection kept sidecar-only, not established".format(
                    name))
    # target_price is never mapped into Nivesha; note whether one was supplied (sidecar-only).
    base_case = packet.case("base")
    if base_case is not None:
        for inp in base_case.inputs:
            if inp.name == "target_price" and inp.present:
                gaps.append(
                    "target_price: present as labelled INPUT -- kept sidecar-only, never "
                    "laundered into a Nivesha price field")

    candidate = CandidateInput(**values)

    domain = ""
    bear_p = base_p = bull_p = None
    catalyst_window = None
    notes = ""
    if base_inputs is not None:
        domain = base_inputs.domain
        bear_p = base_inputs.bear_probability
        base_p = base_inputs.base_probability
        bull_p = base_inputs.bull_probability
        catalyst_window = base_inputs.catalyst_timing_window
        notes = base_inputs.notes

    diligence_inputs = DiligenceInputs(
        domain=domain, candidates=(candidate,),
        bear_probability=bear_p, base_probability=base_p, bull_probability=bull_p,
        catalyst_timing_window=catalyst_window, notes=notes)

    mapping = ForwardSidecarMapping(
        ticker=ticker,
        mapped_fields=tuple(mapped),
        gaps=_dedupe(gaps),
        preserved_data_gaps=tuple(packet.data_gaps),
        preserved_evidence_refs=_dedupe(
            list(packet.evidence_refs) + list(packet.source_refs)
            + list(packet.provenance_refs)),
        scenario_labels=packet.scenario_labels(),
        note="forward adapter mapped INPUTS only; no thesis / strength / score / rank produced",
    )
    return diligence_inputs, mapping


def run_nivesha_thesis_on_forward_sidecar(
    opportunity_hypothesis: Any, packet: ForwardScenarioPacket, *,
    base_inputs: Optional[DiligenceInputs] = None, actor: str = "prometheus", now: float,
):
    """Operator / E2E convenience: adapt the forward packet, then run the ACCEPTED Nivesha
    ``generate_investment_thesis`` UNCHANGED over the adapted inputs.

    Returns ``(InvestmentThesis, ForwardSidecarMapping)``. The adapter itself still produces
    no thesis strength -- Nivesha reasons the (possibly limited / blocked) thesis from the
    honest inputs; insufficient inputs give Nivesha's honest LIMITED thesis, not a padded one.
    ``generate_investment_thesis`` is imported LAZILY so importing this module stays inert.
    """
    from prometheus.investment_thesis import generate_investment_thesis  # lazy: keep inert

    diligence_inputs, mapping = to_nivesha_forward_sidecar(packet, base_inputs=base_inputs)
    thesis = generate_investment_thesis(
        opportunity_hypothesis, diligence_inputs, actor=actor, now=now)
    return thesis, mapping
