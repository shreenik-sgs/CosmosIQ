"""Test package. Ensures ``src/`` is importable under both unittest and pytest.

unittest's discovery imports this package before the test modules, so the path
insertion here makes the runtime packages importable without any external
configuration.
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
