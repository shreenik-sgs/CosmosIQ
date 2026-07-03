"""Nivesha-ready INPUT adapter (IMPLEMENTATION-011D).

Maps a :class:`~diligence_enrichment.models.DiligenceEnrichmentBundle` (produced by
011A/B/C) into the EXACT ``DiligenceInputs`` type Nivesha / Prometheus consumes -- and
NOTHING more. This adapter is an INPUT translator, deliberately dumb about investment
meaning:

* It creates **no** thesis, no thesis strength, no ``buy`` / ``sell`` / ``hold``, no
  ``score`` / ``rank`` / ``rating`` -- Nivesha alone reasons those, unchanged.
* It **fabricates nothing.** A Nivesha candidate field is populated only when the
  enrichment bundle (or an operator-supplied manual ``base_inputs``) genuinely carries
  the evidence. Every field Nivesha could use but no evidence supports stays at Nivesha's
  own honest ABSENT representation (``None`` / the dataclass default) and is recorded as
  an explicit adapter GAP -- never a fabricated strong value to slip past a gate.
* It **preserves source authority.** ``DiligenceInputs`` / ``CandidateInput`` are plain
  frozen dataclasses of bare values -- they carry no provenance slot -- so the authority,
  claim status and ``source_refs`` for every mapped value travel ALONGSIDE the inputs in
  the :class:`NiveshaInputMapping` sidecar, never laundered into the bare inputs. A
  manual / analyst datum stays ``manual`` (never canonical); a company statement stays
  ``company_claim`` (never ``verified_fact``).
* It **bypasses no gate.** If the evidence is thin the adapted inputs are thin, so
  Nivesha's existing gates fire honestly (undetermined asymmetry, no technical
  confirmation, no credible winner -> a limited / blocked thesis). The adapter never pads
  inputs to force a stronger thesis.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Imports the Nivesha input TYPES only
(``prometheus.diligence_inputs``) -- it never imports or modifies Nivesha's reasoning.
The optional :func:`run_nivesha_thesis_on_enrichment` helper calls the accepted
``generate_investment_thesis`` UNCHANGED so an operator / E2E path exists; the helper
imports it lazily so importing this module stays inert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from prometheus.diligence_inputs import CandidateInput, DiligenceInputs

from .models import DiligenceEnrichmentBundle
from .source_contract import ClaimStatus, assert_manual_not_canonical


# --------------------------------------------------------------------------- #
# Provenance sidecar: what the bare DiligenceInputs cannot carry.             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MappedField:
    """One Nivesha candidate field populated from evidence, WITH its provenance.

    ``candidate_field`` is the ``CandidateInput`` attribute that received the value;
    ``authority`` / ``claim_status`` / ``source_refs`` are carried verbatim from the
    enrichment datum (or stamped ``manual`` for an operator-supplied ``base_inputs``
    value). This is provenance, never a score / ranking key.
    """
    candidate_field: str = ""
    value: Optional[object] = None
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


@dataclass(frozen=True)
class NiveshaInputMapping:
    """The provenance + gap sidecar returned next to the adapted ``DiligenceInputs``.

    ``mapped_fields`` records every candidate field the adapter populated and where it
    came from (authority / claim status / source_refs). ``gaps`` lists every Nivesha input
    that stayed ABSENT for want of evidence -- the honest insufficient representation, not
    a fabricated value. ``preserved_data_gaps`` / ``preserved_source_refs`` carry the
    bundle's own gaps + refs through unchanged. There is NO thesis, strength, score, rank
    or buy / sell / hold anywhere here.
    """
    ticker: str = ""
    mapped_fields: Tuple[MappedField, ...] = field(default_factory=tuple)
    gaps: Tuple[str, ...] = field(default_factory=tuple)
    preserved_data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    preserved_source_refs: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


# Nivesha candidate fields the adapter tries to establish from evidence. Any that stay
# absent (neither enrichment nor operator base supplies them) become an explicit gap --
# these are exactly the inputs Nivesha's gauntlet materially reasons over.
_FINANCIAL_FIELDS = (
    "current_price", "shares_outstanding", "revenue", "prior_revenue",
    "gross_margin", "prior_gross_margin", "operating_margin", "cash", "debt",
)
_ASYMMETRY_FIELDS = ("bear_price", "base_price", "bull_price")
_TECHNICAL_FIELDS = (
    "ema9", "ema20", "ema50", "ema200", "ema_slopes_up",
    "breakout_level", "invalidation_level", "price_above_breakout",
    "volume_recent", "volume_avg",
)
_CAPITAL_STRUCTURE_FIELDS = (
    "dilution_risk", "shelf_registration", "atm_facility", "convertible_debt",
)
# Fields whose absence we surface as an honest adapter gap (grouped by what breaks).
_GAP_TRACKED = {
    "value_chain_role": "winner mapping (exposure) needs a value-chain role",
    "tier": "winner mapping needs the value-chain tier",
    "current_price": "asymmetry / valuation needs the current price",
    "revenue": "financial inflection needs revenue",
    "prior_revenue": "financial inflection needs prior revenue (growth)",
    "gross_margin": "financial inflection needs gross margin",
    "prior_gross_margin": "financial inflection needs prior gross margin (expansion)",
    "bear_price": "asymmetry needs a bear-case anchor",
    "bull_price": "asymmetry needs a bull-case anchor",
    "ema9": "technical confirmation needs EMA structure",
    "volume_recent": "technical confirmation needs recent volume",
    "dilution_risk": "capital-structure / dilution not established from evidence",
}


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _base_candidate(base_inputs, ticker: str):
    """Pick the operator-supplied manual candidate for ``ticker`` (or the first), if any."""
    if base_inputs is None or not base_inputs.candidates:
        return None
    up = (ticker or "").upper()
    for c in base_inputs.candidates:
        if (c.ticker or "").upper() == up:
            return c
    return base_inputs.candidates[0]


def _market_evidence_map(bundle: DiligenceEnrichmentBundle):
    """(candidate_field, EnrichmentValue) pairs for the financial magnitudes the market
    snapshot genuinely carries. Only ``present`` values ever overlay a candidate field."""
    m = bundle.market
    return (
        ("current_price", m.price),
        ("shares_outstanding", m.shares_outstanding),
        ("revenue", m.latest_revenue),
        ("gross_margin", m.gross_margin),
        ("operating_margin", m.op_margin),
        ("cash", m.cash),
        ("debt", m.debt),
    )


def _value_chain_role_evidence(bundle: DiligenceEnrichmentBundle):
    """Return (role, authority, claim_status, source_refs) if the value-chain evidence
    explicitly places this ticker in a labelled layer, else None. This is evidence-backed
    (the deck named the company in that layer) -- it is not an inferred/invented role."""
    vc = bundle.value_chain
    if not vc.present:
        return None
    up = (bundle.ticker or "").upper()
    for layer in vc.layers:
        companies = tuple((c or "").upper() for c in layer.companies)
        if up and up in companies and layer.label:
            return (
                layer.label,
                layer.authority or vc.authority,
                layer.claim_status or vc.claim_status,
                tuple(layer.source_refs) or tuple(vc.source_refs),
            )
    return None


def to_nivesha_diligence_inputs(
    enrichment_bundle: DiligenceEnrichmentBundle, *,
    slice_result: Any = None,
    base_inputs: Optional[DiligenceInputs] = None,
) -> Tuple[DiligenceInputs, NiveshaInputMapping]:
    """Map an enrichment bundle into Nivesha-compatible ``DiligenceInputs``.

    Evidence-backed candidate fields (financial magnitudes from the market snapshot, the
    value-chain role from value-chain evidence, the company name from the profile) are
    populated and their authority / claim-status / source_refs recorded in the returned
    :class:`NiveshaInputMapping`. Operator-supplied manual fields from ``base_inputs`` (the
    scenario prices, EMAs, capital-structure flags Nivesha needs that enrichment cannot
    supply) pass through stamped ``manual`` -- never promoted to canonical. Every Nivesha
    input that stays absent is recorded as an honest GAP; NOTHING is fabricated. Source
    authority ordering is preserved: an enrichment datum overlays a manual base value for
    the same field (evidence outranks manual), never the reverse.

    Returns ``(DiligenceInputs, NiveshaInputMapping)``. The adapter produces no thesis,
    strength, score, rank or buy / sell / hold.
    """
    b = enrichment_bundle
    ticker = (b.ticker or "").strip().upper()
    base_cand = _base_candidate(base_inputs, ticker)

    # Start from the operator's manual candidate (if any); everything else defaults to
    # Nivesha's own absent representation (None / dataclass default) -- never invented.
    values: Dict[str, Any] = {}
    if base_cand is not None:
        for f in CandidateInput.__dataclass_fields__:
            values[f] = getattr(base_cand, f)

    mapped: List[MappedField] = []
    gaps: List[str] = []

    def record_base(field_name: str) -> None:
        """A field carried over from the operator's manual base_inputs -> stamp manual."""
        val = values.get(field_name)
        if val in (None, "", 0, 0.0, False):
            return
        assert_manual_not_canonical("manual", ClaimStatus.MANUAL)
        mapped.append(MappedField(
            candidate_field=field_name, value=val, authority="manual",
            claim_status=ClaimStatus.MANUAL,
            source_refs=tuple(base_inputs.notes and (base_inputs.notes,) or ()),
            note="operator-supplied manual diligence input (not canonical)"))

    values["ticker"] = ticker

    # --- 1. company name (profile evidence) ---------------------------------- #
    name_ev = b.profile.company_name
    if name_ev.present:
        values["name"] = str(name_ev.value)
        mapped.append(MappedField(
            candidate_field="name", value=values["name"], authority=name_ev.authority,
            claim_status=name_ev.claim_status, source_refs=tuple(name_ev.source_refs)))
    elif not values.get("name"):
        values["name"] = ticker

    # --- 2. financial magnitudes (market snapshot evidence, authority-stamped) - #
    evidence_fields = set()
    for cand_field, ev in _market_evidence_map(b):
        if ev.present:
            val = _float_or_none(ev.value)
            if val is None:
                continue
            # A manual / analyst datum must never masquerade as canonical.
            assert_manual_not_canonical(ev.authority, ev.claim_status)
            values[cand_field] = val
            evidence_fields.add(cand_field)
            mapped.append(MappedField(
                candidate_field=cand_field, value=val, authority=ev.authority,
                claim_status=ev.claim_status, source_refs=tuple(ev.source_refs),
                note=ev.note))

    # --- 3. value-chain role (value-chain evidence) -------------------------- #
    vc_role = _value_chain_role_evidence(b)
    if vc_role is not None:
        role, authority, claim_status, refs = vc_role
        values["value_chain_role"] = role
        evidence_fields.add("value_chain_role")
        assert_manual_not_canonical(authority, claim_status)
        mapped.append(MappedField(
            candidate_field="value_chain_role", value=role, authority=authority,
            claim_status=claim_status, source_refs=refs))

    # --- 4. operator base fields that Nivesha needs but enrichment cannot give - #
    if base_cand is not None:
        for f in (_ASYMMETRY_FIELDS + _TECHNICAL_FIELDS + _CAPITAL_STRUCTURE_FIELDS
                  + ("prior_revenue", "prior_gross_margin", "tier", "guidance",
                     "value_chain_role")):
            if f in evidence_fields:
                continue  # evidence already established it (evidence outranks manual)
            record_base(f)

    # --- 5. honest gaps: every tracked input that stayed absent -------------- #
    for f, why in _GAP_TRACKED.items():
        present = False
        val = values.get(f)
        if f == "value_chain_role":
            present = bool(val)
        elif f == "dilution_risk":
            present = bool(val) and val != "none"  # 'none' default is not established
        elif f == "tier":
            present = bool(val)
        else:
            present = val not in (None, "")
        if not present:
            gaps.append("{0}: absent -- {1}".format(f, why))

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

    # --- preserve the bundle's own provenance ------------------------------- #
    preserved_refs: List[str] = list(b.provenance_refs)
    for area in (b.profile, b.market, b.tam_estimate, b.value_chain,
                 b.bottleneck, b.ir, b.leadership):
        preserved_refs.extend(getattr(area, "source_refs", ()) or ())
    preserved_refs = list(dict.fromkeys(r for r in preserved_refs if r))

    note = "adapter mapped INPUTS only; no thesis / strength / score / rank produced"
    if slice_result is not None:
        subj = getattr(slice_result, "subject", "") or ""
        if subj:
            note += "; slice subject {0}".format(subj)
        for g in getattr(slice_result, "data_gaps", ()) or ():
            # slice data gaps are (stage, reason) tuples -- keep them visible.
            gaps.append("slice: {0}".format(g[1] if isinstance(g, tuple) and len(g) > 1 else g))

    mapping = NiveshaInputMapping(
        ticker=ticker,
        mapped_fields=tuple(mapped),
        gaps=tuple(dict.fromkeys(gaps)),
        preserved_data_gaps=tuple(b.data_gaps),
        preserved_source_refs=tuple(preserved_refs),
        note=note)
    return diligence_inputs, mapping


