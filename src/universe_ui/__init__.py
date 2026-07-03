"""Universe UI -- CosmosIQ "Universe Canvas" static command-center (010A).

A runnable, LOCAL, static-HTML/CSS product UI over the existing EIOS pipeline. It is
a pure READ-ONLY PROJECTION and presentation layer:

* It generates seven cross-linked static pages (Economic Universe / Galaxy / Solar
  System / Bottleneck Star / IREN Cockpit / CIO Dashboard / Data Quality) with a
  cosmic command-center theme and navigation-only JavaScript.
* It computes NO new score, ranking, master score, or alpha number. CIO buckets come
  only from EXISTING pipeline statuses; visual object SIZE encodes economic magnitude
  as a bounded, purely-visual formatter that feeds no ranking.
* It reuses the ACCEPTED cockpit renderer for the one real candidate (IREN) and the
  ACCEPTED evidence-alpha slice for its statuses; everything else is clearly-labelled
  DEMO terrain.
* No network, no live data, no scheduler, no broker automation, no order affordance.
"""

from __future__ import annotations

from .app import build_universe_app

__all__ = ["build_universe_app"]
