"""The assistant-notes store (PROD-LIVE-3) -- an append-only jsonl SEPARATE from every evidence store.

If (and only if) the operator chooses to keep an assistant output, it is appended here -- to
``<store_dir>/assistant_notes.jsonl``, a file that is DELIBERATELY distinct from every 013B
evidence / signal / candidate / recommendation / data-quality store. Each record is tagged
``ai_generated=True`` and carries the mandatory AI-generated label. This file is NEVER read by
``reality_mesh`` or by any gate / candidate / recommendation / replay -- it is display-only history
for the operator, isolated from the deterministic engine.

Append-only: a record is a new line; nothing is ever rewritten. Stdlib-only, deterministic, OFFLINE.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "ASSISTANT_NOTES_FILENAME",
    "assistant_notes_path",
    "append_assistant_note",
    "read_assistant_notes",
]

# The clearly-labelled, evidence-separate filename. No 013B store uses this name.
ASSISTANT_NOTES_FILENAME = "assistant_notes.jsonl"


def assistant_notes_path(store_dir: str) -> str:
    return os.path.join(str(store_dir), ASSISTANT_NOTES_FILENAME)


def append_assistant_note(store_dir: str, result: Any, *, now: object = "",
                          subject: str = "") -> str:
    """Append ONE assistant result to the isolated notes jsonl; return the note id.

    ``result`` is an :class:`~cosmosiq_assistant.router.AssistantResult`. The record is tagged
    ``ai_generated=True`` with the mandatory label and the POST-FILTERED text -- never any raw
    unmarked model output, never an evidence record. The store never mutates a prior line.
    """
    if not str(store_dir).strip():
        raise ValueError("append_assistant_note requires a non-empty store_dir")
    os.makedirs(str(store_dir), exist_ok=True)
    path = assistant_notes_path(store_dir)
    seq = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            seq = sum(1 for line in handle if line.strip())
    note_id = "assistant-note-{0:06d}".format(seq + 1)
    record: Dict[str, Any] = {
        "note_id": note_id,
        "ai_generated": True,
        "label": getattr(result, "label", ""),
        "task": getattr(result, "task", str(subject)),
        "subject": str(subject),
        "provider_used": getattr(result, "provider_used", ""),
        "mode": getattr(result, "mode", ""),
        "circuit_state": getattr(result, "circuit_state", ""),
        "text": getattr(result, "text", ""),
        "recorded_at": str(now),
        "not_evidence": True,
        "note": ("AI-generated assistant output -- display-only; NOT evidence, NOT a "
                 "recommendation; never read by the deterministic engine, gates, candidates, "
                 "recommendations, or replay"),
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return note_id


def read_assistant_notes(store_dir: str) -> Tuple[Dict[str, Any], ...]:
    """Every appended assistant note (in append order). Display-only; engine never calls this."""
    path = assistant_notes_path(store_dir)
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
