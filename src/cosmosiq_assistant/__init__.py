"""CosmosIQ AI Research Assistant (PROD-LIVE-3) -- the ISOLATED, EDGE-only LLM summariser / analyst.

This package lives OUTSIDE ``reality_mesh`` (the deterministic engine) on purpose. The engine
stays LLM-free and ``reality_mesh`` NEVER imports this package. The assistant summarises a filing
or drafts a thesis note for the operator to REVIEW; its output is DISPLAY-ONLY -- never persisted
as evidence, never fed to any gate / candidate / recommendation / data-quality store, never part
of replay. Every result carries the mandatory, verbatim label
(:data:`~cosmosiq_assistant.guardrails.AI_LABEL`) and its text is POST-FILTERED so it can never
render a buy / sell / order directive.

LLM calls are LAZY (no network on import) and INJECTABLE (tests pass fakes, so the suite is fully
OFFLINE and the real provider network is never exercised). Stdlib-only (``urllib`` inside functions;
no ``anthropic`` / ``openai`` / ``google`` / ``requests`` SDK anywhere). Credentials are PRESENCE
labels only -- a key value is never read, printed, logged, rendered, or persisted.
"""

from __future__ import annotations

from .guardrails import (
    ACTION_REMOVED,
    AI_LABEL,
    contains_action_directive,
    filter_action_directives,
)
from .notes_store import (
    ASSISTANT_NOTES_FILENAME,
    append_assistant_note,
    read_assistant_notes,
)
from .providers import (
    AnthropicClient,
    GeminiClient,
    NvidiaClient,
    ProviderChain,
    ProviderError,
    assistant_configured,
    build_provider_chain,
)
from .router import (
    AssistantResult,
    AssistantRouter,
    CircuitBreaker,
    GLOBAL_BREAKER,
    app_run_assistant,
    clear_test_clients,
    install_test_clients,
    run_assistant,
)
from .tasks import (
    RESEARCH_SYSTEM_PROMPT,
    draft_thesis_note,
    summarize_filing,
)
from .universe_suggestions import (
    AI_SUGGESTION_AUTHORITY,
    SUGGEST_UNIVERSE_TASK,
    SUGGESTION_DISCLAIMER,
    SUGGESTION_SYSTEM_PROMPT,
    UNIVERSE_SUGGESTIONS_FILENAME,
    UNVERIFIED_STATUS,
    UniverseSuggestion,
    UniverseSuggestionResult,
    append_universe_suggestions,
    read_universe_suggestions,
    suggest_universe,
    universe_suggestions_path,
)

__all__ = [
    "AI_LABEL",
    "ACTION_REMOVED",
    "filter_action_directives",
    "contains_action_directive",
    "ProviderError",
    "NvidiaClient",
    "GeminiClient",
    "AnthropicClient",
    "ProviderChain",
    "build_provider_chain",
    "assistant_configured",
    "AssistantResult",
    "AssistantRouter",
    "CircuitBreaker",
    "GLOBAL_BREAKER",
    "run_assistant",
    "app_run_assistant",
    "install_test_clients",
    "clear_test_clients",
    "RESEARCH_SYSTEM_PROMPT",
    "summarize_filing",
    "draft_thesis_note",
    "ASSISTANT_NOTES_FILENAME",
    "append_assistant_note",
    "read_assistant_notes",
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
