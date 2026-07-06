"""Inline static style for the CosmosIQ app pages (IMPLEMENTATION-016B).

ONE deterministic string: :data:`APP_CSS` -- the CosmosIQ dark cosmic look, with palette
values borrowed (copied, never imported) from the Universe UI stylesheet. It is inlined
into every server-rendered page so each page is fully self-contained:

* NO external asset, NO CDN, NO remote font, NO CSS import directive, NO stylesheet
  link tag -- offline always;
* NO JavaScript at all (collapsibles use plain ``<details>``; data gaps are never rendered
  inside a collapsed region);
* colour == meaning: green for healthy/pass labels, amber for degraded/warn, red for
  failed/fail -- badges are LABELS, never scores.

Stdlib-only, Python 3.9, deterministic.
"""

from __future__ import annotations

__all__ = ["APP_CSS"]

# Palette values copied from the Universe UI design system (universe_ui/assets.py, READ-ONLY
# reference): near-black indigo base, glass surfaces, restrained accents.
APP_CSS = """
:root{
  --bg:#060814; --bg2:#0a0e1e; --panel:#0e1330;
  --glass:rgba(18,24,48,.55); --glass-line:rgba(140,160,255,.14);
  --ink:#eef2ff; --muted:#9aa6d6; --faint:#5c6690; --line:#26315f;
  --accent:#8b7bff; --cyan:#4fe0ff;
  --good:#39e0a0; --warn:#ffb03a; --bad:#ff4d6d; --badge:#1b234d;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);
  background:
    radial-gradient(1100px 650px at 18% -8%, #1a2350 0%, rgba(6,8,20,0) 55%),
    radial-gradient(900px 600px at 92% 8%, #241a4a 0%, rgba(6,8,20,0) 52%),
    var(--bg);
  line-height:1.5; font-size:13px;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
/* Full-width, naturally scrolling cockpit: the document is a normal scrolling page
   (no overflow lock on html/body) and the content area spans the whole viewport
   width with sensible gutters -- never squeezed into a narrow centred column. */
.wrap{width:100%;max-width:none;margin:0;padding:1.1rem 2rem 5rem}
.strip{
  position:sticky;top:0;z-index:50;background:rgba(8,11,26,.85);
  border-bottom:1px solid var(--glass-line);color:var(--muted);
  font-size:12px;font-weight:600;padding:.5rem 2rem;letter-spacing:.4px;
}
.strip .sep{color:#465086;margin:0 .35rem}
.bar{display:flex;align-items:center;flex-wrap:wrap;gap:.6rem;
  padding:1rem 2rem .5rem;width:100%;max-width:none;margin:0}
.brand{font-size:1.15rem;font-weight:800;letter-spacing:.5px;margin-right:1rem}
.brand small{display:block;font-size:.68rem;font-weight:600;color:var(--muted);
  letter-spacing:1.5px}
/* the compact honest status chip (a quiet pill; the full honest mode line lives in its
   title tooltip and its expandable details -- honesty preserved, just not shouting). */
.chip-wrap{margin-left:auto}
.chip{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:.45rem;
  padding:.32rem .8rem;border:1px solid var(--glass-line);border-radius:999px;
  background:var(--glass);color:#cdd6ff;font-size:11.5px;font-weight:700;
  white-space:nowrap}
.chip::-webkit-details-marker{display:none}
.chip .dot{width:.5rem;height:.5rem;border-radius:50%;background:var(--good);
  box-shadow:0 0 8px rgba(57,224,160,.7)}
.chip-details{color:var(--muted);font-size:11px;padding:.4rem .8rem;max-width:90ch;
  line-height:1.45}
/* the primary 8-tab nav + a quiet utility row of operator surfaces. */
.tabs{display:flex;flex-wrap:wrap;gap:.4rem;width:100%;padding:.1rem 2rem .55rem}
.subnav{display:flex;flex-wrap:wrap;gap:.9rem;align-items:center;width:100%;
  padding:.15rem 2rem .7rem;border-bottom:1px solid var(--glass-line)}
.navsub{color:var(--faint);font-size:11px;font-weight:600}
.navsub:hover{color:var(--cyan);text-decoration:none}
.navlink{padding:.4rem .95rem;border:1px solid var(--glass-line);border-radius:999px;
  background:var(--glass);color:var(--muted);font-size:12px;font-weight:600}
.navlink:hover{color:var(--ink);border-color:var(--cyan);text-decoration:none}
.navlink.here{color:#fff;border-color:var(--cyan);background:rgba(79,224,255,.12)}
.navnote{color:var(--faint);font-size:11px;padding:.4rem .5rem}
/* dashboard overview cards -- a spacious wide-desktop grid of quiet metric tiles. */
.cards{display:flex;flex-wrap:wrap;gap:.9rem;margin:.7rem 0}
.card{flex:1 1 210px;min-width:180px;background:var(--glass);
  border:1px solid var(--glass-line);border-radius:14px;padding:.95rem 1.05rem;
  box-shadow:0 10px 40px rgba(0,0,0,.35)}
.card .metric{font-size:1.9rem;font-weight:800;color:var(--ink);letter-spacing:-.5px;
  line-height:1.1}
.card .clabel{color:var(--muted);font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.7px;margin-bottom:.2rem}
.card .csub{color:var(--faint);font-size:11px;margin-top:.25rem}
h1{font-size:26px;letter-spacing:-.5px;margin:.5rem 0 .25rem;font-weight:800}
h2{font-size:18px;margin:1.4rem 0 .5rem;border-bottom:1px solid var(--line);
  padding-bottom:.3rem}
h3{font-size:14px;margin:.9rem 0 .35rem;color:#dfe6ff;font-weight:700}
.note{color:var(--muted);font-size:12px;max-width:80ch}
.foot{color:var(--faint);font-size:11px;margin-top:2.5rem;border-top:1px solid var(--line);
  padding-top:.6rem}
.panel{background:var(--glass);border:1px solid var(--glass-line);border-radius:14px;
  padding:1rem 1.1rem;margin:.6rem 0;box-shadow:0 10px 40px rgba(0,0,0,.45)}
table.kv{border-collapse:collapse;width:100%;font-size:12.5px}
table.kv th{color:var(--muted);text-align:left;font-weight:600;padding:.3rem .6rem .3rem 0;
  vertical-align:top;white-space:nowrap}
table.kv td{padding:.3rem .6rem .3rem 0;vertical-align:top;border-top:1px solid
  rgba(38,49,95,.5)}
.badge{display:inline-block;padding:.12rem .5rem;border-radius:999px;font-size:.72rem;
  font-weight:700;border:1px solid var(--line);background:var(--badge);color:#cdd6ff;
  margin:.1rem .25rem .1rem 0;white-space:nowrap}
.badge.ok{color:#7dffb8;border-color:#1f6b45}
.badge.warn{background:#2a1406;border-color:#b5651d;color:#ffbf87}
.badge.bad{background:#2a0d17;border-color:var(--bad);color:#ff9db4}
.verdict{font-size:16px;font-weight:800;padding:.8rem 1rem;border-radius:14px;margin:.6rem 0}
.verdict.ok{background:#0f2a1c;border:1px solid #1f6b45;color:#7dffb8}
.verdict.bad{background:#2a0d17;border:1px solid var(--bad);color:#ff9db4}
ul.gaps li,ul.diffs li{color:#ffbf87;font-size:12.5px;margin:.15rem 0}
ul.diffs li{color:#ff9db4;font-family:var(--mono);font-size:11.5px}
.op-form{margin:.6rem 0;padding:.7rem .9rem;border:1px dashed rgba(140,160,255,.3);
  border-radius:10px;background:rgba(10,14,30,.5)}
.op-form label{display:block;color:var(--muted);font-size:12px;margin:.25rem 0}
.op-form input[type=text]{background:var(--bg2);border:1px solid var(--line);
  color:var(--ink);border-radius:8px;padding:.35rem .5rem;width:100%;max-width:420px;
  font-family:var(--mono);font-size:12px}
.op-form select{background:var(--bg2);border:1px solid var(--line);color:var(--ink);
  border-radius:8px;padding:.35rem .5rem;font-size:12px}
.op-form button{background:rgba(79,224,255,.12);border:1px solid var(--cyan);
  color:#dff6ff;border-radius:999px;padding:.4rem 1rem;font-weight:700;font-size:12px;
  cursor:pointer;margin:.3rem 0}
.op-note{display:block;color:var(--faint);font-size:11px;margin-top:.25rem;max-width:80ch}
.op-form fieldset.op-side{border:1px solid var(--line);border-radius:8px;
  margin:.35rem 0;padding:.3rem .6rem}
.op-form fieldset.op-side legend{color:var(--muted);font-size:12px;padding:0 .3rem}
.op-form label.radio{display:inline-block;margin:.1rem 1rem .1rem 0;color:var(--ink);
  font-size:12.5px}
.op-form label.radio input[type=radio]{margin-right:.35rem;vertical-align:middle}
.form-error{background:#2a0d17;border:1px solid var(--bad);color:#ff9db4;
  border-radius:10px;padding:.5rem .8rem;margin:.5rem 0;font-size:12.5px}
.mono{font-family:var(--mono);font-size:11.5px}
/* the Map view: the generated Universe Canvas framed READ-ONLY, filling the width. */
.canvas-frame{width:100%;height:78vh;min-height:420px;border:1px solid var(--glass-line);
  border-radius:14px;background:var(--bg2);display:block;margin:.6rem 0}
.canvas-open{display:inline-block;background:rgba(79,224,255,.12);border:1px solid var(--cyan);
  color:#dff6ff;border-radius:999px;padding:.4rem 1rem;font-weight:700;font-size:12px;
  margin:.3rem 0}
.canvas-open:hover{text-decoration:none;border-color:var(--ink)}
/* the celestial legend + the plain-language pipeline steps -- a quiet responsive grid. */
.legend{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0}
.legend .cell{flex:1 1 190px;min-width:170px;background:rgba(10,14,30,.5);
  border:1px solid var(--glass-line);border-radius:10px;padding:.55rem .75rem}
.legend .cell b{color:var(--cyan);font-size:12.5px}
.legend .cell span{display:block;color:var(--muted);font-size:11.5px;margin-top:.15rem}
.cmd{font-family:var(--mono);font-size:12px;color:#dff6ff;background:var(--bg2);
  border:1px solid var(--line);border-radius:8px;padding:.45rem .7rem;display:block;
  margin:.5rem 0;white-space:pre-wrap;word-break:break-word}
.steps{display:flex;flex-direction:column;gap:.55rem;margin:.6rem 0}
"""
