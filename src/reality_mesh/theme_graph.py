"""The Theme / Value-Chain / Chokepoint Knowledge Graph (IMPLEMENTATION-021D-GRAPH).

The structured investment-intelligence MAP that powers the Universe Canvas + CosmosIQ
Capital. It is a **MAP, never a recommendation**. Nothing in this module confers any capital
standing on any company: a company appearing in the graph's Monitored Company Universe is a
MONITORED INPUT only -- a :class:`~reality_mesh.capital_candidate.CapitalCandidate` is created
EXCLUSIVELY by the 020A publish path (provenance + signals + hypothesis + diligence + DQ), and
membership in this graph is not part of that lineage.

Discipline baked into the shape (identical spirit to the 012 handoff models):

* **A MAP, not a rating.** There is NO buy / sell / hold / order / trade / broker field and NO
  numeric score / rank / rating field on ANY model here -- every model is
  ``assert_no_trade_fields``-clean. Roles are MAP roles (``beneficiary`` / ``supplier`` /
  ``customer`` / ``enabler``), never a verdict; severities / windows are qualitative labels.
* **Every company is labelled.** A :class:`CompanyUniverseNode` always carries the exact
  monitored label :data:`MONITORED_LABEL` -- "Monitored Company Universe -- Not a Capital
  Candidate unless the pipeline publishes it." Real tickers are fine as *monitored inputs*;
  they are NEVER recommendations.
* **Frozen + validated + referentially whole.** Every model is a frozen dataclass validated on
  construction; a :class:`ThemeGraph` rejects any dangling reference (every ref must resolve).

The celestial hierarchy each model maps to (BRAND_NOMENCLATURE):

    Universe        = the full CosmosIQ intelligence space (the whole graph)
    Galaxy          = Mega Theme       -> :class:`MegaTheme`
    Milky Way       = Theme            -> :class:`Theme`
    Solar System    = Value Chain      -> :class:`ValueChain`
    Star            = Bottleneck / Chokepoint -> :class:`Bottleneck` / :class:`Chokepoint`
    Planet          = Company          -> :class:`CompanyUniverseNode`
    Moon            = Supplier/Customer/Dependency -> :class:`SupplierDependency`
    Comet           = Catalyst         -> :class:`CatalystNode`
    Black Hole      = Major Risk / Red-Team Hazard -> :class:`RiskNode`
    Nebula          = Emerging Weak Signal -> :class:`WeakSignalNode`

Deterministic, stdlib-only, Python 3.9, OFFLINE. No network on import; no scheduler / broker;
no wall-clock. Nothing here is imported by the default product pages -- the graph is opt-in
reference data and never auto-injects a ticker into the empty-store UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import ClassVar, Dict, Tuple

from .validation import assert_no_trade_fields


# --------------------------------------------------------------------------- #
# The exact monitored label -- carried by EVERY company node, verbatim.         #
# --------------------------------------------------------------------------- #
MONITORED_LABEL: str = (
    "Monitored Company Universe -- Not a Capital Candidate unless the pipeline publishes it."
)

# Closed MAP-role vocabulary (a placement on the map, NOT a rating or a verdict).
ROLE_LABELS: Tuple[str, ...] = ("beneficiary", "supplier", "customer", "enabler")

# Closed dependency-edge (moon) kinds.
DEPENDENCY_TYPES: Tuple[str, ...] = ("supplier", "customer", "dependency")

# Qualitative risk severity labels (a label, never a number).
SEVERITY_LABELS: Tuple[str, ...] = ("minor", "moderate", "major", "severe", "unknown")

# Qualitative catalyst-window labels (a label, never a date/number).
WINDOW_LABELS: Tuple[str, ...] = (
    "near_term", "mid_term", "long_term", "recurring", "event_driven", "unknown",
)


def _require_id(obj, name: str) -> None:
    value = getattr(obj, name, "")
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(
            "{0}.{1} is a required id and must be non-empty".format(type(obj).__name__, name))


def _require_in(obj, name: str, vocab: Tuple[str, ...]) -> None:
    value = getattr(obj, name, "")
    if value not in vocab:
        raise ValueError(
            "{0}.{1}: invalid label {2!r} (allowed: {3})".format(
                type(obj).__name__, name, value, list(vocab)))


# --------------------------------------------------------------------------- #
# Galaxy = Mega Theme                                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MegaTheme:
    """Galaxy -- a Mega Theme (NOT a generic domain). The top organising lens of the map."""
    CELESTIAL: ClassVar[str] = "galaxy"
    mega_theme_id: str = ""
    name: str = ""
    thesis: str = ""
    data_sources_needed: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_id(self, "mega_theme_id")


# --------------------------------------------------------------------------- #
# Milky Way = Theme                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Theme:
    """Milky Way -- a Theme within a Mega Theme."""
    CELESTIAL: ClassVar[str] = "milky_way"
    theme_id: str = ""
    name: str = ""
    mega_theme_ref: str = ""

    def __post_init__(self) -> None:
        _require_id(self, "theme_id")
        _require_id(self, "mega_theme_ref")


# --------------------------------------------------------------------------- #
# Solar System = Value Chain                                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ValueChain:
    """Solar System -- a Value Chain that realises a Theme, as ordered stages."""
    CELESTIAL: ClassVar[str] = "solar_system"
    value_chain_id: str = ""
    name: str = ""
    theme_ref: str = ""
    stages: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_id(self, "value_chain_id")
        _require_id(self, "theme_ref")


# --------------------------------------------------------------------------- #
# Star = Bottleneck / Chokepoint                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Bottleneck:
    """Star -- a bottleneck in a value chain (why the chain is constrained here)."""
    CELESTIAL: ClassVar[str] = "star"
    bottleneck_id: str = ""
    name: str = ""
    value_chain_ref: str = ""
    why_it_matters: str = ""
    is_chokepoint: bool = False

    def __post_init__(self) -> None:
        _require_id(self, "bottleneck_id")
        _require_id(self, "value_chain_ref")


@dataclass(frozen=True)
class Chokepoint(Bottleneck):
    """Star -- a CRITICAL bottleneck (a chokepoint). A Chokepoint is a critical Bottleneck."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_chokepoint", True)
        super().__post_init__()