def run_nivesha_thesis_on_enrichment(
    opportunity_hypothesis: Any, enrichment_bundle: DiligenceEnrichmentBundle, *,
    base_inputs: Optional[DiligenceInputs] = None, slice_result: Any = None,
    actor: str = "prometheus", now: float,
):
    """Operator / E2E convenience: adapt the bundle, then call the ACCEPTED Nivesha
    ``generate_investment_thesis`` UNCHANGED over the adapted inputs.

    Returns ``(InvestmentThesis, NiveshaInputMapping)``. The adapter itself still produces
    no thesis strength -- Nivesha reasons the (possibly limited / blocked) thesis from the
    honest inputs. ``generate_investment_thesis`` is imported lazily so importing this
    module stays inert and offline.
    """
    from prometheus.investment_thesis import generate_investment_thesis  # lazy: keep inert

    diligence_inputs, mapping = to_nivesha_diligence_inputs(
        enrichment_bundle, slice_result=slice_result, base_inputs=base_inputs)
    thesis = generate_investment_thesis(
        opportunity_hypothesis, diligence_inputs, actor=actor, now=now)
    return thesis, mapping


# Migrated (English) name for the investment-diligence input-mapping sidecar. The legacy
# ``NiveshaInputMapping`` name is retained as the definition; new code should use this alias.
InvestmentDiligenceInputMapping = NiveshaInputMapping
