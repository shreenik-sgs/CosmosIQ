"""Static local assets for the Universe UI (IMPLEMENTATION-010A).

Two deterministic strings only:

* :data:`COSMIC_CSS` -- an executive, sci-fi command-center stylesheet (cosmic dark
  background, luminous galaxy/planet/star nodes, heat/urgency indicators, evidence
  and source-authority badges, red-team / black-hole markers, data-gap warnings).
* :data:`NAV_JS` -- navigation-ONLY JavaScript. It attaches click listeners (via
  ``addEventListener``, never inline ``onclick``) that toggle tab visibility and
  expand/collapse panels, and nothing else. It contains NO ``fetch`` / ``XMLHttpRequest``
  / live call, NO ``<form>`` handling, NO submit, and NO order / buy / sell affordance.
  It can only switch views, scroll, and drive CSS zoom transitions -- it can never
  hide a data gap (gaps are always rendered outside any collapsible region).

Both are emitted as local assets (``assets/universe.css`` / ``assets/universe.js``)
and are also inlined so every page is self-contained. Local assets only -- no CDN,
no remote font, no network reference of any kind.
"""

from __future__ import annotations

COSMIC_CSS = """
:root{
  --bg:#05060d; --bg2:#0a0e1c; --panel:#0e1330; --panel2:#131a3d;
  --ink:#e7ecff; --muted:#9aa6d6; --line:#26315f;
  --heat-hot:#ff5d3b; --heat-warm:#ffb03a; --heat-cool:#4ad6ff; --heat-dim:#5b6690;
  --good:#38e08a; --warn:#ffcf4d; --bad:#ff5470; --hazard:#ff2e63;
  --badge:#1b234d; --accent:#7c8cff;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);
  background:
    radial-gradient(1200px 700px at 20% -5%, #16204d 0%, rgba(5,6,13,0) 55%),
    radial-gradient(900px 600px at 90% 10%, #241640 0%, rgba(5,6,13,0) 50%),
    var(--bg);
  line-height:1.5; letter-spacing:.1px;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1200px;margin:0 auto;padding:0 1.25rem 4rem}

/* ---- persistent status strip (never collapsible) ---- */
.status-strip{
  position:sticky;top:0;z-index:50;
  background:linear-gradient(90deg,#0a0f24,#131a3d);
  border-bottom:1px solid var(--line);
  color:var(--muted);font-size:.82rem;font-weight:600;
  padding:.5rem 1.25rem;letter-spacing:.3px;
}
.status-strip .sep{color:#465086;margin:0 .35rem}
.status-strip b{color:#cdd6ff}

/* ---- top command bar / nav ---- */
.command-bar{
  display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;
  padding:1rem 1.25rem .4rem;max-width:1200px;margin:0 auto;
}
.brand{font-size:1.15rem;font-weight:800;letter-spacing:.5px;margin-right:1rem}
.brand small{display:block;font-size:.68rem;font-weight:600;color:var(--muted);letter-spacing:1.5px}
.navlink{
  padding:.35rem .7rem;border:1px solid var(--line);border-radius:999px;
  background:var(--panel);color:var(--muted);font-size:.8rem;font-weight:600;
}
.navlink:hover{color:var(--ink);border-color:var(--accent);text-decoration:none}
.navlink.here{color:#fff;border-color:var(--accent);background:var(--panel2)}

h1{font-size:1.7rem;margin:.6rem 0 .2rem}
h2{font-size:1.25rem;margin:1.6rem 0 .5rem;border-bottom:1px solid var(--line);padding-bottom:.3rem}
h3{font-size:1.02rem;margin:1.1rem 0 .35rem;color:#cdd6ff}
h4{font-size:.9rem;margin:.7rem 0 .3rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px}
.lead{color:var(--muted);max-width:70ch}

/* ---- badges ---- */
.badge{display:inline-block;padding:.12rem .5rem;border-radius:999px;font-size:.72rem;
  font-weight:700;border:1px solid var(--line);background:var(--badge);color:#cdd6ff;
  margin:.1rem .25rem .1rem 0;white-space:nowrap}
.badge.demo{background:#241a10;border-color:#6b4d1e;color:#ffcf8a}
.badge.real{background:#0f2a1c;border-color:#1f6b45;color:#7dffb8}
.badge.auth-canonical{background:#0f2440;border-color:#2f6bd0;color:#8fc2ff}
.badge.auth-convenience{background:#241f10;border-color:#7a6320;color:#ffde8a}
.badge.auth-fallback{background:#26161c;border-color:#7a2f44;color:#ffa9c0}
.badge.q-high{color:#7dffb8;border-color:#1f6b45}
.badge.q-medium{color:#ffde8a;border-color:#7a6320}
.badge.q-low,.badge.q-sparse{color:#ffa9c0;border-color:#7a2f44}
.badge.hazard{background:#2a0d17;border-color:var(--hazard);color:#ff9db4}
.badge.gap{background:#2a1406;border-color:#b5651d;color:#ffbf87}

/* ---- heat / node cards ---- */
.grid-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.card{
  background:linear-gradient(160deg,var(--panel),var(--panel2));
  border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem;
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.card:hover{transform:translateY(-3px) scale(1.012);border-color:var(--accent);
  box-shadow:0 10px 40px rgba(80,110,255,.18)}
.card .title{font-size:1.05rem;font-weight:800;margin:0 0 .2rem}
.card .sub{color:var(--muted);font-size:.82rem;margin:0 0 .5rem}

/* heat glow rings on the galaxy nodes */
.galaxy-node{position:relative;overflow:hidden}
.galaxy-node::before{content:"";position:absolute;inset:-40% -40% auto auto;width:170px;height:170px;
  border-radius:50%;filter:blur(30px);opacity:.55;pointer-events:none}
.heat-hot::before{background:var(--heat-hot)}
.heat-warm::before{background:var(--heat-warm)}
.heat-cool::before{background:var(--heat-cool)}
.heat-dim{opacity:.72}
.heat-dim::before{background:var(--heat-dim);opacity:.28}
.data-poor{filter:saturate(.6)}
.blackhole{border-color:var(--hazard);box-shadow:inset 0 0 60px rgba(255,46,99,.18)}
.euphoric{border-color:#b5651d;box-shadow:0 0 0 1px #b5651d, 0 0 34px rgba(181,101,29,.25)}

.kv{width:100%;border-collapse:collapse;margin:.3rem 0;font-size:.86rem}
.kv th{text-align:left;color:var(--muted);font-weight:600;width:38%;
  vertical-align:top;padding:.22rem .4rem;border-bottom:1px solid rgba(38,49,95,.5)}
.kv td{padding:.22rem .4rem;vertical-align:top;border-bottom:1px solid rgba(38,49,95,.5)}
table.chain{width:100%;border-collapse:collapse;font-size:.82rem;margin:.4rem 0}
table.chain th,table.chain td{border:1px solid var(--line);padding:.35rem .5rem;text-align:left}
table.chain th{background:#121a3d;color:#cdd6ff}

.tier-tag{font-size:.7rem;font-weight:700;color:#9fb0ff;text-transform:uppercase;letter-spacing:.6px}
.gap-box{background:#2a1406;border:1px solid #7a4a18;border-radius:10px;padding:.6rem .8rem;margin:.6rem 0}
.gap-box h4{color:#ffbf87;margin-top:0}
.warn-box{background:#2a2406;border:1px solid #7a6a18;border-radius:10px;padding:.6rem .8rem;margin:.6rem 0}
.hazard-box{background:#2a0d17;border:1px solid var(--hazard);border-radius:10px;padding:.6rem .8rem;margin:.6rem 0}
.note{color:var(--muted);font-size:.82rem;font-style:italic}
.qualifier{color:#ffcf8a;font-size:.8rem;font-weight:600}

/* tabs (navigation-only, no form) */
.tabbar{display:flex;flex-wrap:wrap;gap:.4rem;margin:1rem 0 .6rem}
.tab{cursor:pointer;padding:.35rem .8rem;border:1px solid var(--line);border-radius:999px;
  background:var(--panel);color:var(--muted);font-size:.82rem;font-weight:700;user-select:none}
.tab:hover{color:var(--ink);border-color:var(--accent)}
.tab.active{color:#fff;background:var(--panel2);border-color:var(--accent)}
[data-tab-panel]{display:none}
[data-tab-panel].shown{display:block}

/* collapsible (never wraps a data gap) */
.collapse-head{cursor:pointer;user-select:none;color:#cdd6ff;font-weight:700}
.collapse-head::before{content:"\\25BE  "}
.collapsible.collapsed{display:none}

.bucket{margin:1.2rem 0}
.bucket h3{display:flex;align-items:center;gap:.5rem}
.bucket .count{font-size:.78rem;color:var(--muted);font-weight:600}
/* visual-size orb: SIZE = economic magnitude; GLOW = status; NOT a ranking input */
.orb-wrap{display:flex;align-items:center;gap:.6rem;margin:.4rem 0}
.orb{border-radius:50%;flex:none;
  background:radial-gradient(circle at 35% 30%, #aab6ff, #4756c8 60%, #23306e);
  box-shadow:0 0 10px rgba(124,140,255,.35)}
.orb.glow-3{box-shadow:0 0 26px 4px rgba(124,255,184,.55)}
.orb.glow-2{box-shadow:0 0 16px 2px rgba(255,222,138,.4)}
.orb.glow-1{box-shadow:0 0 8px rgba(120,130,160,.3);filter:saturate(.7)}
.orb.dashed{border:2px dashed #ffbf87;background:radial-gradient(circle at 35% 30%,#3a3550,#20233d)}
.orb-meta{font-size:.78rem;color:var(--muted)}
.orb-meta b{color:#cdd6ff}
.dashed-outline{border-style:dashed !important;border-color:#ffbf87 !important}
.banner{background:linear-gradient(90deg,#1a1030,#241640);border:1px solid #5a3fb0;
  border-radius:12px;padding:.8rem 1rem;margin:1rem 0;font-weight:700;color:#e3d9ff}
footer{color:#4b5687;font-size:.75rem;margin-top:2.5rem;border-top:1px solid var(--line);padding-top:.8rem}
"""


