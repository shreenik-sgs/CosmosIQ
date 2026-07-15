"""EDGE-ONLY AI suggestions of EMERGING themes / tickers (UNIVERSE-DISCOVERY UD-2).

UD-1 does the EVIDENCE-driven half of universe discovery (real screener rows + real SEC filings,
inside the deterministic engine). UD-2 does the SPECULATIVE half: it asks the EXISTING isolated AI
Research Assistant to PROPOSE emerging investment THEMES -- and, per theme, CANDIDATE TICKERS -- that
the SEC / FMP taxonomies may not classify yet. These are LEADS for the operator to investigate and
to EVIDENCE-GROUND later (UD-3), nothing more.

HONESTY IS THE INVARIANT. Every suggestion is:

* LABELLED with the verbatim :data:`~cosmosiq_assistant.guardrails.AI_LABEL`
  ("AI-generated -- not evidence, not a recommendation."),
* stamped ``verification_status="unverified_ai_suggestion"`` and
  ``source_authority="ai_suggestion"`` -- a NON-authority that is DELIBERATELY OUTSIDE the real
  evidence ladder (``canonical > primary > convenience > fallback > manual > rumor``); it is never
  canonical / primary / convenience / fallback / manual / rumor,
* POST-FILTERED through :func:`~cosmosiq_assistant.guardrails.filter_action_directives` (a model that
  returns "buy NVDA now" comes back with the removal marker -- no buy / sell / order directive can
  survive),
* carried alongside a :data:`SUGGESTION_DISCLAIMER` that every theme / ticker is UNVERIFIED and must
  be grounded against SEC / FMP before any use.

ISOLATION IS PRESERVED. This module lives in ``cosmosiq_assistant`` (the EDGE) and NEVER imports
``reality_mesh`` -- not the engine, not ``universe_discovery``. The suggestions it produces are
NEVER written to any Event / Finding / Signal / candidate / diligence / theme-graph store; they
persist ONLY to the assistant-owned, clearly-labelled :data:`UNIVERSE_SUGGESTIONS_FILENAME` jsonl.
They never enter the deterministic engine / graph / pulse / lineage. The shape (``theme`` +
``candidate_tickers``) is ALIGNED with UD-1's ``DiscoveredUniverseCandidate`` vocabulary WITHOUT
importing it, so UD-3 can later ground a suggestion into a provenanced candidate.

LLM calls are LAZY (no network on import) and INJECTABLE (tests pass fakes; the real provider path is
never exercised). Credentials are PRESENCE labels only. Stdlib-only, Python 3.9, deterministic,
OFFLINE tests.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .guardrails import ACTION_REMOVED, AI_LABEL, filter_action_directives
from .router import run_assistant

__all__ = [
    "SUGGEST_UNIVERSE_TASK",
    "SUGGESTION_SYSTEM_PROMPT",
    "SUGGESTION_DISCLAIMER",
    "UNVERIFIED_STATUS",
    "AI_SUGGESTION_AUTHORITY",
    "UNIVERSE_SUGGESTIONS_FILENAME",
    "UniverseSuggestion",
    "UniverseSuggestionResult",
    "suggest_universe",
    "universe_suggestions_path",
    "append_universe_suggestions",
    "read_universe_suggestions",
]

SUGGEST_UNIVERSE_TASK = "suggest_universe"

# The stamp every suggestion carries: it is an UNVERIFIED AI lead, not evidence.
UNVERIFIED_STATUS = "unverified_ai_suggestion"

# A NON-authority. It is DELIBERATELY OUTSIDE the real evidence ladder
# (canonical > primary > convenience > fallback > manual > rumor); tests assert it is not a member.
AI_SUGGESTION_AUTHORITY = "ai_suggestion"

# The clearly-labelled, evidence-SEPARATE store filename. No engine / evidence store uses this name.
UNIVERSE_SUGGESTIONS_FILENAME = "universe_suggestions.jsonl"

# The verbatim disclaimer bound to every result + every persisted suggestion.
SUGGESTION_DISCLAIMER = (
    "Every theme and ticker here is an UNVERIFIED AI suggestion -- a lead to INVESTIGATE, not "
    "evidence and not a recommendation. Ground each against SEC / FMP (UD-3) before any use; none "
    "has entered the deterministic engine, graph, pulse, or lineage.")

# The suggestion persona: an EDGE research assistant proposing LEADS, never an adviser. Belt (system
# prompt) AND braces (the output post-filter applied by run_assistant + re-applied per parsed field).
SUGGESTION_SYSTEM_PROMPT = (
    "You are CosmosIQ's EDGE research assistant. Your job is to PROPOSE emerging investment THEMES "
    "that established SEC / FMP sector taxonomies may not classify yet, and for each theme a few "
    "CANDIDATE TICKER symbols worth INVESTIGATING. Everything you propose is an UNVERIFIED LEAD for "
    "the operator to verify against primary sources -- it is NOT evidence and NOT a recommendation. "
    "You are NOT an investment adviser: never tell anyone to buy, sell, hold, or place an order, "
    "and never give a price target or position size as advice. If you are unsure a ticker exists, "
    "still present it only as a lead to verify, never as a fact. Everything you write is "
    "AI-generated, unverified, and must be grounded against SEC / FMP before any use.")

_SUGGEST_TEMPLATE = (
    "Propose emerging investment themes and candidate tickers for the operator to INVESTIGATE, "
    "given the research context below. For EACH theme, output a block EXACTLY in this shape:\n\n"
    "THEME: <short emerging theme name>\n"
    "RATIONALE: <one or two sentences on why it is emerging and worth investigating>\n"
    "TICKERS: <comma-separated candidate ticker symbols to investigate, uppercase>\n\n"
    "Present every theme and every ticker as an UNVERIFIED lead to verify against SEC / FMP, never "
    "as advice. Do not tell anyone to buy, sell, hold, or size a position.\n\n"
    "--- RESEARCH CONTEXT ---\n{context}\n--- END CONTEXT ---")

# A candidate ticker: an UPPERCASE symbol string (1-10 chars, letters lead, digits / . / - allowed).
# The operator VERIFIES it later; here it is only a lead, never a claim that the symbol is real.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


# --------------------------------------------------------------------------- #
# The typed suggestion contracts (frozen; labelled; unverified; ai_suggestion)   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UniverseSuggestion:
    """One AI-proposed EMERGING theme + its candidate tickers -- an UNVERIFIED lead, never evidence.

    ``candidate_tickers`` are UPPERCASE symbol strings the operator will VERIFY; nothing here is a
    claim that the symbol is real or a recommendation to trade it. ``verification_status`` is always
    ``unverified_ai_suggestion`` and ``source_authority`` is always the NON-authority
    ``ai_suggestion`` (OUTSIDE the real evidence ladder). It confers NO capital standing and never
    enters the deterministic engine / graph / pulse / lineage.
    """

    theme: str = ""
    rationale: str = ""
    candidate_tickers: Tuple[str, ...] = field(default_factory=tuple)
    verification_status: str = UNVERIFIED_STATUS
    source_authority: str = AI_SUGGESTION_AUTHORITY
    label: str = AI_LABEL
    ai_generated: bool = True
    not_evidence: bool = True


@dataclass(frozen=True)
class UniverseSuggestionResult:
    """The output of one :func:`suggest_universe` run: labelled, disclaimed, post-filtered leads.

    ``suggestions`` is the best-effort STRUCTURED parse of the (already action-filtered) model
    output. ``label`` is the verbatim :data:`AI_LABEL`; ``disclaimer`` is
    :data:`SUGGESTION_DISCLAIMER`. ``provider_used`` is "" on an honest all-provider gap. The whole
    result is DISPLAY-ONLY -- never evidence, never an engine / graph / pulse / lineage input.
    """

    suggestions: Tuple[UniverseSuggestion, ...] = field(default_factory=tuple)
    label: str = AI_LABEL
    disclaimer: str = SUGGESTION_DISCLAIMER
    provider_used: str = ""
    mode: str = "free"
    source_authority: str = AI_SUGGESTION_AUTHORITY
    ai_generated: bool = True
    not_evidence: bool = True
    notes: Tuple[str, ...] = field(default_factory=tuple)
    raw_text: str = ""


# --------------------------------------------------------------------------- #
# The producer                                                                  #
# --------------------------------------------------------------------------- #
def suggest_universe(context: object, *, mode: str = "free",
                     env: Optional[Mapping[str, str]] = None,
                     clients: Optional[Mapping[str, Any]] = None,
                     now: object = 0.0) -> UniverseSuggestionResult:
    """Ask the isolated AI assistant to PROPOSE emerging themes + candidate tickers to INVESTIGATE.

    ``context`` is the operator-supplied research context (free text). The prompt asks the model for
    EMERGING themes and, per theme, candidate ticker symbols -- explicitly as leads to verify, NOT
    recommendations. The model output is run through :func:`run_assistant` (so it is already
    action-directive POST-FILTERED and carries :data:`AI_LABEL`), then best-effort STRUCTURED-parsed
    into :class:`UniverseSuggestion`s. Each suggestion is stamped ``unverified_ai_suggestion`` /
    ``ai_suggestion`` and every parsed field is re-filtered so no buy / sell / order directive can
    survive. ``clients`` injects fakes (OFFLINE tests); ``now`` is the injected clock. Nothing here
    is persisted as evidence or fed to the engine -- see :func:`append_universe_suggestions`.
    """
    prompt = _SUGGEST_TEMPLATE.format(context=str(context if context is not None else ""))
    result = run_assistant(SUGGEST_UNIVERSE_TASK, prompt, system=SUGGESTION_SYSTEM_PROMPT,
                           mode=mode, env=env, clients=clients, now=now)
    suggestions = _parse_suggestions(result.text)
    return UniverseSuggestionResult(
        suggestions=suggestions,
        label=result.label,                    # always AI_LABEL (mandatory, verbatim)
        disclaimer=SUGGESTION_DISCLAIMER,
        provider_used=result.provider_used,
        mode=result.mode,
        notes=result.notes,
        raw_text=result.text,
    )


def _parse_suggestions(text: object) -> Tuple[UniverseSuggestion, ...]:
    """Best-effort parse of ``THEME:`` / ``RATIONALE:`` / ``TICKERS:`` blocks into suggestions.

    ``text`` is the ALREADY action-filtered model output. Each field is defensively re-filtered so a
    directive can never leak through the parse. A ticker is any UPPERCASE symbol token; non-ticker
    tokens (prose, the redaction marker, blanks) are dropped. A block with neither a theme nor a
    ticker is skipped (nothing fabricated).
    """
    lines = str(text if text is not None else "").splitlines()
    blocks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    def _flush() -> None:
        if current is not None and (current["theme"] or current["candidate_tickers"]):
            blocks.append(current)

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        label, _, value = line.partition(":")
        key = label.strip().lower()
        value = value.strip()
        if key == "theme":
            _flush()
            current = {"theme": filter_action_directives(value),
                       "rationale": "", "candidate_tickers": []}
        elif key == "rationale":
            if current is None:
                current = {"theme": "", "rationale": "", "candidate_tickers": []}
            current["rationale"] = filter_action_directives(value)
        elif key in ("tickers", "ticker", "candidate_tickers", "candidates"):
            if current is None:
                current = {"theme": "", "rationale": "", "candidate_tickers": []}
            current["candidate_tickers"] = _parse_tickers(value)
    _flush()

    return tuple(
        UniverseSuggestion(
            theme=b["theme"],
            rationale=b["rationale"],
            candidate_tickers=tuple(b["candidate_tickers"]),
        )
        for b in blocks
    )


def _parse_tickers(value: str) -> List[str]:
    """Split a ``TICKERS:`` line into deduped ALREADY-UPPERCASE symbol tokens (order-stable).

    The line is action-filtered first (so a "buy NVDA now, sell TSLA" line loses the directive
    words), the inert redaction marker is stripped (so its prose never leaks as a token), then the
    remainder is split on commas / whitespace. Only tokens that are ALREADY an uppercase symbol
    survive -- lowercase prose ("buy" / "now" / "sell") is never up-cased into a fake ticker. Each is
    only a lead the operator will VERIFY.
    """
    cleaned = filter_action_directives(value).replace(ACTION_REMOVED, " ")
    out: List[str] = []
    for token in re.split(r"[,\s]+", cleaned):
        token = token.strip().strip(".")
        if _TICKER_RE.match(token) and token not in out:
            out.append(token)
    return out


# --------------------------------------------------------------------------- #
# The assistant-OWNED suggestions store (SEPARATE from every evidence store)      #
# --------------------------------------------------------------------------- #
def universe_suggestions_path(store_dir: str) -> str:
    return os.path.join(str(store_dir), UNIVERSE_SUGGESTIONS_FILENAME)


def append_universe_suggestions(store_dir: str, result: UniverseSuggestionResult, *,
                                now: object = "", subject: str = "") -> Tuple[str, ...]:
    """Append each suggestion of ``result`` to the isolated jsonl; return the appended ids.

    Writes ONLY to :data:`UNIVERSE_SUGGESTIONS_FILENAME` -- NEVER to any Event / Finding / Signal /
    candidate / diligence / theme-graph store. Every record is tagged ``ai_generated=True``,
    ``not_evidence=True``, ``source_authority="ai_suggestion"`` (a NON-authority OUTSIDE the evidence
    ladder) and ``verification_status="unverified_ai_suggestion"``, carries the verbatim
    :data:`AI_LABEL` + :data:`SUGGESTION_DISCLAIMER`, and is append-only (a prior line is never
    rewritten). A result with no suggestions writes nothing and returns ``()``.
    """
    if not str(store_dir).strip():
        raise ValueError("append_universe_suggestions requires a non-empty store_dir")
    if not result.suggestions:
        return ()
    os.makedirs(str(store_dir), exist_ok=True)
    path = universe_suggestions_path(store_dir)
    seq = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            seq = sum(1 for line in handle if line.strip())

    ids: List[str] = []
    with open(path, "a", encoding="utf-8") as handle:
        for suggestion in result.suggestions:
            seq += 1
            suggestion_id = "ai-univ-suggestion-{0:06d}".format(seq)
            record: Dict[str, Any] = {
                "suggestion_id": suggestion_id,
                "ai_generated": True,
                "not_evidence": True,
                "source_authority": AI_SUGGESTION_AUTHORITY,
                "verification_status": UNVERIFIED_STATUS,
                "label": AI_LABEL,
                "disclaimer": SUGGESTION_DISCLAIMER,
                "theme": suggestion.theme,
                "rationale": suggestion.rationale,
                "candidate_tickers": list(suggestion.candidate_tickers),
                "provider_used": result.provider_used,
                "mode": result.mode,
                "subject": str(subject),
                "recorded_at": str(now),
                "note": (
                    "AI-generated EMERGING-theme/ticker suggestion (UD-2) -- display-only lead for "
                    "operator review + evidence-grounding (UD-3); NOT evidence, NOT a recommendation; "
                    "source_authority 'ai_suggestion' is OUTSIDE the "
                    "canonical/primary/convenience/fallback/manual/rumor evidence ladder; never read "
                    "by the deterministic engine, graph, pulse, or lineage"),
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            ids.append(suggestion_id)
    return tuple(ids)


def read_universe_suggestions(store_dir: str) -> Tuple[Dict[str, Any], ...]:
    """Every appended AI universe suggestion (append order). Display-only; the engine never reads it."""
    path = universe_suggestions_path(store_dir)
    if not os.path.isfile(path):
        return ()
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(dict(json.loads(line)))
            except ValueError:
                continue
    return tuple(out)