# --------------------------------------------------------------------------- #
# Planet = Company / Capital Candidate (MONITORED input, NEVER a recommendation) #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompanyUniverseNode:
    """Planet -- a monitored company mapped to one or more bottlenecks.

    Membership here confers NO standing: this is a MONITORED INPUT, carrying the exact
    :data:`MONITORED_LABEL`. ``role_label`` is a MAP placement (``beneficiary`` / ``supplier``
    / ``customer`` / ``enabler``), never a rating. There is NO score / rank / verdict field.
    """
    CELESTIAL: ClassVar[str] = "planet"
    ticker: str = ""
    company_name: str = ""
    role_label: str = "beneficiary"
    linked_bottleneck_refs: Tuple[str, ...] = field(default_factory=tuple)
    monitored_label: str = MONITORED_LABEL

    def __post_init__(self) -> None:
        _require_id(self, "ticker")
        _require_in(self, "role_label", ROLE_LABELS)
        # The monitored label is NON-NEGOTIABLE: it is always exactly MONITORED_LABEL.
        if self.monitored_label != MONITORED_LABEL:
            raise ValueError(
                "CompanyUniverseNode.monitored_label must be exactly the monitored label")


# --------------------------------------------------------------------------- #
# Moon = Supplier / Customer / Dependency edge                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SupplierDependency:
    """Moon -- a directed supplier / customer / dependency edge between two companies."""
    CELESTIAL: ClassVar[str] = "moon"
    from_ticker: str = ""
    to_ticker: str = ""
    dependency_type: str = "dependency"

    def __post_init__(self) -> None:
        _require_id(self, "from_ticker")
        _require_id(self, "to_ticker")
        _require_in(self, "dependency_type", DEPENDENCY_TYPES)


