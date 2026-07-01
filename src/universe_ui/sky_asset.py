"""Deterministic, LOCAL deep-space background asset (IMPLEMENTATION-010A-SKY-VISUAL).

``deep_space_background_svg()`` returns a self-contained SVG string — a telescope /
deep-field night sky: a deep black-indigo gradient, a faint deep-field glow, soft
nebula clouds, dark dust lanes, a distant galaxy, and a dense star field (hundreds of
stars with varied size / brightness / colour-temperature, plus a few bright glow
stars). The app writes it once to ``assets/deep_space_background.svg`` and the hero
references it as a LOCAL background image.

Discipline: it is a checked-in-style LOCAL asset built at BUILD time (not runtime, not
in the browser). Positions/sizes/opacities come from a fixed-seed pure LCG (no
``random`` module, no clock, no network, no remote/copyrighted image) so two builds are
byte-identical. All colours/shapes are our own procedural art.
"""

from __future__ import annotations

_W = 1600
_H = 1000
_SEED = 1013904223


def _lcg():
    """A tiny deterministic 0..1 generator (numerical-recipes LCG); no random/clock."""
    state = _SEED

    def nxt() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    return nxt


def deep_space_background_svg() -> str:
    """Return the deterministic deep-space SVG (a pure function; byte-stable)."""
    nxt = _lcg()
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'preserveAspectRatio="xMidYMid slice">'.format(w=_W, h=_H))

    # ---- defs: gradients + blur filters ----
    parts.append(
        "<defs>"
        '<radialGradient id="sky" cx="42%" cy="32%" r="85%">'
        '<stop offset="0%" stop-color="#141033"/>'
        '<stop offset="42%" stop-color="#0b0a22"/>'
        '<stop offset="72%" stop-color="#060614"/>'
        '<stop offset="100%" stop-color="#020109"/>'
        "</radialGradient>"
        '<radialGradient id="deepfield" cx="50%" cy="46%" r="60%">'
        '<stop offset="0%" stop-color="#2a2668" stop-opacity="0.55"/>'
        '<stop offset="60%" stop-color="#120f38" stop-opacity="0.18"/>'
        '<stop offset="100%" stop-color="#060614" stop-opacity="0"/>'
        "</radialGradient>"
        '<radialGradient id="nVio" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#7b3ff2" stop-opacity="0.9"/>'
        '<stop offset="100%" stop-color="#7b3ff2" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="nBlue" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#2f7bd0" stop-opacity="0.9"/>'
        '<stop offset="100%" stop-color="#2f7bd0" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="nRose" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#e0518a" stop-opacity="0.85"/>'
        '<stop offset="100%" stop-color="#e0518a" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="nTeal" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#33d6c0" stop-opacity="0.8"/>'
        '<stop offset="100%" stop-color="#33d6c0" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="starGlow" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#ffffff" stop-opacity="0.9"/>'
        '<stop offset="35%" stop-color="#cfe0ff" stop-opacity="0.35"/>'
        '<stop offset="100%" stop-color="#cfe0ff" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="galaxy" cx="50%" cy="50%" r="50%">'
        '<stop offset="0%" stop-color="#fff7e6" stop-opacity="0.95"/>'
        '<stop offset="24%" stop-color="#ffd79a" stop-opacity="0.5"/>'
        '<stop offset="60%" stop-color="#a86bd0" stop-opacity="0.22"/>'
        '<stop offset="100%" stop-color="#a86bd0" stop-opacity="0"/></radialGradient>'
        '<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="46"/></filter>'
        '<filter id="dust" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="24"/></filter>'
        "</defs>")

    # ---- sky + deep-field glow ----
    parts.append('<rect width="{w}" height="{h}" fill="url(#sky)"/>'.format(w=_W, h=_H))
    parts.append('<rect width="{w}" height="{h}" fill="url(#deepfield)"/>'.format(w=_W, h=_H))

    # ---- soft nebula clouds (blurred, low opacity) ----
    nebs = (
        (330, 250, 430, 300, "nVio", 0.30),
        (1180, 360, 520, 360, "nBlue", 0.22),
        (760, 780, 400, 260, "nRose", 0.16),
        (980, 150, 300, 220, "nTeal", 0.12),
    )
    parts.append('<g filter="url(#soft)">')
    for cx, cy, rx, ry, grad, op in nebs:
        parts.append(
            '<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#{g})" '
            'opacity="{o}"/>'.format(cx=cx, cy=cy, rx=rx, ry=ry, g=grad, o=op))
    parts.append("</g>")

    # ---- dark dust lanes (blurred silhouettes crossing the field) ----
    parts.append('<g filter="url(#dust)" fill="#04040c">')
    parts.append('<path d="M-100 560 Q 500 500 900 600 T 1700 560 L 1700 700 '
                 'Q 900 720 500 640 T -100 700 Z" opacity="0.55"/>')
    parts.append('<ellipse cx="1150" cy="800" rx="520" ry="70" '
                 'transform="rotate(-14 1150 800)" opacity="0.4"/>')
    parts.append("</g>")

    # ---- a faint distant galaxy ----
    parts.append(
        '<g transform="translate(1240 250) rotate(24)">'
        '<ellipse cx="0" cy="0" rx="150" ry="54" fill="url(#galaxy)"/>'
        '<ellipse cx="0" cy="0" rx="60" ry="60" fill="url(#galaxy)" opacity="0.7"/>'
        "</g>")

    # ---- dense star field (deterministic) ----
    parts.append("<g>")
    for _ in range(540):
        x = nxt() * _W
        y = nxt() * _H
        r = 0.35 + (nxt() ** 2) * 1.55          # mostly tiny, a few larger
        o = 0.32 + nxt() * 0.6
        t = nxt()
        col = "#ffffff" if t < 0.70 else ("#ffe6c4" if t < 0.86 else "#cfe0ff")
        parts.append(
            '<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{c}" '
            'opacity="{o:.2f}"/>'.format(x=x, y=y, r=r, c=col, o=o))
    parts.append("</g>")

    # ---- a few BRIGHT stars with a soft glow halo ----
    parts.append("<g>")
    for _ in range(30):
        x = nxt() * _W
        y = nxt() * _H
        r = 1.3 + nxt() * 1.7
        parts.append(
            '<circle cx="{x:.1f}" cy="{y:.1f}" r="{g:.1f}" fill="url(#starGlow)"/>'
            '<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#ffffff"/>'.format(
                x=x, y=y, g=r * 4.2, r=r))
    parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)
