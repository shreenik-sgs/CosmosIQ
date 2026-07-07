"""LLM provider clients + the free / paid provider chain (PROD-LIVE-3).

Each provider is a small client with a UNIFORM interface -- ``complete(prompt, *, system) -> text``.
Three real clients are supported, all reached over stdlib ``urllib`` that is imported LAZILY inside
the call (never at module top), so importing this module touches NO network and pulls in NO network
library. Tests inject a FAKE client (any object with ``.provider`` / ``.configured`` /
``complete``) so the suite stays fully OFFLINE and the real provider network is NEVER exercised.

CREDENTIALS ARE PRESENCE LABELS ONLY. A client is built from key PRESENCE (``name in env``); the
key VALUE is read lazily inside :meth:`complete` at call time and is never stored, printed, logged,
rendered, or persisted. A provider whose key is absent is ``configured=False`` and is SKIPPED by
the chain builder with an honest note (an honest gap in the chain, never a crash).

NO SDK. There is no ``anthropic`` / ``openai`` / ``google`` / ``requests`` import anywhere -- the
HTTP is hand-rolled over ``urllib`` so ``dependencies_reviewed`` stays green (stdlib-only).

Two chains (assembled by :func:`build_provider_chain` from key presence):

* FREE (default, all unattended work): ``NVIDIA_API_KEY`` -> NVIDIA NIM (workhorse) -> on
  error / unconfigured -> ``GOOGLE_API_KEY`` -> Gemini.
* PAID (explicit "full_api" only): ``ANTHROPIC_API_KEY`` -> Claude -> on billing / http failure
  -> ``ANTHROPIC_API_KEY_FALLBACK`` -> a secondary Claude key.

Stdlib-only, Python 3.9, deterministic, OFFLINE tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

__all__ = [
    "ProviderError",
    "NvidiaClient",
    "GeminiClient",
    "AnthropicClient",
    "ProviderChain",
    "build_provider_chain",
    "assistant_configured",
    "PROVIDER_KEY_ENV_VARS",
    "FREE_MODES",
    "PAID_MODES",
]

# The env var NAMES the assistant may consult (PRESENCE only -- a value is never read here).
PROVIDER_KEY_ENV_VARS: Tuple[str, ...] = (
    "NVIDIA_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FALLBACK")

FREE_MODES = frozenset({"free", "", "default", "unattended"})
PAID_MODES = frozenset({"paid", "full_api", "full-api", "claude"})

# Real endpoints (used ONLY on a live operator run; NEVER reached in tests -- fakes are injected).
_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "{model}:generateContent")
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
_GEMINI_MODEL = "gemini-1.5-flash"
_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"

# Error-body / status tokens that classify a failure as a BILLING / credit-ceiling failure (which,
# for a paid provider, trips the circuit breaker). Kept conservative and lowercase.
_BILLING_TOKENS = (
    "billing", "credit", "credits", "quota", "insufficient", "payment", "exceeded",
    "over the limit", "balance", "402")
_AUTH_TOKENS = ("401", "403", "unauthorized", "forbidden", "invalid api key",
                "invalid_api_key", "authentication")


class ProviderError(Exception):
    """A typed failure from one provider ``complete`` call.

    ``kind`` is a closed label the router reads: ``"unconfigured"`` (no key -- skip), ``"billing"``
    (credit / billing ceiling -- paid providers trip the breaker), ``"auth"`` (401/403 -- paid
    providers trip the breaker), ``"5xx"`` (server error -- paid providers trip the breaker), or
    ``"http"`` (any other transport / parse failure). The message NEVER contains a key value.
    """

    def __init__(self, message: str, *, kind: str = "http", provider: str = "") -> None:
        super().__init__(str(message))
        self.kind = kind
        self.provider = provider


def _classify_http(status: Optional[int], body: str) -> str:
    """Classify an HTTP failure into a ProviderError kind from status + (lowercased) body."""
    text = str(body or "").lower()
    if status is not None and 500 <= int(status) <= 599:
        return "5xx"
    if status in (401, 403) or any(tok in text for tok in _AUTH_TOKENS):
        return "auth"
    if status == 402 or any(tok in text for tok in _BILLING_TOKENS):
        return "billing"
    return "http"


def _http_post_json(url: str, headers: Mapping[str, str], payload: Mapping[str, Any],
                    *, provider: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Lazy stdlib HTTP POST of a JSON body -> decoded JSON dict. urllib is imported HERE.

    A non-2xx / transport / decode failure is raised as a typed :class:`ProviderError` (its kind
    classified from the status + body). NEVER exercised by the offline test suite (fakes injected).
    """
    import json
    import urllib.error       # LAZY -- import-time stays network-free by construction.
    import urllib.request

    data = json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json",
                                              **dict(headers)})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # nosec - audited boundary
            raw = resp.read()
    except urllib.error.HTTPError as exc:                # noqa: BLE001 -- typed below, never leaks
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:                               # noqa: BLE001
            body = ""
        raise ProviderError(
            "{0} HTTP {1}".format(provider, exc.code),
            kind=_classify_http(exc.code, body), provider=provider)
    except Exception as exc:                            # noqa: BLE001 -- timeout / URLError / etc.
        raise ProviderError(
            "{0} transport failure: {1}".format(provider, type(exc).__name__),
            kind="http", provider=provider)
    try:
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        return json.loads(text)
    except Exception as exc:                            # noqa: BLE001 -- malformed body
        raise ProviderError("{0} malformed response: {1}".format(provider, type(exc).__name__),
                            kind="http", provider=provider)


