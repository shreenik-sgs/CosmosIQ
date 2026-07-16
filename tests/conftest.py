"""pytest path setup: make ``src/`` AND ``tests/`` importable when running under pytest.

``tests/`` is a package (it has ``__init__.py``), so pytest's default "prepend" import mode walks
up to the first directory WITHOUT one -- the repo root -- and puts THAT on ``sys.path``, never
``tests/`` itself. But seven test modules import the shared helper as a bare top-level module
(``from _real_chain import ...``), which resolves only when ``tests/`` is literally on the path.
``python -m unittest discover -s tests`` inserts the start directory for free, which is why
``make test`` / ``make ci`` never noticed; plain ``pytest tests/`` collected ZERO tests instead.

Six of those seven only ever "passed" under pytest by accident -- an unrelated module happened to
``sys.path.insert`` the tests directory as a side effect and happened to sort earlier in the
alphabet. That is not a fix; it breaks the moment anyone runs a single file, filters with ``-k``,
shards, or randomises order. Put ``tests/`` on the path here, once, so every invocation works.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
for _path in (_SRC, _HERE):
    if _path not in sys.path:
        sys.path.insert(0, _path)
