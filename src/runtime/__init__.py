"""Runtime layer: the vertical-slice runner."""

from __future__ import annotations

from .vertical_slice_runner import run_iren_slice, SliceResult
from .evidence_alpha_slice_runner import (
    run_evidence_alpha_slice,
    EvidenceAlphaSliceResult,
)

__all__ = [
    "run_iren_slice",
    "SliceResult",
    "run_evidence_alpha_slice",
    "EvidenceAlphaSliceResult",
]