class _RealClientBase:
    """Shared real-client behaviour: presence-only credential + lazy value read at call time."""

    provider = ""
    env_key = ""

    def __init__(self, *, configured: bool = False, env_key: Optional[str] = None,
                 provider: Optional[str] = None, model: Optional[str] = None) -> None:
        self._configured = bool(configured)
        if env_key is not None:
            self.env_key = env_key
        if provider is not None:
            self.provider = provider
        self.model = model or self._default_model()

    def _default_model(self) -> str:
        return ""

    @property
    def configured(self) -> bool:
        return self._configured

    def __repr__(self) -> str:  # presence label only -- a key value never exists on the instance
        return "{0}(provider={1!r}, env_key={2!r}, configured={3})".format(
            type(self).__name__, self.provider, self.env_key, self._configured)

    def complete(self, prompt: str, *, system: str = "") -> str:
        """Read the key VALUE lazily from the environment and call the provider. Never in tests."""
        import os  # lazy; NOT a network import
        key = os.environ.get(self.env_key, "")
        if not key:
            raise ProviderError(
                "{0} unconfigured ({1} absent)".format(self.provider, self.env_key),
                kind="unconfigured", provider=self.provider)
        return self._call(key, str(prompt or ""), str(system or ""))

    def _call(self, key: str, prompt: str, system: str) -> str:  # pragma: no cover - real path
        raise NotImplementedError


class NvidiaClient(_RealClientBase):
    """NVIDIA NIM (OpenAI-compatible chat/completions), Bearer ``NVIDIA_API_KEY``. FREE workhorse."""

    provider = "nvidia"
    env_key = "NVIDIA_API_KEY"

    def _default_model(self) -> str:
        return _NVIDIA_MODEL

    def _call(self, key: str, prompt: str, system: str) -> str:  # pragma: no cover - real path
        payload = {
            "model": self.model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 1024,
        }
        data = _http_post_json(_NVIDIA_URL, {"Authorization": "Bearer " + key},
                               payload, provider=self.provider)
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else {}) or {}
        return str(message.get("content", "") or "")


class GeminiClient(_RealClientBase):
    """Google Gemini generateContent, ``?key=GOOGLE_API_KEY``. FREE fallback."""

    provider = "gemini"
    env_key = "GOOGLE_API_KEY"

    def _default_model(self) -> str:
        return _GEMINI_MODEL

    def _call(self, key: str, prompt: str, system: str) -> str:  # pragma: no cover - real path
        payload: Dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            payload["system_instruction"] = {"parts": [{"text": system}]}
        url = _GEMINI_URL.format(model=self.model) + "?key=" + key
        data = _http_post_json(url, {}, payload, provider=self.provider)
        candidates = data.get("candidates") or []
        content = (candidates[0].get("content") if candidates else {}) or {}
        parts = content.get("parts") or []
        return "".join(str(p.get("text", "") or "") for p in parts)


