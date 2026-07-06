"""Pure view-model for the Theme / Value-Chain / Chokepoint graph (IMPLEMENTATION-021D-GRAPH).

Renders the CosmosIQ celestial hierarchy of a :class:`~reality_mesh.theme_graph.ThemeGraph` as
a structured view-model + a small text/HTML tree, so the Universe Canvas can render the graph
hierarchy at the data / view-model level WITHOUT touching ``universe_ui``. It shows the MAP
only:

    Galaxy (Mega Theme) -> Milky Way (Theme) -> Solar System (Value Chain)
      -> Star (Bottleneck / Chokepoint) -> Planet (monitored company)
      -> Moon (dependency) -> Comet (catalyst) -> Black Hole (risk) -> Nebula (weak signal)

HARD DISCIPLINE (identical spirit to the 016 cockpits):

* **A MAP, never a recommendation.** No buy / sell / order control, no ``<button>`` / ``<form>``,
  no score / rank / rating -- the render carries none of these tokens.
* **Every company is labelled.** Each planet row carries the exact monitored label
  (:data:`~reality_mesh.theme_graph.MONITORED_LABEL`) -- a monitored input, not a candidate.

Deterministic, stdlib-only, Python 3.9, OFFLINE. Importing this module pulls in NO network /
scheduler / broker, and it is NOT imported by the default product pages -- the graph is opt-in.
"""

from __future__ import annotations

from typing import Any, Dict, List

from reality_mesh.theme_graph import MONITORED_LABEL, ThemeGraph, build_seed_theme_graph

# Celestial body -> (display name, meaning). The permanent BRAND_NOMENCLATURE mapping.
CELESTIAL_DISPLAY = {
    "galaxy": ("Galaxy", "Mega Theme"),
    "milky_way": ("Milky Way", "Theme"),
    "solar_system": ("Solar System", "Value Chain"),
    "star": ("Star", "Bottleneck / Chokepoint"),
    "planet": ("Planet", "Company"),
    "moon": ("Moon", "Supplier / Customer / Dependency"),
    "comet": ("Comet", "Catalyst"),
    "black_hole": ("Black Hole", "Major Risk / Red-Team Hazard"),
    "nebula": ("Nebula", "Emerging Weak Signal"),
}


def hierarchy_view_model(graph: ThemeGraph) -> Dict[str, Any]:
    """Build a plain, nested dict view-model of the celestial hierarchy (no rendering).

    The structure the Universe Canvas can consume directly: a ``universe`` root whose
    ``galaxies`` are the mega themes, each nesting milky-ways (themes) -> solar-systems
    (value chains) -> stars (bottlenecks) -> planets (monitored companies), plus each
    planet's moons (dependencies), and comets (catalysts) / black-holes (risks) / nebulae
    (weak signals) attached at each level. Every planet carries the monitored label.
    """
    def catalysts(ref: str) -> List[Dict[str, str]]:
        return [{"celestial": "comet", "catalyst_id": c.catalyst_id,
                 "description": c.description, "window": c.expected_window_label}
                for c in graph.catalysts_of(ref)]

    def risks(ref: str) -> List[Dict[str, str]]:
        return [{"celestial": "black_hole", "risk_id": r.risk_id,
                 "description": r.description, "severity": r.severity_label}
                for r in graph.risks_of(ref)]

    def weak_signals(ref: str) -> List[Dict[str, str]]:
        return [{"celestial": "nebula", "weak_signal_id": w.weak_signal_id,
                 "description": w.description}
                for w in graph.weak_signals_of(ref)]

    def planet(node) -> Dict[str, Any]:
        return {
            "celestial": "planet",
            "ticker": node.ticker,
            "company_name": node.company_name,
            "role_label": node.role_label,
            "monitored_label": node.monitored_label,
            "moons": [
                {"celestial": "moon", "from_ticker": d.from_ticker,
                 "to_ticker": d.to_ticker, "dependency_type": d.dependency_type}
                for d in graph.dependencies_of(node.ticker)
            ],
            "comets": catalysts(node.ticker),
            "black_holes": risks(node.ticker),
        }

    galaxies = []
    for mega in graph.mega_themes:
        milky_ways = []
        for theme in graph.themes_of(mega.mega_theme_id):
            solar_systems = []
            for chain in graph.value_chains_of(theme.theme_id):
                stars = []
                for bn in graph.bottlenecks_of(chain.value_chain_id):
                    stars.append({
                        "celestial": "star",
                        "bottleneck_id": bn.bottleneck_id,
                        "name": bn.name,
                        "is_chokepoint": bn.is_chokepoint,
                        "why_it_matters": bn.why_it_matters,
                        "planets": [planet(c) for c in graph.companies_of(bn.bottleneck_id)],
                        "comets": catalysts(bn.bottleneck_id),
                        "black_holes": risks(bn.bottleneck_id),
                    })
                solar_systems.append({
                    "celestial": "solar_system",
                    "value_chain_id": chain.value_chain_id,
                    "name": chain.name,
                    "stages": list(chain.stages),
                    "stars": stars,
                })
            milky_ways.append({
                "celestial": "milky_way",
                "theme_id": theme.theme_id,
                "name": theme.name,
                "solar_systems": solar_systems,
                "comets": catalysts(theme.theme_id),
                "black_holes": risks(theme.theme_id),
                "nebulae": weak_signals(theme.theme_id),
            })
        galaxies.append({
            "celestial": "galaxy",
            "mega_theme_id": mega.mega_theme_id,
            "name": mega.name,
            "thesis": mega.thesis,
            "data_sources_needed": list(mega.data_sources_needed),
            "milky_ways": milky_ways,
            "comets": catalysts(mega.mega_theme_id),
            "black_holes": risks(mega.mega_theme_id),
            "nebulae": weak_signals(mega.mega_theme_id),
        })

    return {
        "universe": "CosmosIQ intelligence space",
        "monitored_label": MONITORED_LABEL,
        "disclaimer": ("This is a MAP, not investment advice. Graph membership confers no "
                       "capital standing; a company becomes a Capital Candidate only when the "
                       "pipeline publishes it with full evidence lineage."),
        "galaxies": galaxies,
    }