NAV_JS = """
/* Universe UI -- navigation-ONLY behaviour. No network, no form, no order. */
(function(){
  function ready(fn){
    if(document.readyState!=='loading'){fn();}
    else{document.addEventListener('DOMContentLoaded',fn);}
  }
  ready(function(){
    /* Tab switching: show one panel in a group, hide its siblings. */
    var tabs=document.querySelectorAll('[data-tab-target]');
    for(var i=0;i<tabs.length;i++){
      tabs[i].addEventListener('click',function(){
        var group=this.getAttribute('data-tab-group');
        var target=this.getAttribute('data-tab-target');
        var panels=document.querySelectorAll('[data-tab-panel][data-tab-group="'+group+'"]');
        for(var j=0;j<panels.length;j++){panels[j].classList.remove('shown');}
        var el=document.getElementById(target);
        if(el){el.classList.add('shown');}
        var sib=document.querySelectorAll('.tab[data-tab-group="'+group+'"]');
        for(var k=0;k<sib.length;k++){sib[k].classList.remove('active');}
        this.classList.add('active');
      });
    }
    /* Expand / collapse -- toggles visibility only; data gaps live outside these. */
    var heads=document.querySelectorAll('[data-collapse-target]');
    for(var m=0;m<heads.length;m++){
      heads[m].addEventListener('click',function(){
        var el=document.getElementById(this.getAttribute('data-collapse-target'));
        if(el){el.classList.toggle('collapsed');}
      });
    }
  });
})();
"""