# --------------------------------------------------------------------------- #
# Comet = Catalyst                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CatalystNode:
    """Comet -- a catalyst attached to a theme / mega theme / value chain / company."""
    CELESTIAL: ClassVar[str] = "comet"
    catalyst_id: str = ""
    description: str = ""
    theme_or_company_ref: str = ""
    expected_window_label: str = "unknown"

    def __post_init__(self) -> None:
        _require_id(self, "catalyst_id")
        _require_id(self, "theme_or_company_ref")
        _require_in(self, "expected_window_label", WINDOW_LABELS)


# --------------------------------------------------------------------------- #
# Black Hole = Major Risk / Red-Team Hazard                                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RiskNode:
    """Black Hole -- a major risk / red-team hazard attached to a theme or a company."""
    CELESTIAL: ClassVar[str] = "black_hole"
    risk_id: str = ""
    description: str = ""
    severity_label: str = "moderate"
    theme_or_company_ref: str = ""

    def __post_init__(self) -> None:
        _require_id(self, "risk_id")
        _require_id(self, "theme_or_company_ref")
        _require_in(self, "severity_label", SEVERITY_LABELS)


# --------------------------------------------------------------------------- #
# Nebula = Emerging Weak Signal / Early Theme Cloud                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WeakSignalNode:
    """Nebula -- an emerging weak signal / early theme cloud attached to a theme."""
    CELESTIAL: ClassVar[str] = "nebula"
    weak_signal_id: str = ""
    description: str = ""
    theme_or_company_ref: str = ""

    def __post_init__(self) -> None:
        _require_id(self, "weak_signal_id")
        _require_id(self, "theme_or_company_ref")


# The graph's node models (for registry / introspection). Every one is trade/score-clean.
GRAPH_MODELS = (
    MegaTheme, Theme, ValueChain, Bottleneck, Chokepoint, CompanyUniverseNode,
    SupplierDependency, CatalystNode, RiskNode, WeakSignalNode,
)