def _label(celestial: str) -> str:
    name, meaning = CELESTIAL_DISPLAY[celestial]
    return "{0} ({1})".format(name, meaning)


def render_graph_hierarchy(graph: ThemeGraph) -> str:
    """Render the celestial hierarchy of ``graph`` as an indented text tree.

    Every celestial level is labelled with its display name + meaning (e.g. "Galaxy (Mega
    Theme): AI Infrastructure"); every monitored company carries the monitored label. The
    output contains NO trade affordance and NO score / rank -- it is a MAP view only.
    """
    vm = hierarchy_view_model(graph)
    lines: List[str] = []
    lines.append("Universe: {0}".format(vm["universe"]))
    lines.append("Note: {0}".format(vm["disclaimer"]))
    ind = "  "

    def emit_catalysts(items, depth):
        for c in items:
            lines.append("{0}{1}: {2} [{3}]".format(
                ind * depth, _label("comet"), c["description"], c["window"]))

    def emit_risks(items, depth):
        for r in items:
            lines.append("{0}{1}: {2} [severity: {3}]".format(
                ind * depth, _label("black_hole"), r["description"], r["severity"]))

    def emit_nebulae(items, depth):
        for w in items:
            lines.append("{0}{1}: {2}".format(ind * depth, _label("nebula"), w["description"]))

    for g in vm["galaxies"]:
        lines.append("{0}: {1}".format(_label("galaxy"), g["name"]))
        emit_catalysts(g["comets"], 1)
        emit_risks(g["black_holes"], 1)
        emit_nebulae(g["nebulae"], 1)
        for mw in g["milky_ways"]:
            lines.append("{0}{1}: {2}".format(ind, _label("milky_way"), mw["name"]))
            emit_nebulae(mw["nebulae"], 2)
            for ss in mw["solar_systems"]:
                lines.append("{0}{1}: {2} [stages: {3}]".format(
                    ind * 2, _label("solar_system"), ss["name"], " -> ".join(ss["stages"])))
                for st in ss["stars"]:
                    kind = "Chokepoint" if st["is_chokepoint"] else "Bottleneck"
                    lines.append("{0}{1}: {2} -- {3}".format(
                        ind * 3, _label("star"), st["name"], kind))
                    for p in st["planets"]:
                        lines.append("{0}{1}: {2} ({3}) -- role: {4}".format(
                            ind * 4, _label("planet"), p["ticker"], p["company_name"],
                            p["role_label"]))
                        lines.append("{0}{1}".format(ind * 5, p["monitored_label"]))
                        for m in p["moons"]:
                            lines.append("{0}{1}: {2} -> {3} [{4}]".format(
                                ind * 5, _label("moon"), m["from_ticker"], m["to_ticker"],
                                m["dependency_type"]))
    return "\n".join(lines) + "\n"
