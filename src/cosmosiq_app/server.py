"""The THIN operator-started HTTP shell around the pure dispatcher (IMPLEMENTATION-016A).

This module is the ONLY place in the product where a socket is bound and a serve loop runs --
and it runs ONLY because an operator explicitly started it:

    PYTHONPATH=src python3 -m cosmosiq_app --store-dir generated/pulse_store [--port N]

The shell parses each HTTP request into the plain dict :func:`cosmosiq_app.api.dispatch`
expects, injects wall-clock ``now`` AT THIS BOUNDARY ONLY (the dispatcher itself never reads a
clock), and writes the JSON response back. It binds **127.0.0.1 by default** and REFUSES a
non-local host unless ``--allow-remote`` is passed explicitly (with a printed warning). It
serves until Ctrl-C, then exits -- there is no scheduler daemon, no background thread, no
broker, and no trading endpoint (the dispatcher refuses trade-like routes with 403).

This module is NOT imported by :mod:`cosmosiq_app` itself, NOT imported by the offline test
suite (tests exercise :mod:`cosmosiq_app.api` only), and NOT imported by anything inside
:mod:`reality_mesh` -- the reality_mesh anti-network / anti-daemon AST guards stay untouched.
The ``serve_forever`` loop below is permitted HERE ONLY (Phase 016: the operator-started app
process).

Stdlib-only, Python 3.9, localhost-by-default.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlsplit

from .api import APP_NAME, dispatch

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "LOCAL_HOSTS",
    "BANNER",
    "CosmosIQRequestHandler",
    "form_body",
    "serve",
    "wall_clock_now",
]

# Localhost is the HARD-CODED default. Binding anything else requires the explicit
# --allow-remote flag (and prints a warning) -- never a silent exposure.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8016
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

# The honest banner printed at startup: exactly what this process is, and is not.
BANNER = """\
{app} -- local operator app (Phase 016A)
  * local app: serving http://{host}:{port} (localhost-only by default)
  * operator-started: this process exists only because you started it; Ctrl-C stops it
  * no scheduler daemon: nothing runs in the background; ticks and pulses are explicit
  * no broker: read-only evidence plus explicit manual actions (ack / pause / resume /
    manual pulse / settings) -- no trading endpoint exists
  * store_dir: {store_dir} (append-only JSONL; history is never rewritten)
"""


def wall_clock_now() -> str:
    """Wall-clock ``now`` -- read at the SHELL BOUNDARY ONLY, never inside the dispatcher."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 016B: form keys the browser posts as comma-separated text but the dispatcher expects as
# JSON lists (the operator forms on the server-rendered pages).
_FORM_LIST_KEYS = ("watchlist", "watchlists", "themes", "subscriptions")


def form_body(raw_text: str, now: str) -> dict:
    """Decode ONE urlencoded operator-form body into the dispatcher's plain-dict shape.

    Boundary adaptation only (016B): comma-separated list fields become lists, and the
    injected ``at`` instant is added HERE (the shell boundary) when the form did not carry
    one -- the dispatcher itself still never reads a clock.
    """
    data: dict = {}
    for key, value in parse_qsl(raw_text, keep_blank_values=True):
        if key in _FORM_LIST_KEYS:
            data[key] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            data[key] = value
    data.setdefault("at", now)
    return data


class CosmosIQRequestHandler(BaseHTTPRequestHandler):
    """Parse one HTTP request -> the dispatcher's request dict -> one JSON response."""

    server_version = "CosmosIQ/016A"

    def _handle(self) -> None:
        parts = urlsplit(self.path)
        now = wall_clock_now()
        body = None
        method = self.command
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            raw = self.rfile.read(length)
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if content_type.lower() == "application/x-www-form-urlencoded":
                # 016B: an operator form posted from a server-rendered page.
                body = form_body(raw.decode("utf-8", "replace"), now)
                override = str(body.pop("_method", "") or "")
                if override:
                    method = override.upper()   # HTML forms cannot send PUT themselves
            else:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    body = raw.decode("utf-8", "replace")   # dispatch answers 400 + reason
        request = {
            "method": method,
            "path": parts.path,
            "query": dict(parse_qsl(parts.query)),
            "body": body,
        }
        response = dispatch(request, store_dir=self.server.store_dir, now=now)
        headers = dict(response.get("headers") or {})
        response_body = response.get("body")
        if isinstance(response_body, str) and \
                not headers.get("Content-Type", "").startswith("application/json"):
            payload = response_body.encode("utf-8")    # 016B: server-rendered HTML page
        else:
            payload = json.dumps(response_body, sort_keys=True).encode("utf-8")
        self.send_response(int(response.get("status", 200)))
        for name, value in (response.get("headers") or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle


def serve(store_dir: str, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          allow_remote: bool = False) -> None:
    """Bind and serve until Ctrl-C. Localhost by default; non-local requires --allow-remote."""
    if not str(store_dir).strip():
        raise SystemExit("cosmosiq_app requires a non-empty --store-dir")
    if host not in LOCAL_HOSTS:
        if not allow_remote:
            raise SystemExit(
                "refusing to bind non-local host {0!r}: CosmosIQ is a LOCAL operator app. "
                "Pass --allow-remote explicitly if you really mean to expose it (a warning "
                "will be printed).".format(host))
        print("WARNING: --allow-remote set -- binding non-local host {0!r}. CosmosIQ has no "
              "authentication; anyone who can reach this port can read your local stores "
              "and journal manual actions. Prefer the localhost default.".format(host))

    server = HTTPServer((host, port), CosmosIQRequestHandler)
    server.store_dir = str(store_dir)
    print(BANNER.format(app=APP_NAME, host=host, port=port, store_dir=store_dir))
    try:
        # Permitted HERE ONLY: the operator-started app process (Phase 016). The dispatcher
        # and everything in reality_mesh remain loop-free.
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCtrl-C received -- {0} app shell stopped.".format(APP_NAME))
    finally:
        server.server_close()