class AnthropicClient(_RealClientBase):
    """Anthropic Claude messages, ``x-api-key`` + ``anthropic-version``. PAID chain.

    ``fallback=True`` reads ``ANTHROPIC_API_KEY_FALLBACK`` and reports ``provider=
    'anthropic_fallback'`` so the router can name which key served the request.
    """

    provider = "anthropic"
    env_key = "ANTHROPIC_API_KEY"

    def __init__(self, *, configured: bool = False, fallback: bool = False,
                 model: Optional[str] = None) -> None:
        super().__init__(
            configured=configured,
            env_key="ANTHROPIC_API_KEY_FALLBACK" if fallback else "ANTHROPIC_API_KEY",
            provider="anthropic_fallback" if fallback else "anthropic",
            model=model)

    def _default_model(self) -> str:
        return _ANTHROPIC_MODEL

    def _call(self, key: str, prompt: str, system: str) -> str:  # pragma: no cover - real path
        payload: Dict[str, Any] = {
            "model": self.model, "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        data = _http_post_json(_ANTHROPIC_URL, headers, payload, provider=self.provider)
        blocks = data.get("content") or []
        return "".join(str(b.get("text", "") or "") for b in blocks
                       if isinstance(b, dict) and b.get("type", "text") == "text")


# slot -> (provider label, env var NAME, real-client factory). The chain is assembled from these.
def _nvidia(configured: bool) -> NvidiaClient:
    return NvidiaClient(configured=configured)


def _gemini(configured: bool) -> GeminiClient:
    return GeminiClient(configured=configured)


def _anthropic(configured: bool) -> AnthropicClient:
    return AnthropicClient(configured=configured, fallback=False)


def _anthropic_fallback(configured: bool) -> AnthropicClient:
    return AnthropicClient(configured=configured, fallback=True)


_FREE_SLOTS: Tuple[Tuple[str, str, str, Any], ...] = (
    ("nvidia", "nvidia", "NVIDIA_API_KEY", _nvidia),
    ("gemini", "gemini", "GOOGLE_API_KEY", _gemini),
)
_PAID_SLOTS: Tuple[Tuple[str, str, str, Any], ...] = (
    ("anthropic", "anthropic", "ANTHROPIC_API_KEY", _anthropic),
    ("anthropic_fallback", "anthropic_fallback", "ANTHROPIC_API_KEY_FALLBACK",
     _anthropic_fallback),
)


def normalize_mode(mode: object) -> str:
    """The two effective chains: 'paid' for an explicit full_api opt-in, else 'free'."""
    token = str(mode or "").strip().lower()
    return "paid" if token in PAID_MODES else "free"


@dataclass(frozen=True)
class ProviderChain:
    """One assembled, ordered chain of CONFIGURED clients + honest notes on any skipped slot."""

    mode: str = "free"
    clients: Tuple[Any, ...] = field(default_factory=tuple)
    notes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def provider_order(self) -> Tuple[str, ...]:
        return tuple(getattr(c, "provider", "") for c in self.clients)

    @property
    def configured(self) -> bool:
        return bool(self.clients)


def build_provider_chain(*, mode: str = "free", env: Optional[Mapping[str, str]] = None,
                         clients: Optional[Mapping[str, Any]] = None) -> ProviderChain:
    """Assemble the FREE or PAID chain from key PRESENCE (``name in env``); inject fakes via ``clients``.

    ``env`` defaults to ``os.environ`` and is consulted PRESENCE-ONLY (a value is never read here).
    ``clients`` maps a slot name (``"nvidia"`` / ``"gemini"`` / ``"anthropic"`` /
    ``"anthropic_fallback"``) to an injected client (the offline-test seam). A slot whose client is
    unconfigured (no key / injected ``configured=False``) is SKIPPED with an honest note -- a gap in
    the chain, never a crash.
    """
    import os  # lazy; NOT a network import
    mapping: Mapping[str, str] = os.environ if env is None else env
    injected: Mapping[str, Any] = dict(clients or {})
    slots = _PAID_SLOTS if normalize_mode(mode) == "paid" else _FREE_SLOTS

    ordered: List[Any] = []
    notes: List[str] = []
    for slot, provider, env_key, factory in slots:
        client = injected.get(slot)
        if client is None:
            client = factory(env_key in mapping)      # presence only -- never reads the value
        if not getattr(client, "configured", True):
            notes.append(
                "{0} unconfigured ({1} absent) -- skipped (honest gap in the chain)".format(
                    provider, env_key))
            continue
        ordered.append(client)
    return ProviderChain(mode=normalize_mode(mode), clients=tuple(ordered), notes=tuple(notes))


def assistant_configured(env: Optional[Mapping[str, str]] = None) -> bool:
    """True iff ANY LLM provider key is PRESENT (membership only -- a value is never read).

    Used by the app panel to choose between the live assistant and the honest "not configured"
    state. NVIDIA / GOOGLE / ANTHROPIC presence -> configured.
    """
    import os  # lazy
    mapping: Mapping[str, str] = os.environ if env is None else env
    return any(name in mapping for name in
               ("NVIDIA_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"))
