"""The assistant output guardrails (PROD-LIVE-3) -- the mandatory label + action-directive filter.

The LLM Research Assistant is a SUMMARIZER / ANALYST, never an advisor. Two guardrails make
that impossible to violate even though the model output is free-form:

* :data:`AI_LABEL` -- the verbatim, unmissable tag every assistant result carries. It states, in
  plain English, that the output is AI-generated, is NOT evidence, is NOT a recommendation, and
  must be verified against cited sources.
* :func:`filter_action_directives` -- a POST-FILTER over the raw model text. It reuses the 020D
  :data:`reality_mesh.alerts.FORBIDDEN_ALERT_PHRASES` PLUS a word-boundary ``buy`` / ``sell`` /
  ``order`` sweep; ANY action-directive phrase is REPLACED with :data:`ACTION_REMOVED` so the
  returned / rendered text can never carry a buy / sell / order instruction. This keeps the repo
  trade-affordance guardrail scans clean even though the LLM output is free-form.

The filter is a SINGLE left-to-right ``re.sub`` pass: the regex engine never re-scans the text it
just inserted, so the replacement marker (which itself names ``buy/sell`` in prose) is never
re-matched. Longer forbidden PHRASES are listed before the bare word-boundary alternative, so
``strong buy`` collapses to one marker rather than leaking a bare ``buy``.

Stdlib-only, Python 3.9, deterministic, OFFLINE. Importing this module touches no network.
"""

from __future__ import annotations

import re

# Reuse the 020D forbidden action-language set (never re-defined here -- one source of truth).
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES

__all__ = [
    "AI_LABEL",
    "ACTION_REMOVED",
    "filter_action_directives",
    "contains_action_directive",
]

# The VERBATIM, unmissable tag every assistant result carries (returned AND rendered).
AI_LABEL = ("AI-generated — not evidence, not a recommendation. "
            "Verify against cited sources.")

# The replacement injected wherever an action directive is found in the model output. It names
# what was removed in plain English; the single-pass sub never re-scans it, so it is inert.
ACTION_REMOVED = (
    "[action directive removed — CosmosIQ issues no buy/sell instructions]")

# The combined action-directive matcher: every 020D forbidden PHRASE (longest first, so a
# multi-word phrase wins over the bare word-boundary alternative) + a word-boundary buy/sell/
# order sweep. Case-insensitive; a single re.sub pass replaces each match with ACTION_REMOVED.
_ACTION_DIRECTIVE_RE = re.compile(
    "|".join(
        [re.escape(phrase) for phrase in sorted(FORBIDDEN_ALERT_PHRASES,
                                                 key=len, reverse=True)]
        + [r"\b(?:buy|sell|order)\b"]),
    re.IGNORECASE)


def filter_action_directives(text: object) -> str:
    """Replace every action-directive phrase in ``text`` with :data:`ACTION_REMOVED`.

    One deterministic left-to-right pass: a forbidden phrase (``strong buy`` / ``submit order``
    / ``buy now`` ...) or a bare word-boundary ``buy`` / ``sell`` / ``order`` becomes the inert
    removal marker. The result therefore carries NO 020D forbidden phrase and no bare buy / sell
    / order instruction -- the assistant can never render a trade directive.
    """
    return _ACTION_DIRECTIVE_RE.sub(ACTION_REMOVED, str(text if text is not None else ""))


def contains_action_directive(text: object) -> bool:
    """True iff ``text`` still carries an action directive (a guard for tests / callers)."""
    return bool(_ACTION_DIRECTIVE_RE.search(str(text if text is not None else "")))
