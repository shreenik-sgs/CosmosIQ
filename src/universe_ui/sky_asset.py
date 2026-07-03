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

_W = 2200
_H = 1300
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
        '<radialGradient id="sky" cx="42%" cy="32%" r="92%">'
        '<stop offset="0%" stop-color="#17113a"/>'
        '<stop offset="38%" stop-color="#0b0a24"/>'
        '<stop offset="70%" stop-color="#050612"/>'
        '<stop offset="100%" stop-color="#020109"/>'
        "</radialGradient>"
        '<radialGradient id="deepfield" cx="48%" cy="45%" r="64%">'
        '<stop offset="0%" stop-color="#312a78" stop-opacity="0.58"/>'
        '<stop offset="58%" stop-color="#120f38" stop-opacity="0.2"/>'
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
        '<linearGradient id="dustLine" x1="0%" y1="0%" x2="100%" y2="0%">'
        '<stop offset="0%" stop-color="#02020a" stop-opacity="0"/>'
        '<stop offset="42%" stop-color="#02020a" stop-opacity="0.9"/>'
        '<stop offset="58%" stop-color="#04030c" stop-opacity="0.88"/>'
        '<stop offset="100%" stop-color="#02020a" stop-opacity="0"/></linearGradient>'
        '<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="46"/></filter>'
        '<filter id="wideSoft" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="78"/></filter>'
        '<filter id="dust" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="24"/></filter>'
        "</defs>")

    # ---- sky + deep-field glow ----
    parts.append('<rect width="{w}" height="{h}" fill="url(#sky)"/>'.format(w=_W, h=_H))
    parts.append('<rect width="{w}" height="{h}" fill="url(#deepfield)"/>'.format(w=_W, h=_H))

    # ---- soft nebula clouds (blurred, low opacity) ----
    nebs = (
        (420, 300, 560, 360, "nVio", 0.28),
        (1610, 460, 680, 420, "nBlue", 0.2),
        (1040, 1010, 520, 320, "nRose", 0.15),
        (1360, 190, 420, 260, "nTeal", 0.12),
        (780, 640, 980, 180, "nBlue", 0.08),
    )
    parts.append('<g filter="url(#wideSoft)">')
    for cx, cy, rx, ry, grad, op in nebs:
        parts.append(
            '<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#{g})" '
            'opacity="{o}"/>'.format(cx=cx, cy=cy, rx=rx, ry=ry, g=grad, o=op))
    parts.append("</g>")

    # ---- dark dust lanes (blurred silhouettes crossing the field) ----
    parts.append('<g filter="url(#dust)" fill="#04040c">')
    parts.append('<path d="M-160 690 Q 620 585 1180 720 T 2360 680 L 2360 850 '
                 'Q 1200 880 620 790 T -160 850 Z" fill="url(#dustLine)" opacity="0.62"/>')
    parts.append('<ellipse cx="1540" cy="1000" rx="700" ry="82" '
                 'transform="rotate(-14 1540 1000)" opacity="0.38"/>')
    parts.append('<ellipse cx="560" cy="190" rx="420" ry="56" '
                 'transform="rotate(18 560 190)" opacity="0.24"/>')
    parts.append("</g>")

    # ---- elegant distant galaxy CLUSTERS (soft luminous spiral discs) ----
    galaxies = (
        (1700, 320, 24, 200, 70, 0.95),
        (460, 900, -18, 128, 44, 0.68),
        (1160, 240, 8, 88, 30, 0.55),
        (1850, 930, 40, 104, 34, 0.56),
        (760, 520, -32, 72, 22, 0.38),
    )
    for cx, cy, rot, rx, ry, op in galaxies:
        parts.append(
            '<g transform="translate({cx} {cy}) rotate({rot})" opacity="{op}">'
            '<ellipse cx="0" cy="0" rx="{rx}" ry="{ry}" fill="url(#galaxy)"/>'
            '<path d="M-{rx} 0 C -{h} -{q} {h} {q} {rx} 0" '
            'stroke="#fff2cf" stroke-opacity="0.2" stroke-width="2" fill="none"/>'
            '<path d="M-{rx} 0 C -{h} {q} {h} -{q} {rx} 0" '
            'stroke="#b9a8ff" stroke-opacity="0.16" stroke-width="2" fill="none"/>'
            '<ellipse cx="0" cy="0" rx="{cr}" ry="{cr}" fill="url(#galaxy)" opacity="0.7"/>'
            "</g>".format(cx=cx, cy=cy, rot=rot, rx=rx, ry=ry, op=op,
                          h=rx * 0.42, q=ry * 1.05, cr=ry * 1.05))

    # ---- dense star field (deterministic) ----
    parts.append("<g>")
    for _ in range(920):
        x = nxt() * _W
        y = nxt() * _H
        r = 0.28 + (nxt() ** 2.2) * 1.65
        o = 0.24 + nxt() * 0.68
        t = nxt()
        col = "#ffffff" if t < 0.70 else ("#ffe6c4" if t < 0.86 else "#cfe0ff")
        parts.append(
            '<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{c}" '
            'opacity="{o:.2f}"/>'.format(x=x, y=y, r=r, c=col, o=o))
    parts.append("</g>")

    # ---- a few BRIGHT stars with a soft glow halo ----
    parts.append("<g>")
    for _ in range(44):
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