# --------------------------------------------------------------------------- #
# The whole map                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThemeGraph:
    """The whole investment-intelligence MAP -- referentially whole, never a recommendation.

    ``__post_init__`` enforces referential integrity: every reference (theme -> mega,
    value-chain -> theme, bottleneck -> value-chain, company -> bottleneck, dependency
    endpoints -> company, catalyst/risk/weak-signal -> some named entity) must resolve. A
    dangling reference raises ``ValueError``. Nothing here carries a buy/sell/order/score/rank
    field. There is no cycle requirement beyond the dependency edges (which may form any DAG or
    cycle -- a supplier can also be a customer).
    """
    mega_themes: Tuple[MegaTheme, ...] = field(default_factory=tuple)
    themes: Tuple[Theme, ...] = field(default_factory=tuple)
    value_chains: Tuple[ValueChain, ...] = field(default_factory=tuple)
    bottlenecks: Tuple[Bottleneck, ...] = field(default_factory=tuple)
    companies: Tuple[CompanyUniverseNode, ...] = field(default_factory=tuple)
    dependencies: Tuple[SupplierDependency, ...] = field(default_factory=tuple)
    catalysts: Tuple[CatalystNode, ...] = field(default_factory=tuple)
    risks: Tuple[RiskNode, ...] = field(default_factory=tuple)
    weak_signals: Tuple[WeakSignalNode, ...] = field(default_factory=tuple)

    # -- referential integrity -------------------------------------------------- #
    def __post_init__(self) -> None:
        mega_ids = {m.mega_theme_id for m in self.mega_themes}
        theme_ids = {t.theme_id for t in self.themes}
        chain_ids = {v.value_chain_id for v in self.value_chains}
        bottleneck_ids = {b.bottleneck_id for b in self.bottlenecks}
        tickers = {c.ticker for c in self.companies}
        # Any named entity a catalyst / risk / weak signal may attach to.
        any_ref = mega_ids | theme_ids | chain_ids | bottleneck_ids | tickers

        for t in self.themes:
            if t.mega_theme_ref not in mega_ids:
                self._dangle("Theme", t.theme_id, "mega_theme_ref", t.mega_theme_ref)
        for v in self.value_chains:
            if v.theme_ref not in theme_ids:
                self._dangle("ValueChain", v.value_chain_id, "theme_ref", v.theme_ref)
        for b in self.bottlenecks:
            if b.value_chain_ref not in chain_ids:
                self._dangle("Bottleneck", b.bottleneck_id, "value_chain_ref",
                             b.value_chain_ref)
        for c in self.companies:
            for ref in c.linked_bottleneck_refs:
                if ref not in bottleneck_ids:
                    self._dangle("CompanyUniverseNode", c.ticker, "linked_bottleneck_ref", ref)
        for d in self.dependencies:
            if d.from_ticker not in tickers:
                self._dangle("SupplierDependency", d.from_ticker, "from_ticker", d.from_ticker)
            if d.to_ticker not in tickers:
                self._dangle("SupplierDependency", d.to_ticker, "to_ticker", d.to_ticker)
        for cat in self.catalysts:
            if cat.theme_or_company_ref not in any_ref:
                self._dangle("CatalystNode", cat.catalyst_id, "theme_or_company_ref",
                             cat.theme_or_company_ref)
        for r in self.risks:
            if r.theme_or_company_ref not in any_ref:
                self._dangle("RiskNode", r.risk_id, "theme_or_company_ref",
                             r.theme_or_company_ref)
        for w in self.weak_signals:
            if w.theme_or_company_ref not in any_ref:
                self._dangle("WeakSignalNode", w.weak_signal_id, "theme_or_company_ref",
                             w.theme_or_company_ref)

    @staticmethod
    def _dangle(kind: str, ident: str, field_name: str, ref: str) -> None:
        raise ValueError(
            "ThemeGraph referential integrity: {0} {1!r} has a dangling {2} -> {3!r} "
            "(no such entity in the graph)".format(kind, ident, field_name, ref))

    # -- accessors -------------------------------------------------------------- #
    def themes_of(self, mega_theme_id: str) -> Tuple[Theme, ...]:
        return tuple(t for t in self.themes if t.mega_theme_ref == mega_theme_id)

    def value_chains_of(self, theme_id: str) -> Tuple[ValueChain, ...]:
        return tuple(v for v in self.value_chains if v.theme_ref == theme_id)

    def bottlenecks_of(self, value_chain_id: str) -> Tuple[Bottleneck, ...]:
        return tuple(b for b in self.bottlenecks if b.value_chain_ref == value_chain_id)

    def companies_of(self, bottleneck_id: str) -> Tuple[CompanyUniverseNode, ...]:
        return tuple(c for c in self.companies if bottleneck_id in c.linked_bottleneck_refs)

    def company(self, ticker: str) -> CompanyUniverseNode:
        for c in self.companies:
            if c.ticker == ticker:
                return c
        raise KeyError("no monitored company {0!r} in the graph".format(ticker))

    def dependencies_of(self, ticker: str) -> Tuple[SupplierDependency, ...]:
        return tuple(d for d in self.dependencies
                     if d.from_ticker == ticker or d.to_ticker == ticker)

    def catalysts_of(self, ref: str) -> Tuple[CatalystNode, ...]:
        return tuple(c for c in self.catalysts if c.theme_or_company_ref == ref)

    def risks_of(self, ref: str) -> Tuple[RiskNode, ...]:
        return tuple(r for r in self.risks if r.theme_or_company_ref == ref)

    def weak_signals_of(self, ref: str) -> Tuple[WeakSignalNode, ...]:
        return tuple(w for w in self.weak_signals if w.theme_or_company_ref == ref)

    @property
    def monitored_tickers(self) -> Tuple[str, ...]:
        """Every ticker in the Monitored Company Universe (order-stable)."""
        return tuple(c.ticker for c in self.companies)


# --------------------------------------------------------------------------- #
# Construction-time guard: NO model in the graph may carry a trade/score field.  #
# --------------------------------------------------------------------------- #
for _model in GRAPH_MODELS + (ThemeGraph,):
    assert_no_trade_fields(_model)
