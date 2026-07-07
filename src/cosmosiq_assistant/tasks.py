"""The two assistant capabilities + the neutral research system prompt (PROD-LIVE-3).

Two display-only capabilities for the operator to REVIEW -- never advice, never a directive:

* :func:`summarize_filing` -- summarise a filing / filing-event's METADATA and text in plain
  English, citing only what is in the input.
* :func:`draft_thesis_note` -- draft a neutral, evidence-anchored research note for a ticker from
  the operator-supplied evidence context, listing both the supporting and the contradicting points.

Both run through :func:`cosmosiq_assistant.router.run_assistant`, so every result is LABELLED with
the mandatory AI-generated tag and its ``text`` is POST-FILTERED (no buy / sell / order directive
can ever be returned). The :data:`RESEARCH_SYSTEM_PROMPT` instructs the model to summarise /
analyse and to REFUSE advice -- belt (system prompt) AND braces (the output post-filter).

Stdlib-only, Python 3.9, deterministic, OFFLINE tests.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .router import AssistantResult, run_assistant

__all__ = [
    "RESEARCH_SYSTEM_PROMPT",
    "summarize_filing",
    "draft_thesis_note",
    "SUMMARIZE_TASK",
    "THESIS_TASK",
]

SUMMARIZE_TASK = "summarize_filing"
THESIS_TASK = "draft_thesis_note"

# The neutral research persona: a summariser / analyst, NOT an advisor. Instruct the model to cite
# only the input and to REFUSE any buy / sell / hold / order directive. This is the belt; the
# output post-filter is the braces.
RESEARCH_SYSTEM_PROMPT = (
    "You are CosmosIQ's research assistant. Your ONLY job is to SUMMARISE and ANALYSE the "
    "material the operator provides. Cite only what is present in the input; if a figure or "
    "fact is not in the input, say it is not stated rather than inventing it. Surface both "
    "supporting and contradicting evidence, and flag anything unverified or rumoured AS "
    "unverified. You are NOT an investment adviser: never tell anyone to buy, sell, hold, or "
    "place an order, never issue a trade instruction, target price as advice, or sizing "
    "directive. If asked to advise, decline and summarise the evidence instead. Everything you "
    "write is AI-generated, is not evidence and not a recommendation, and must be verified by "
    "the operator against the cited sources.")

_SUMMARIZE_TEMPLATE = (
    "Summarise the following filing or filing-event for the operator{ticker}. Give a short "
    "plain-English overview, then bullet the key facts (form / date / stated figures), then "
    "note any dilution, restatement, guidance or risk language IF present in the text, then "
    "list what the input does NOT state (gaps). Cite only what is below; do not advise.\n\n"
    "--- FILING / EVENT INPUT ---\n{body}\n--- END INPUT ---")

_THESIS_TEMPLATE = (
    "Draft a neutral research note for {ticker} from the operator-supplied evidence context "
    "below. Structure it as: (1) what the evidence says, (2) supporting points, (3) "
    "contradicting / risk points, (4) open questions and gaps. Anchor every point to the "
    "evidence provided; mark anything unverified or rumoured as such. This is a REVIEW note "
    "for the operator, not advice: do not tell anyone to buy, sell, hold, or size a position.\n\n"
    "--- EVIDENCE CONTEXT for {ticker} ---\n{context}\n--- END CONTEXT ---")


def summarize_filing(filing_text_or_event: object, *, ticker: str = "", mode: str = "free",
                     env: Optional[Mapping[str, str]] = None,
                     clients: Optional[Mapping[str, Any]] = None,
                     now: object = 0.0) -> AssistantResult:
    """Summarise a filing / filing-event for the operator to REVIEW (labelled + post-filtered).

    ``filing_text_or_event`` may be raw filing text or a stringified filing-event. ``ticker`` is
    an optional subject label. Returns an :class:`AssistantResult` carrying the mandatory
    AI-generated label and the post-filtered summary (never a buy / sell / order directive).
    """
    subject = " for {0}".format(str(ticker).strip().upper()) if str(ticker).strip() else ""
    prompt = _SUMMARIZE_TEMPLATE.format(
        ticker=subject, body=str(filing_text_or_event if filing_text_or_event is not None else ""))
    return run_assistant(SUMMARIZE_TASK, prompt, system=RESEARCH_SYSTEM_PROMPT, mode=mode,
                        env=env, clients=clients, now=now)


def draft_thesis_note(ticker: str, evidence_context: object, *, mode: str = "free",
                      env: Optional[Mapping[str, str]] = None,
                      clients: Optional[Mapping[str, Any]] = None,
                      now: object = 0.0) -> AssistantResult:
    """Draft a neutral, evidence-anchored thesis note for ``ticker`` (labelled + post-filtered).

    ``evidence_context`` is the operator-supplied evidence text the note is anchored to. Returns
    an :class:`AssistantResult` with the mandatory AI-generated label and the post-filtered note.
    It surfaces supporting AND contradicting points; it never issues an action directive.
    """
    symbol = str(ticker).strip().upper() or "the company"
    prompt = _THESIS_TEMPLATE.format(
        ticker=symbol,
        context=str(evidence_context if evidence_context is not None else ""))
    return run_assistant(THESIS_TASK, prompt, system=RESEARCH_SYSTEM_PROMPT, mode=mode,
                        env=env, clients=clients, now=now)
