"""CLI entry point: ``PYTHONPATH=src python3 -m cosmosiq_pulse --watchlist … --themes … --out …``.

The migrated (English) name for the manual, on-demand Reality-Mesh pulse. It delegates VERBATIM
to :func:`tattva_pulse.__main__.main`, so the produced evidence pages + ``pulse_summary.json`` are
byte-for-byte identical to the legacy ``python3 -m tattva_pulse`` invocation. See
``docs/OPERATOR_GUIDE_012.md``.
"""

from __future__ import annotations

import sys

from tattva_pulse.__main__ import main


if __name__ == "__main__":
    sys.exit(main())