del _model


# =========================================================================== #
# The FIRST seed of the map -- the 10 Mega Themes.                              #
# =========================================================================== #
def build_seed_theme_graph() -> ThemeGraph:
    """Build the FIRST version of the map: the 10 Mega Themes with a reasonable seed.

    Each Mega Theme carries a few themes, value chains, bottlenecks / chokepoints, a small
    MONITORED company universe (real tickers as *monitored inputs*, clearly labelled and NEVER
    recommendations), known risks, known catalysts, and the data sources it would need.
    Accuracy + honest labelling over volume. Fully deterministic -- calling it twice returns
    equal graphs.
    """
    mega, themes, chains, bns, cos, deps, cats, risks, weaks = ([] for _ in range(9))

    def C(ticker, name, role, *bottleneck_ids):
        cos.append(CompanyUniverseNode(
            ticker=ticker, company_name=name, role_label=role,
            linked_bottleneck_refs=tuple(bottleneck_ids)))

    def M(mid, name, thesis, sources):
        mega.append(MegaTheme(mega_theme_id=mid, name=name, thesis=thesis,
                              data_sources_needed=tuple(sources)))

    def T(tid, name, mid):
        themes.append(Theme(theme_id=tid, name=name, mega_theme_ref=mid))

    def V(vid, name, tid, stages):
        chains.append(ValueChain(value_chain_id=vid, name=name, theme_ref=tid,
                                 stages=tuple(stages)))

    def B(bid, name, vid, why, choke=False):
        cls = Chokepoint if choke else Bottleneck
        bns.append(cls(bottleneck_id=bid, name=name, value_chain_ref=vid, why_it_matters=why))

    def D(a, b, kind):
        deps.append(SupplierDependency(from_ticker=a, to_ticker=b, dependency_type=kind))

    def CAT(cid, desc, ref, window):
        cats.append(CatalystNode(catalyst_id=cid, description=desc, theme_or_company_ref=ref,
                                 expected_window_label=window))

    def R(rid, desc, sev, ref):
        risks.append(RiskNode(risk_id=rid, description=desc, severity_label=sev,
                              theme_or_company_ref=ref))

    def W(wid, desc, ref):
        weaks.append(WeakSignalNode(weak_signal_id=wid, description=desc,
                                    theme_or_company_ref=ref))

    # 1 -- AI Infrastructure ------------------------------------------------- #
    M("ai-infrastructure", "AI Infrastructure",
      "Compute, memory, and interconnect capacity to train and serve frontier AI.",
      ["SEC filings", "hyperscaler capex disclosures", "foundry utilization", "HBM supply"])
    T("ai-accelerators", "AI Accelerators", "ai-infrastructure")
    T("ai-datacenter", "AI Data Center Build-out", "ai-infrastructure")
    V("vc-accelerator", "Accelerator supply chain", "ai-accelerators",
      ["EDA / IP", "advanced logic foundry", "HBM memory", "advanced packaging", "systems"])
    B("bn-advpkg", "Advanced packaging (CoWoS)", "vc-accelerator",
      "CoWoS/advanced-packaging capacity gates accelerator output.", choke=True)
    B("bn-hbm", "HBM memory supply", "vc-accelerator",
      "High-bandwidth memory is supply-constrained and co-designed with the accelerator.",
      choke=True)
    V("vc-dc", "Data-center capacity", "ai-datacenter",
      ["power", "land/shell", "cooling", "networking", "servers"])
    B("bn-dc-power", "Data-center power interconnection", "vc-dc",
      "Grid interconnection queue length gates when compute can be energized.", choke=True)
    C("NVDA", "NVIDIA", "beneficiary", "bn-advpkg", "bn-hbm")
    C("TSM", "TSMC", "enabler", "bn-advpkg")
    C("AVGO", "Broadcom", "beneficiary", "bn-advpkg")
    C("SSNLF", "Samsung Electronics", "supplier", "bn-hbm")
    C("SK_HYNIX", "SK hynix", "supplier", "bn-hbm")
    D("NVDA", "TSM", "supplier")
    D("NVDA", "SSNLF", "supplier")
    CAT("cat-ai-capex", "Hyperscaler raises annual AI capex guidance.",
        "ai-infrastructure", "recurring")
    R("risk-ai-digest", "AI capex digestion / over-build could stall order growth.",
      "major", "ai-infrastructure")
    R("risk-advpkg-single", "Advanced-packaging capacity concentrated in few suppliers.",
      "major", "bn-advpkg")
    W("weak-ai-inference", "Inference-at-the-edge demand emerging beyond training.",
      "ai-infrastructure")

    # 2 -- Physical AI ------------------------------------------------------- #
    M("physical-ai", "Physical AI",
      "AI embodied in the physical world: autonomy, sensing, and real-world actuation.",
      ["patent filings", "auto-OEM disclosures", "LiDAR shipments", "compute-per-vehicle"])
    T("autonomy", "Autonomous Systems", "physical-ai")
    V("vc-autonomy", "Autonomy stack", "autonomy",
      ["sensors", "compute", "models", "integration", "fleet"])
    B("bn-av-sensor", "Automotive-grade sensing & compute", "vc-autonomy",
      "Reliable, cost-viable sensing + on-vehicle compute gates deployment.", choke=True)
    C("TSLA", "Tesla", "beneficiary", "bn-av-sensor")
    C("MBLY", "Mobileye", "beneficiary", "bn-av-sensor")
    C("NVDA", "NVIDIA", "enabler", "bn-av-sensor")  # duplicate ticker is de-duped below
    D("MBLY", "TSM", "supplier")
    CAT("cat-av-reg", "Regulator expands driverless operating domains.",
        "physical-ai", "event_driven")
    R("risk-av-safety", "Safety incident triggers regulatory rollback.",
      "severe", "physical-ai")
    W("weak-humanoid", "Humanoid robotics pilots expanding in logistics.", "physical-ai")

    # 3 -- Power & Grid ------------------------------------------------------ #
    M("power-and-grid", "Power & Grid",
      "Electrification + AI load growth strain generation, transmission, and grid equipment.",
      ["utility IRPs", "interconnection queues", "transformer lead times", "PPA disclosures"])
    T("grid-equipment", "Grid Equipment", "power-and-grid")
    V("vc-grid", "Transmission & distribution", "grid-equipment",
      ["generation", "transformers", "switchgear", "transmission", "distribution"])
    B("bn-transformer", "Large power transformers", "vc-grid",
      "Multi-year transformer lead times bottleneck grid expansion.", choke=True)
    C("GEV", "GE Vernova", "beneficiary", "bn-transformer")
    C("ETN", "Eaton", "beneficiary", "bn-transformer")
    C("VRT", "Vertiv", "beneficiary", "bn-transformer")
    CAT("cat-grid-load", "Utility raises multi-year load-growth forecast on data centers.",
        "power-and-grid", "long_term")
    R("risk-grid-permit", "Permitting / siting delays stall transmission build.",
      "major", "power-and-grid")

    # 4 -- Optical Networking ----------------------------------------------- #
    M("optical-networking", "Optical Networking",
      "AI clusters need vast optical interconnect bandwidth inside and between data centers.",
      ["transceiver shipments", "switch silicon roadmaps", "hyperscaler optics RFQs"])
    T("optics", "Datacenter Optics", "optical-networking")
    V("vc-optics", "Optical interconnect", "optics",
      ["laser/PIC", "transceiver", "switch silicon", "systems"])
    B("bn-transceiver", "High-speed optical transceivers", "vc-optics",
      "800G/1.6T transceiver supply gates cluster interconnect scaling.", choke=True)
    C("COHR", "Coherent", "supplier", "bn-transceiver")
    C("LITE", "Lumentum", "supplier", "bn-transceiver")
    C("ANET", "Arista Networks", "beneficiary", "bn-transceiver")
    D("ANET", "COHR", "supplier")
    CAT("cat-optics-16t", "Hyperscalers begin 1.6T optics qualification.",
        "optical-networking", "mid_term")
    R("risk-optics-copper", "Co-packaged copper alternatives could slow optics attach.",
      "moderate", "optical-networking")

    # 5 -- Space & Defense --------------------------------------------------- #
    M("space-and-defense", "Space & Defense",
      "Reusable launch, proliferated LEO, and a re-armament cycle across allied budgets.",
      ["defense budget appropriations", "launch cadence", "satellite manifests"])
    T("space-launch", "Launch & Space Systems", "space-and-defense")
    V("vc-space", "Launch to on-orbit", "space-launch",
      ["propulsion", "launch", "satellite bus", "payload", "ground"])
    B("bn-launch", "Reliable low-cost launch cadence", "vc-space",
      "Launch cadence and cost gate the economics of proliferated constellations.", choke=True)
    C("RKLB", "Rocket Lab", "beneficiary", "bn-launch")
    C("LMT", "Lockheed Martin", "beneficiary", "bn-launch")
    CAT("cat-defense-budget", "Allied defense budgets ratified above trend.",
        "space-and-defense", "long_term")
    R("risk-space-launch-fail", "Launch failure grounds a vehicle for quarters.",
      "severe", "bn-launch")

    # 6 -- Nuclear / Energy Security ---------------------------------------- #
    M("nuclear-energy-security", "Nuclear / Energy Security",
      "Firm clean baseload -- SMRs, uranium fuel cycle, and life-extension -- for AI + grid.",
      ["NRC dockets", "uranium spot/term prices", "enrichment capacity", "PPA disclosures"])
    T("nuclear-fuel", "Nuclear Fuel Cycle", "nuclear-energy-security")
    V("vc-nuclear", "Fuel to power", "nuclear-fuel",
      ["mining", "conversion", "enrichment", "fabrication", "reactor"])
    B("bn-enrichment", "Enrichment / conversion capacity", "vc-nuclear",
      "Western enrichment/conversion capacity is scarce and slow to add.", choke=True)
    C("CCJ", "Cameco", "beneficiary", "bn-enrichment")
    C("OKLO", "Oklo", "beneficiary", "bn-enrichment")
    CAT("cat-smr-approval", "Regulator advances an SMR design certification.",
        "nuclear-energy-security", "long_term")
    R("risk-nuclear-fuel", "Fuel-supply disruption from geopolitics.",
      "major", "nuclear-energy-security")

    # 7 -- Cybersecurity ----------------------------------------------------- #
    M("cybersecurity", "Cybersecurity",
      "Attack surface and AI-enabled threats expand faster than defenses; platforms consolidate.",
      ["breach disclosures (8-K)", "CISA advisories", "customer counts", "NRR disclosures"])
    T("cyber-platform", "Security Platforms", "cybersecurity")
    V("vc-cyber", "Detect to respond", "cyber-platform",
      ["identity", "endpoint", "network", "cloud", "SOC/response"])
    B("bn-identity", "Identity & access as the new perimeter", "vc-cyber",
      "Identity is the primary attack path; consolidation favors platform owners.")
    C("CRWD", "CrowdStrike", "beneficiary", "bn-identity")
    C("PANW", "Palo Alto Networks", "beneficiary", "bn-identity")
    C("ZS", "Zscaler", "beneficiary", "bn-identity")
    CAT("cat-cyber-mandate", "New disclosure / zero-trust mandate raises spend.",
        "cybersecurity", "recurring")
    R("risk-cyber-outage", "A defender-caused outage dents platform trust.",
      "major", "cybersecurity")

    # 8 -- Healthcare AI ----------------------------------------------------- #
    M("healthcare-ai", "Healthcare AI",
      "AI in drug discovery, diagnostics, and clinical workflow -- gated by evidence + reimbursement.",
      ["FDA clearances", "clinical-trial registries", "CMS reimbursement", "payer coverage"])
    T("ai-diagnostics", "AI Diagnostics", "healthcare-ai")
    V("vc-dx", "Discovery to reimbursement", "ai-diagnostics",
      ["data", "model", "clinical validation", "regulatory", "reimbursement"])
    B("bn-reimbursement", "Reimbursement & regulatory clearance", "vc-dx",
      "FDA clearance + payer reimbursement gate real adoption of AI diagnostics.", choke=True)
    C("ISRG", "Intuitive Surgical", "beneficiary", "bn-reimbursement")
    C("TEM", "Tempus AI", "beneficiary", "bn-reimbursement")
    CAT("cat-fda-clearance", "FDA clears an AI diagnostic for a broad indication.",
        "healthcare-ai", "event_driven")
    R("risk-hc-reimburse", "Reimbursement denied / delayed for AI tools.",
      "major", "bn-reimbursement")

    # 9 -- Robotics / Automation -------------------------------------------- #
    M("robotics-automation", "Robotics / Automation",
      "Labor scarcity + reshoring drive factory, warehouse, and service automation.",
      ["industrial orders", "robot install base", "PMI", "capex disclosures"])
    T("industrial-automation", "Industrial Automation", "robotics-automation")
    V("vc-robotics", "Sense-plan-actuate", "industrial-automation",
      ["actuators", "controls", "vision", "software", "integration"])
    B("bn-actuation", "Precision actuation & motion control", "vc-robotics",
      "Precision actuation + controls is the hard, margin-rich layer of automation.")
    C("ABBN", "ABB", "beneficiary", "bn-actuation")
    C("ROK", "Rockwell Automation", "beneficiary", "bn-actuation")
    CAT("cat-reshoring", "Reshoring incentive package lifts automation orders.",
        "robotics-automation", "mid_term")
    R("risk-robo-cycle", "Industrial capex is cyclical; orders can air-pocket.",
      "moderate", "robotics-automation")

    # 10 -- Supply Chain Resilience ----------------------------------------- #
    M("supply-chain-resilience", "Supply Chain Resilience",
      "Reshoring, friend-shoring, and critical-materials security reshape industrial flows.",
      ["customs/trade data", "critical-materials pricing", "capex disclosures", "policy filings"])
    T("critical-materials", "Critical Materials", "supply-chain-resilience")
    V("vc-materials", "Mine to magnet", "critical-materials",
      ["mining", "refining", "separation", "components", "OEM"])
    B("bn-refining", "Rare-earth / critical-materials refining", "vc-materials",
      "Refining/separation capacity, not ore, is the true chokepoint.", choke=True)
    C("MP", "MP Materials", "beneficiary", "bn-refining")
    C("ALB", "Albemarle", "supplier", "bn-refining")
    CAT("cat-materials-policy", "Government funds domestic refining capacity.",
        "supply-chain-resilience", "long_term")
    R("risk-materials-export", "Export controls on a critical material disrupt supply.",
      "severe", "supply-chain-resilience")
    W("weak-friendshoring", "Friend-shoring shifting orders to allied suppliers.",
      "supply-chain-resilience")

    # De-duplicate company nodes by ticker (a ticker may appear under several mega themes;
    # keep the first mapping, merge its bottleneck links -- deterministic, order-stable).
    merged: Dict[str, CompanyUniverseNode] = {}
    order = []
    for c in cos:
        if c.ticker not in merged:
            merged[c.ticker] = c
            order.append(c.ticker)
        else:
            prev = merged[c.ticker]
            links = tuple(dict.fromkeys(prev.linked_bottleneck_refs + c.linked_bottleneck_refs))
            merged[c.ticker] = CompanyUniverseNode(
                ticker=prev.ticker, company_name=prev.company_name, role_label=prev.role_label,
                linked_bottleneck_refs=links)
    companies = tuple(merged[t] for t in order)

    return ThemeGraph(
        mega_themes=tuple(mega), themes=tuple(themes), value_chains=tuple(chains),
        bottlenecks=tuple(bns), companies=companies, dependencies=tuple(deps),
        catalysts=tuple(cats), risks=tuple(risks), weak_signals=tuple(weaks))
