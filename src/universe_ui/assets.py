"""Static local assets for the Universe UI (IMPLEMENTATION-010A).

Two deterministic strings only:

* :data:`COSMIC_CSS` -- an executive, sci-fi command-center stylesheet (cosmic dark
  background, luminous galaxy/planet/star nodes, heat/urgency indicators, evidence
  and source-authority badges, red-team / black-hole markers, data-gap warnings).
* :data:`NAV_JS` -- navigation-ONLY JavaScript. It attaches click listeners (via
  ``addEventListener``, never inline ``onclick``) that toggle tab visibility and
  expand/collapse panels, and nothing else. It contains NO ``fetch`` / ``XMLHttpRequest``
  / live call and NO action-taking affordance.
  It can only switch views, scroll, and drive CSS zoom transitions -- it can never
  hide a data gap (gaps are always rendered outside any collapsible region).

Both are emitted as local assets (``assets/universe.css`` / ``assets/universe.js``)
and are also inlined so every page is self-contained. Local assets only -- no CDN,
no remote font, no network reference of any kind.
"""

from __future__ import annotations

COSMIC_CSS = """
:root{
  /* --- 010A-S design system: near-black indigo base, glass surfaces --- */
  --bg:#060814; --bg2:#0a0e1e; --panel:#0e1330; --panel2:#131a3d;
  --glass:rgba(18,24,48,.55); --glass-line:rgba(140,160,255,.14);
  --ink:#eef2ff; --muted:#9aa6d6; --faint:#5c6690; --line:#26315f;
  /* restrained, purposeful accents: colour == meaning */
  --accent:#8b7bff; --cyan:#4fe0ff;
  --heat-hot:#ff5d3b; --heat-warm:#ffb03a; --heat-cool:#4ad6ff; --heat-dim:#5b6690;
  --good:#39e0a0; --confirmed:#39e0a0; --warn:#ffb03a; --bad:#ff4d6d; --hazard:#ff4d6d;
  --badge:#1b234d;
  --mono:ui-monospace,"SF Mono",Menlo,"Cascadia Code",Consolas,monospace;
  --shadow:0 10px 40px rgba(0,0,0,.45);
  --r-sm:10px; --r:14px; --r-lg:18px;
}
.micro{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  color:var(--faint)}
.num,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:0}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);
  background:
    radial-gradient(1100px 650px at 18% -8%, #1a2350 0%, rgba(6,8,20,0) 55%),
    radial-gradient(900px 600px at 92% 8%, #241a4a 0%, rgba(6,8,20,0) 52%),
    var(--bg);
  line-height:1.5; letter-spacing:.1px; font-size:13px;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1200px;margin:0 auto;padding:0 1.25rem 4rem}

/* ---- persistent status strip (never collapsible) ---- */
.status-strip{
  position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:.42rem;
  background:rgba(8,11,26,.84);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-bottom:1px solid var(--glass-line);
  color:var(--muted);font-size:12px;font-weight:700;
  padding:.42rem 1.25rem;letter-spacing:.2px;
}
.status-brand-mini{color:#fff;font-weight:900;letter-spacing:.45px;margin-right:.35rem}
.status-chip{display:inline-flex;align-items:center;min-height:22px;padding:.1rem .55rem;
  border:1px solid rgba(150,170,255,.16);border-radius:999px;
  background:rgba(20,27,56,.72);color:#cbd5ff;white-space:nowrap}
.status-chip.mode{border-color:rgba(255,207,138,.28);color:#ffcf8a;background:rgba(45,30,13,.62)}
.status-chip.off,.status-chip.disabled{color:#aeb9e8}
.status-chip.manual{border-color:rgba(57,224,160,.25);color:#8dffc9;background:rgba(14,42,30,.5)}

/* ---- top command bar / nav ---- */
.command-bar{
  display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;
  padding:1rem 1.25rem .4rem;max-width:1200px;margin:0 auto;
}
.brand{font-size:1.15rem;font-weight:800;letter-spacing:.5px;margin-right:1rem}
.brand small{display:block;font-size:.68rem;font-weight:600;color:var(--muted);letter-spacing:1.5px}
.navlink{
  padding:.4rem .85rem;border:1px solid var(--glass-line);border-radius:999px;
  background:var(--glass);backdrop-filter:blur(10px);color:var(--muted);
  font-size:12px;font-weight:600;letter-spacing:.2px;
}
.navlink:hover{color:var(--ink);border-color:var(--cyan);text-decoration:none}
.navlink.here{color:#fff;border-color:var(--cyan);background:rgba(79,224,255,.12)}

h1{font-size:30px;letter-spacing:-.6px;margin:.4rem 0 .25rem;font-weight:800}
h2{font-size:20px;letter-spacing:-.2px;margin:1.4rem 0 .5rem;border-bottom:1px solid var(--line);padding-bottom:.35rem}
h3{font-size:15px;margin:.9rem 0 .35rem;color:#dfe6ff;font-weight:700}
h4{font-size:11px;margin:.7rem 0 .3rem;color:var(--faint);text-transform:uppercase;letter-spacing:1.5px}
.lead{color:var(--muted);max-width:74ch;font-size:13px}

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
  position:relative;background:var(--glass);
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border:1px solid var(--glass-line);border-radius:var(--r);padding:1rem 1.1rem;
  box-shadow:var(--shadow);
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.card::before{content:"";position:absolute;left:0;right:0;top:0;height:1px;
  border-radius:var(--r) var(--r) 0 0;
  background:linear-gradient(90deg,transparent,rgba(180,200,255,.28),transparent)}
.card:hover{transform:translateY(-3px);border-color:var(--cyan);
  box-shadow:0 16px 50px rgba(0,0,0,.5)}
.card .title{font-size:15px;font-weight:800;margin:0 0 .2rem;letter-spacing:-.2px}
.card .sub{color:var(--muted);font-size:12px;margin:0 0 .5rem}

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
/* visual-size orb: SIZE = economic magnitude; GLOW = status */
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

/* ---- one zoomable cosmos canvas ---- */
.cosmos{display:grid;grid-template-columns:1fr 320px;gap:1rem;align-items:start}
@media(max-width:900px){.cosmos{grid-template-columns:1fr}}
.breadcrumb{display:flex;flex-wrap:wrap;align-items:center;gap:.2rem;
  background:#0a0f24;border:1px solid var(--line);border-radius:999px;
  padding:.45rem .9rem;font-size:.82rem;font-weight:600;margin:.2rem 0 .6rem}
.breadcrumb .crumb{color:#9fb0ff}
.breadcrumb .crumb:last-child{color:#fff}
.crumb-sep{color:#465086}
.zoom-controls{display:flex;align-items:center;gap:.8rem;margin:0 0 .8rem}
.zoom-ctrl{padding:.35rem .8rem;border:1px solid var(--line);border-radius:8px;
  background:var(--panel);color:#cdd6ff;font-size:.82rem;font-weight:700;cursor:pointer}
.zoom-ctrl:hover{border-color:var(--accent);text-decoration:none}
.hint{color:var(--muted);font-size:.78rem}
.level-head{font-size:.72rem;letter-spacing:1.5px;text-transform:uppercase;color:#7f8bc0;margin:0 0 .4rem}
.object-detail{display:none}
.detail-panel{position:sticky;top:64px;background:linear-gradient(160deg,#0c1130,#141a3d);
  border:1px solid var(--line);border-radius:14px;padding:1rem}
.detail-panel h3{margin:0 0 .5rem}
.detail-body .badge{margin-bottom:.3rem}
.minimap{margin-top:.8rem;font-size:.74rem;color:var(--muted)}

/* ---- two-pane: dominant top canvas + dynamic bottom intelligence pane ---- */
.cosmos-vertical{display:flex;flex-direction:column;gap:1rem}
.top-canvas{position:relative;border:1px solid var(--glass-line);border-radius:var(--r-lg);
  overflow:hidden;box-shadow:var(--shadow)}
.intel-pane{background:var(--glass);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border:1px solid var(--glass-line);border-radius:var(--r-lg);padding:1rem 1.2rem;
  max-height:44vh;overflow:auto;box-shadow:var(--shadow)}
.intel-pane h3{margin-top:0}
.intel-pane .badge{margin-bottom:.3rem}
.heatbar{display:inline-block;width:34px;height:9px;border-radius:5px;vertical-align:middle;
  background:#39406e}
.heatbar.g3{background:linear-gradient(90deg,#ff8a3a,#ff5d3b)}
.heatbar.g2{background:linear-gradient(90deg,#ffd15a,#ffb03a)}
.heatbar.g1{background:#4a5686}

/* value-chain flow diagram */
.flow-diagram{display:flex;flex-wrap:wrap;align-items:stretch;gap:.4rem;margin:.5rem 0}
.flow-node{background:#101636;border:1px solid var(--line);border-radius:10px;padding:.5rem .6rem;
  min-width:150px;max-width:220px;font-size:.78rem}
.flow-node b{color:#cdd6ff}
.flow-node .fn-line{color:var(--muted);margin-top:.15rem}
.flow-arrow{align-self:center;color:#6b78b8;font-weight:800;font-size:1.1rem}

/* bottleneck diagram */
.bottleneck-diagram{display:grid;grid-template-columns:1fr auto 1fr;gap:.7rem;align-items:center;margin:.5rem 0}
.bd-core{background:#2a0d17;border:1px solid var(--hazard);border-radius:12px;padding:.7rem .8rem;text-align:center}
.bd-core b{color:#ff9db4}
.bd-side{background:#101636;border:1px solid var(--line);border-radius:12px;padding:.6rem .7rem}
.bd-side.beneficiaries{border-color:#1f6b45}
.bd-side.losers{border-color:#7a2f44}
.bd-side h4{margin-top:0}
@media(max-width:700px){.bottleneck-diagram{grid-template-columns:1fr}}
.cockpit-link a{font-weight:700}

/* ==================================================================== */
/* IMMERSIVE DEEP-SPACE SCENE (top canvas). CSS-only motion; no random.  */
/* ==================================================================== */
/* Intel is data-only: it lives in the hidden store + bottom pane, NEVER the canvas */
.intel-template{display:none !important}
.intel-store{display:none}
.scene-caption{display:none}
/* top canvas ~60vh dominant; background is CSS layers only (no star divs) */
.viewport{position:relative;overflow:hidden;height:60vh;border:0;padding:0;
  cursor:grab;touch-action:none;
  background:
    radial-gradient(80% 60% at 45% 42%,rgba(32,25,80,.34),transparent 70%),
    linear-gradient(180deg,#050713,#010208 80%)}
.viewport.grabbing{cursor:grabbing}
/* the pan/zoom transform layer -- JS applies translate()+scale() to the ACTIVE one */
.scene-transform{position:absolute;inset:0;transform-origin:center center;
  transition:transform .12s ease;will-change:transform}
/* deep-space backdrop: a soft galactic glow + one tiled star texture + nebulae + vignette */
.space-glow{position:absolute;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(58% 44% at 38% 30%, rgba(130,120,255,.20), rgba(6,8,20,0) 70%),
    radial-gradient(52% 42% at 74% 70%, rgba(70,150,220,.13), rgba(6,8,20,0) 72%)}
.space-stars{position:absolute;inset:0;z-index:0;pointer-events:none;opacity:.55;
  background-image:
    radial-gradient(1px 1px at 24px 32px, rgba(255,255,255,.75), transparent),
    radial-gradient(1px 1px at 88px 120px, rgba(200,220,255,.6), transparent),
    radial-gradient(1.4px 1.4px at 150px 60px, rgba(255,255,255,.5), transparent),
    radial-gradient(1px 1px at 190px 170px, rgba(220,230,255,.5), transparent),
    radial-gradient(1px 1px at 250px 100px, rgba(255,245,225,.45), transparent);
  background-size:280px 280px;background-repeat:repeat}
.nebula{position:absolute;border-radius:50%;filter:blur(80px);pointer-events:none;z-index:0}
.neb-1{width:48%;height:54%;left:-10%;top:-14%;opacity:.34;
  background:radial-gradient(circle,#7b3ff2 0%,rgba(123,63,242,0) 66%)}
.neb-2{width:56%;height:58%;right:-14%;top:16%;opacity:.24;
  background:radial-gradient(circle,#2f6bd0 0%,rgba(47,107,208,0) 66%)}
.vignette{position:absolute;inset:0;z-index:1;pointer-events:none;
  box-shadow:inset 0 0 220px 80px rgba(0,0,0,.82)}

.scene-layer{position:absolute;inset:0;z-index:8;opacity:0;transition:opacity .32s ease}
.scene-layer.active{opacity:1}
/* Connector SVGs are intentionally not emitted in the immersive canvas. */
.scene-caption{position:absolute;left:1rem;top:.7rem;z-index:6;max-width:64%}
.scene-caption h2{margin:.1rem 0;font-size:1.1rem;text-shadow:0 2px 14px #000}
.scene-caption .level-head{margin:0}
.scene-bodies{position:absolute;inset:0;z-index:3}

/* a cosmic body positioned in space (absolute; NOT a grid card) */
.cosmic-object{position:absolute;transform:translate(-50%,-50%);cursor:pointer;
  text-align:center;z-index:3}
.cosmic-object:hover{z-index:9}
.cosmic-object:focus-visible{outline:2px solid var(--cyan);outline-offset:8px;border-radius:999px;z-index:10}
.cosmic-object .body{position:relative;margin:0 auto;border-radius:50%;
  transition:box-shadow .2s ease,transform .2s ease}
.cosmic-object:hover .body{transform:scale(1.16)}
.cosmic-object.ev-low{opacity:.72}.cosmic-object.ev-sparse{opacity:.5}
.cosmic-object.magnitude-missing .body{outline:none!important}
/* persistent SELECTED state: a cyan accent halo ring */
.cosmic-object.selected .body:not(.image-body){box-shadow:0 0 0 2px var(--cyan),0 0 26px 8px rgba(79,224,255,.5)}
.cosmic-object.selected .body-label{color:#fff;border-color:var(--cyan)}

/* name chip under the body (clean, legible) */
.body-label{margin-top:.5rem;font-size:11px;font-weight:700;color:#e9edff;letter-spacing:.2px;
  position:relative;white-space:nowrap;display:inline-block;
  background:rgba(8,11,26,.72);border:1px solid var(--glass-line);border-radius:999px;
  padding:.12rem .55rem;text-shadow:0 1px 4px #000}
/* floating PREVIEW chip on hover (name + 2-3 stats) */
.body-tip{display:none;position:absolute;left:50%;top:150%;transform:translateX(-50%);
  background:rgba(10,14,32,.92);backdrop-filter:blur(10px);
  border:1px solid var(--glass-line);border-radius:var(--r-sm);padding:.5rem .65rem;
  width:236px;font-weight:600;font-size:11px;color:#cdd6ff;white-space:normal;
  letter-spacing:.1px;box-shadow:var(--shadow);z-index:30}
.body-tip b{color:#eaf6ff;font-family:var(--mono)}
.body-tip .badge{margin:.12rem .15rem;font-size:10px}
.cosmic-object:hover .body-tip{display:block}

/* GLOW tiers (brightness = heat/status) */
.glow-3 .body{box-shadow:0 0 34px 10px rgba(255,150,90,.55),0 0 12px 3px rgba(255,230,190,.7)}
.glow-2 .body{box-shadow:0 0 24px 7px rgba(255,210,120,.42)}
.glow-1 .body{box-shadow:0 0 14px 4px rgba(150,170,230,.32)}

/* GALAXY = luminous spiral disc with a bright core + faint arms + slow rotation */
.body-galaxy .body{
  background:radial-gradient(circle at 50% 50%,#fff 0%,#ffe9b8 12%,#ffb454 26%,
    rgba(180,90,220,.5) 52%,rgba(90,70,200,.18) 74%,rgba(20,16,60,0) 100%);
  filter:drop-shadow(0 0 18px rgba(200,140,255,.5));animation:spin 90s linear infinite}
.body-galaxy .body::before{content:"";position:absolute;inset:-18%;border-radius:50%;
  background:conic-gradient(from 0deg,rgba(255,255,255,.28),rgba(120,90,255,0) 30%,
    rgba(255,180,120,.22) 55%,rgba(120,90,255,0) 78%,rgba(255,255,255,.28));
  filter:blur(6px);opacity:.7}
@keyframes spin{to{transform:rotate(360deg)}}

/* PLANET = lit sphere (upper-left light) + halo; hot ones gently pulse */
.body-planet .body{
  background:radial-gradient(circle at 34% 30%,#dbe6ff 0%,#7d90d8 32%,#3a4790 62%,#1a2054 100%)}
.body-planet.glow-3 .body{animation:pulse 4.2s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 30px 8px rgba(255,160,100,.5)}
  50%{box-shadow:0 0 46px 16px rgba(255,190,130,.72)}}
.body-planet .body::after{content:"";position:absolute;left:-32%;right:-32%;top:44%;height:14%;
  border-radius:50%;border:1px solid rgba(180,200,255,.28);transform:rotate(-16deg)}

/* STAR / bottleneck = bright point + strong bloom + cross-flare */
.body-star .body{background:radial-gradient(circle,#ffffff 0%,#ffe6a8 32%,#ff9a3c 66%,rgba(255,120,40,0) 100%);
  box-shadow:0 0 40px 12px rgba(255,180,90,.6)}
.body-star .body::before,.body-star .body::after{content:"";position:absolute;left:50%;top:50%;
  background:linear-gradient(rgba(255,235,190,0),rgba(255,235,190,.85),rgba(255,235,190,0))}
.body-star .body::before{width:2px;height:260%;transform:translate(-50%,-50%)}
.body-star .body::after{width:260%;height:2px;transform:translate(-50%,-50%)}

/* NEBULA = soft large blurred colored cloud (weak-signal / emerging / value-chain) */
.body-nebula .body,.variant-nebula .body{
  background:radial-gradient(circle,rgba(120,200,255,.55) 0%,rgba(160,90,230,.32) 45%,
    rgba(60,40,120,0) 78%);
  filter:blur(6px);box-shadow:0 0 40px 16px rgba(120,150,255,.28);border-radius:48% 52% 55% 45%}

/* COMET = catalyst: bright head + gradient tail */
.variant-comet .body::before{content:"";position:absolute;right:60%;top:38%;width:180%;height:22%;
  border-radius:50%;transform:rotate(8deg);
  background:linear-gradient(90deg,rgba(180,220,255,0),rgba(180,220,255,.7));filter:blur(3px)}

/* BLACK HOLE = severe risk: dark core ringed by red accretion glow */
.variant-blackhole .body{background:radial-gradient(circle,#000 0%,#0a0206 46%,#3a0a16 60%,rgba(58,10,22,0) 100%);
  box-shadow:0 0 30px 6px rgba(255,40,90,.6),inset 0 0 12px 2px #000}
.variant-blackhole .body::before{content:"";position:absolute;inset:-26%;border-radius:50%;
  border:2px solid rgba(255,60,100,.55);filter:blur(2px)}
.redshadow .body{box-shadow:0 0 28px 8px rgba(255,46,99,.5)}

/* MOON = tiny pale sphere */
.body-moon .body{background:radial-gradient(circle at 36% 32%,#e8ecff,#8b93c0 60%,#41476e 100%)}
.cosmic-object:hover .body{filter:brightness(1.18) saturate(1.05)}

/* ==================================================================== */
/* Executive chrome: canvas bar, legend, briefing cards, dashboard glass */
/* ==================================================================== */
.canvas-bar{position:absolute;top:0;left:0;right:0;z-index:12;display:flex;
  align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap;
  padding:.7rem .9rem;
  background:linear-gradient(180deg,rgba(6,8,20,.75),rgba(6,8,20,0));
  -webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}
.breadcrumb{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem;
  background:rgba(10,14,32,.6);border:1px solid var(--glass-line);border-radius:999px;
  padding:.4rem .9rem;font-size:12px;font-weight:600;margin:0;letter-spacing:.2px}
.breadcrumb .crumb{color:var(--cyan)}
.breadcrumb .crumb:last-child{color:#fff}
.crumb-sep{color:var(--faint)}
.zoom-controls{display:flex;align-items:center;gap:.4rem;margin:0}
.zoom-ctrl{padding:.32rem .7rem;border:1px solid var(--glass-line);border-radius:var(--r-sm);
  background:rgba(10,14,32,.6);color:#cdd6ff;font-size:12px;font-weight:700;cursor:pointer;
  font-family:var(--mono)}
.zoom-ctrl:hover{border-color:var(--cyan);color:#fff;text-decoration:none}
.hint{color:var(--faint);font-size:11px;letter-spacing:.3px}

/* legend card (corner, collapsible) */
.legend{position:absolute;right:.9rem;bottom:.9rem;z-index:12;width:210px;
  background:var(--glass);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px);
  border:1px solid var(--glass-line);border-radius:var(--r);box-shadow:var(--shadow);
  overflow:hidden;font-size:11px}
.legend-head{display:flex;align-items:center;justify-content:space-between;cursor:pointer;
  padding:.5rem .7rem;user-select:none}
.lg-toggle{color:var(--faint)}
.legend-body{padding:.2rem .7rem .6rem;display:grid;gap:.28rem}
.legend-body.collapsed{display:none}
.lg-row{display:flex;justify-content:space-between;gap:.6rem;color:var(--muted)}
.lg-key{color:#cdd6ff;font-weight:700}
.lg-val{color:var(--faint);text-align:right}

/* executive briefing (bottom pane) */
.brief-header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;
  flex-wrap:wrap;padding-bottom:.6rem;margin-bottom:.6rem;
  border-bottom:1px solid var(--glass-line)}
.brief-eyebrow{margin-bottom:.15rem}
.brief-title{margin:0;font-size:20px;letter-spacing:-.3px;color:#fff}
.brief-badges{display:flex;flex-wrap:wrap;gap:.2rem;align-items:flex-start;justify-content:flex-end}
.brief-card{background:rgba(12,16,36,.5);border:1px solid var(--glass-line);
  border-radius:var(--r);padding:.7rem .85rem;margin:.55rem 0}
.brief-card.risk{border-color:rgba(255,77,109,.28);background:rgba(42,13,23,.35)}
.brief-label{margin-bottom:.4rem;color:var(--faint)}
.brief-body p{margin:.25rem 0}
.cockpit-cta-wrap{margin:.4rem 0 .2rem}
.cockpit-cta{display:inline-block;font-weight:800;font-size:13px;color:#04121a;
  background:linear-gradient(180deg,#7ff0ff,#3fc6e6);border-radius:999px;
  padding:.45rem 1rem;box-shadow:0 6px 22px rgba(79,224,255,.3)}
.cockpit-cta:hover{text-decoration:none;filter:brightness(1.06)}
.timeline{display:flex;flex-wrap:wrap;gap:.35rem;margin:.3rem 0}
.tl-chip{font-size:11px;font-weight:600;color:#dfe6ff;background:rgba(79,224,255,.08);
  border:1px solid rgba(79,224,255,.22);border-radius:999px;padding:.18rem .6rem}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
@media(max-width:640px){.cols{grid-template-columns:1fr}}
.kv td,.chain td.num,.chain th.num,td.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.chain .num{text-align:right}

/* dashboard executive cards get a status accent rail */
.bucket .card{border-left:3px solid var(--glass-line)}
.legend-body,.brief-card,.tl-chip,.cockpit-cta{will-change:auto}

/* ==================================================================== */
/* 010A-S2: distinct levels, milky-way body, flow, bottleneck, previews  */
/* ==================================================================== */
/* each zoom level reads distinctly at a glance (left accent rail + hue tint) */
.level-universe{--lvl:#8b7bff}
.level-galaxy{--lvl:#b07bff}
.level-theme{--lvl:#7b9cff}
.level-valuechain{--lvl:#4fe0ff}
.level-star{--lvl:#ffb03a}
.level-planet{--lvl:#39e0a0}
.scene-layer::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
  background:var(--lvl);opacity:.7;z-index:6;pointer-events:none}
.scene-layer::after{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;opacity:.5;
  background:radial-gradient(70% 55% at 50% 42%,color-mix(in srgb,var(--lvl) 12%,transparent),transparent 72%)}
.level-valuechain .scene-transform{--flowhint:1}

/* MILKY WAY / GALAXY BAND (mega theme) = the infinity-shaped galaxy body the user
   recognizes as the top-level Mega Theme Galaxy. */
.body-milkyway .body{
  background:radial-gradient(circle at 50% 50%,#ffffff 0%,#bcdcff 15%,
    rgba(120,140,255,.42) 42%,rgba(60,50,160,.14) 70%,rgba(20,16,60,0) 100%);
  filter:drop-shadow(0 0 14px rgba(140,160,255,.45))}
.body-milkyway .body::before{content:"";position:absolute;inset:-8% -32%;border-radius:50%;
  border:1px solid rgba(150,180,255,.4);transform:rotate(-18deg)}
.body-milkyway .body::after{content:"";position:absolute;inset:34%;border-radius:50%;
  background:#fff;box-shadow:0 0 10px 3px rgba(200,220,255,.7)}

/* THEME CLOUD = concentrated local star cloud inside a Mega Theme Galaxy. */
.body-themecloud .body{
  border-radius:48% 52% 50% 50%;
  background:
    radial-gradient(circle at 50% 48%,#fff 0%,#dff0ff 8%,transparent 13%),
    radial-gradient(circle at 38% 42%,rgba(255,255,255,.72) 0 1px,transparent 2px),
    radial-gradient(circle at 62% 55%,rgba(214,228,255,.68) 0 1px,transparent 2px),
    radial-gradient(ellipse at 50% 50%,rgba(130,175,255,.46) 0%,rgba(82,92,210,.2) 58%,transparent 76%);
  filter:drop-shadow(0 0 16px rgba(120,165,255,.38))}
.body-themecloud .body::before{content:"";position:absolute;inset:22% -20%;border-radius:50%;
  background:linear-gradient(90deg,transparent,rgba(190,215,255,.28),transparent);
  transform:rotate(-12deg);filter:blur(.4px)}
.body-themecloud .body::after{content:"";position:absolute;inset:40%;border-radius:50%;
  background:#fff;box-shadow:0 0 8px 2px rgba(210,230,255,.62)}

/* small orbiting evidence/catalyst/risk markers around the galaxy band center */
.body-milkyway.halo .body{box-shadow:0 0 0 1px rgba(181,101,29,.5),0 0 22px rgba(181,101,29,.3)}

/* Value-chain meaning appears through local celestial placement and the briefing panel. */

/* small node marker label above a flow node */
.body-marker{position:absolute;left:50%;top:-1.35rem;transform:translateX(-50%);
  white-space:nowrap;color:#ffd79a;font-size:10px;text-shadow:0 1px 4px #000;z-index:5}

/* BOTTLENECK STAR central + DOMINANT (glow/rays, not by faking magnitude size) */
.bottleneck-central{z-index:8}
.bottleneck-central .body{
  box-shadow:0 0 64px 22px rgba(255,180,90,.55),0 0 0 2px rgba(255,210,140,.55)}
.bottleneck-central .body::after{content:"";position:absolute;inset:-70%;border-radius:50%;
  border:1px dashed rgba(255,200,120,.42);animation:scarce 16s linear infinite}
.bottleneck-central .body-marker{color:#ffcf8a;font-weight:800}
@keyframes scarce{to{transform:rotate(360deg)}}

/* candidate planet HOVER SUMMARY (compact) */
.pv-name{font-size:12px;color:#fff;margin-bottom:.28rem}
.pv-name b{font-family:var(--mono)}
.pv-row{display:flex;justify-content:space-between;gap:.7rem;color:var(--muted);
  font-size:11px;padding:.05rem 0}
.pv-row span{color:var(--faint)}
.pv-row b{color:#eaf0ff;text-align:right;font-family:var(--mono);font-weight:600}
.pv-foot{margin-top:.32rem;color:var(--faint);font-size:10px}

/* five-line EXECUTIVE HEADER (bottom pane opens with this) */
.exec-header{display:grid;gap:.3rem;margin:0 0 .75rem;padding:.75rem .85rem;
  background:linear-gradient(160deg,rgba(79,224,255,.06),rgba(139,123,255,.07));
  border:1px solid var(--glass-line);border-radius:var(--r)}
.exec-line{display:grid;grid-template-columns:158px 1fr;gap:.7rem;align-items:baseline}
@media(max-width:640px){.exec-line{grid-template-columns:1fr}}
.exec-frame{color:var(--cyan)}
.exec-text{color:#e2e9ff;font-size:12.5px;line-height:1.4}

/* ==================================================================== */
/* 010A-SKY: immersive full-screen telescope HERO; intel pane below fold  */
/* ==================================================================== */
/* the page SCROLLS naturally (no overflow lock); the HERO is the first full
   screen -- the universe -- and the intelligence pane lives BELOW the fold. */
body.sky{min-height:100vh;overflow-x:hidden}
body.sky .command-bar{max-width:none;width:100%;padding:.4rem 1rem .3rem}
/* HERO = the universe telescope view, sized to the first viewport minus header */
.universe-hero{position:relative;width:100%;height:calc(100vh - 92px);
  min-height:560px;padding:0 .6rem .2rem}
.universe-hero .top-canvas{position:relative;height:100%;width:100%}
.universe-hero .top-canvas .viewport{height:100%}
/* the intelligence pane sits BELOW the fold as a SECOND full-screen section:
   full width, at least one viewport tall, natural scroll */
.intel-section{width:100%;max-width:none;min-height:100vh;margin:0;
  padding:1.6rem clamp(1rem,4vw,3rem) 3rem;max-height:none;overflow:visible;
  border-radius:0;border-top:1px solid var(--glass-line);box-shadow:none}
/* keep long-form briefing text readable inside the full-width section */
.intel-section .detail-body{max-width:1180px;margin:0 auto}

/* --- telescopic deep-field background (parallax-able .sky-bg wrapper) --- */
.sky-bg{position:absolute;inset:-12%;z-index:0;pointer-events:none;
  transform-origin:center center;will-change:transform}
.sky-bg .space-glow{position:absolute;inset:0;
  background:
    radial-gradient(46% 34% at 40% 30%, rgba(150,140,255,.24), rgba(6,8,20,0) 70%),
    radial-gradient(40% 32% at 72% 66%, rgba(80,160,230,.16), rgba(6,8,20,0) 72%),
    radial-gradient(70% 60% at 50% 50%, rgba(30,22,70,.5), rgba(6,8,20,0) 80%)}
/* three tiled star layers (far/mid/near) for depth -- no per-star DOM */
.star-far,.star-mid,.star-near{position:absolute;inset:0;background-repeat:repeat}
.star-far{opacity:.5;background-size:340px 340px;background-image:
  radial-gradient(0.8px 0.8px at 40px 60px,rgba(255,255,255,.55),transparent),
  radial-gradient(0.8px 0.8px at 180px 220px,rgba(200,220,255,.45),transparent),
  radial-gradient(0.7px 0.7px at 280px 120px,rgba(255,245,225,.4),transparent)}
.star-mid{opacity:.7;background-size:260px 260px;background-image:
  radial-gradient(1.1px 1.1px at 24px 32px,rgba(255,255,255,.8),transparent),
  radial-gradient(1.2px 1.2px at 150px 60px,rgba(210,225,255,.7),transparent),
  radial-gradient(1px 1px at 200px 190px,rgba(255,240,220,.6),transparent)}
.star-near{opacity:.95;background-size:200px 200px;background-image:
  radial-gradient(1.7px 1.7px at 60px 80px,rgba(255,255,255,.95),transparent),
  radial-gradient(1.5px 1.5px at 150px 150px,rgba(190,220,255,.8),transparent)}
.sky-bg .nebula{position:absolute;border-radius:50%;filter:blur(90px);opacity:.3}
.sky-bg .neb-1{width:46%;height:52%;left:-8%;top:-12%;
  background:radial-gradient(circle,#7b3ff2 0%,rgba(123,63,242,0) 66%)}
.sky-bg .neb-2{width:54%;height:56%;right:-12%;top:14%;opacity:.22;
  background:radial-gradient(circle,#2f6bd0 0%,rgba(47,107,208,0) 66%)}
.sky-bg .neb-3{width:40%;height:44%;left:30%;bottom:-10%;opacity:.18;
  background:radial-gradient(circle,#e0518a 0%,rgba(224,81,138,0) 66%)}
/* a dark dust-lane silhouette across the field (depth cue) */
.dust-lane{position:absolute;left:-10%;right:-10%;top:52%;height:26%;
  transform:rotate(-11deg);filter:blur(30px);opacity:.6;
  background:linear-gradient(90deg,rgba(4,4,12,0),rgba(4,4,12,.85) 45%,rgba(4,4,12,0))}
/* softer vignette so it frames without overpowering the economic objects */
.universe-hero .vignette{box-shadow:inset 0 0 260px 60px rgba(0,0,0,.72)}

/* --- floating selected-object PREVIEW card (inside the hero) --- */
.floating-preview{position:absolute;left:1rem;top:3.4rem;z-index:14;width:288px;
  background:var(--glass);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);
  border:1px solid var(--glass-line);border-radius:var(--r-lg);box-shadow:var(--shadow);
  padding:.8rem .9rem;transition:opacity .2s ease,transform .2s ease}
.floating-preview.dismissed{opacity:0;pointer-events:none;transform:translateY(-6px)}
.fp-head{display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.fp-type{color:var(--cyan)}
.fp-close{color:var(--faint);font-size:16px;line-height:1;font-weight:700}
.fp-close:hover{color:#fff;text-decoration:none}
.fp-title{margin:.2rem 0 .4rem;font-size:16px;letter-spacing:-.2px;color:#fff}
.fp-body{font-size:11.5px;color:#cdd6ff}
.fp-body b{font-family:var(--mono);color:#eaf6ff}
.fp-body .pv-row{display:flex;justify-content:space-between;gap:.7rem;padding:.05rem 0}
.fp-body .pv-row span{color:var(--faint)}
.fp-actions{display:flex;gap:.4rem;margin-top:.6rem;flex-wrap:wrap}
.fp-btn{font-size:11px;font-weight:700;color:#04121a;
  background:linear-gradient(180deg,#7ff0ff,#3fc6e6);border-radius:999px;padding:.32rem .7rem}
.fp-btn:hover{text-decoration:none;filter:brightness(1.06)}
#fp-zoom{color:#dfe6ff;background:rgba(79,224,255,.1);border:1px solid rgba(79,224,255,.28)}
@media(max-width:620px){.floating-preview{width:min(288px,86vw)}}

/* ==================================================================== */
/* 010A-FIX: no false universe centre; panoramic L0 field; no visible graph lines */
/* ==================================================================== */
/* full-width app shell for the Universe Canvas page */
.universe-app{width:100vw;max-width:none}
/* the UNIVERSE (L0) field is WIDER than the viewport -> the user pans across space.
   Galaxies float here with NO centre and NO visible connector graph. */
.level-universe .scene-transform{width:150%;height:126%;left:-25%;top:-13%}

/* ==================================================================== */
/* 010A-SKY-VISUAL: telescope deep-field LOCAL asset + richer bodies      */
/* ==================================================================== */
/* the LOCAL, deterministic deep-space SVG leads the backdrop; the CSS star
   layers below become a subtle parallax shimmer on top of it. */
.deep-space-bg{position:absolute;inset:0;z-index:0;pointer-events:none;
  background:#02010a url("assets/deep_space_background.svg") center center / cover no-repeat}
.star-far{opacity:.32}.star-mid{opacity:.4}.star-near{opacity:.55}
.sky-bg .nebula{opacity:.2}.sky-bg .neb-2{opacity:.16}.sky-bg .neb-3{opacity:.12}

/* GALAXY: brighter luminous core + deeper bloom */
.body-galaxy .body{filter:drop-shadow(0 0 26px rgba(210,160,255,.6))}
/* PLANET: a polished sphere -- specular highlight, terminator, thin atmosphere rim */
.body-planet .body{
  background:
    radial-gradient(circle at 30% 26%, rgba(255,255,255,.95) 0%, rgba(255,255,255,0) 18%),
    radial-gradient(circle at 36% 32%, #cfe0ff 0%, #7d90d8 34%, #38468e 64%, #141a44 100%)}
.body-planet .body::before{content:"";position:absolute;inset:-6%;border-radius:50%;
  box-shadow:inset 0 0 12px 2px rgba(120,150,255,.45),0 0 10px rgba(120,150,255,.25);
  pointer-events:none}
/* BOTTLENECK STAR: powerful, scarce -- tighter white-hot core + wide corona */
.body-star .body{box-shadow:0 0 52px 16px rgba(255,180,90,.6),0 0 16px 4px rgba(255,240,200,.8)}
/* BLACK HOLE: dangerous but not cartoonish -- desaturated void + thin red accretion */
.variant-blackhole .body{
  background:radial-gradient(circle,#000 0%,#050308 44%,#25060f 58%,rgba(37,6,15,0) 100%);
  box-shadow:0 0 26px 5px rgba(230,60,90,.5),inset 0 0 14px 3px #000}
.variant-blackhole .body::before{border-color:rgba(220,70,95,.5)}

/* ==================================================================== */
/* 010A-SKY-VISUAL-REF: data-quality control panel + EIOS layer map      */
/* ==================================================================== */
.glass-panel{background:var(--glass);-webkit-backdrop-filter:blur(14px);
  backdrop-filter:blur(14px);border:1px solid var(--glass-line);
  border-radius:var(--r-lg);box-shadow:var(--shadow);padding:1rem 1.1rem;margin:.5rem 0 1rem}
.dq-head{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap}
/* A. source-hierarchy pipeline */
.dq-pipeline{display:flex;align-items:stretch;gap:.5rem;flex-wrap:wrap}
.pipe-stage{flex:1 1 140px;min-width:118px;text-align:center;background:rgba(12,16,36,.5);
  border:1px solid var(--glass-line);border-radius:var(--r);padding:.7rem .6rem}
.pipe-name{font-weight:800;margin:.3rem 0 .1rem;font-size:13px}
.pipe-count{font-size:22px;color:#fff}
.pipe-arrow{align-self:center;color:var(--cyan);font-weight:800;font-size:1.3rem}
/* C. quality stat cards */
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:.7rem;margin:.4rem 0 1rem}
.stat-card{background:var(--glass);border:1px solid var(--glass-line);border-radius:var(--r);
  padding:.75rem .85rem;border-left:3px solid var(--glass-line);
  -webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.stat-card.auth-canonical{border-left-color:#4fe0ff}
.stat-card.auth-convenience{border-left-color:#ffb03a}
.stat-card.auth-fallback{border-left-color:#ff9db4}
.stat-card.real{border-left-color:#39e0a0}
.stat-card.warn{border-left-color:#ffb03a}
.stat-card.gap{border-left-color:#b5651d}
.stat-card.hazard{border-left-color:#ff4d6d}
.stat-n{font-size:26px;color:#fff}.stat-l{margin-top:.2rem}
/* B. source authority matrix */
table.matrix td,table.matrix th{vertical-align:middle}
.cov-bar{display:inline-block;width:80px;height:8px;border-radius:5px;background:#1a2145;
  vertical-align:middle;overflow:hidden;margin-right:.4rem}
.cov-bar span{display:block;height:100%;background:linear-gradient(90deg,#4fe0ff,#8b7bff)}
.cov-n{font-family:var(--mono);color:#cdd6ff}
.mx-flag{font-family:var(--mono);font-weight:700;padding:.05rem .4rem;border-radius:6px}
.mx-flag.warn{color:#ffd79a;background:rgba(255,176,58,.14)}
.mx-flag.gap{color:#ffbf87;background:rgba(181,101,29,.16)}
.mx-flag.hazard{color:#ff9db4;background:rgba(255,77,109,.16)}
.mx-ok{color:var(--faint)}
/* EIOS platform layer map (corrected labels; diagram colour groups) */
.layer-map .layer-rows{display:grid;gap:.3rem;margin:.5rem 0}
.layer-row{display:grid;grid-template-columns:26px 118px 1fr;gap:.7rem;align-items:center;
  padding:.34rem .5rem;border-radius:8px;background:rgba(12,16,36,.45);
  border-left:3px solid var(--glass-line)}
.layer-num{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-family:var(--mono);font-weight:800;font-size:12px;color:#04121a}
.layer-name{font-weight:800;color:#fff}
.layer-label{color:var(--muted);font-size:12px}
.grp-reason{border-left-color:#ffb03a}.grp-reason .layer-num{background:#ffb03a}
.grp-cap{border-left-color:#39e0a0}.grp-cap .layer-num{background:#39e0a0}
.grp-op{border-left-color:#4fe0ff}.grp-op .layer-num{background:#4fe0ff}
.layer-legend{color:var(--muted);font-size:11px;margin-top:.5rem}
.lg-dot{display:inline-block;width:9px;height:9px;border-radius:50%;
  margin:0 .2rem 0 .5rem;vertical-align:middle}
.lg-dot.grp-reason{background:#ffb03a}.lg-dot.grp-cap{background:#39e0a0}
.lg-dot.grp-op{background:#4fe0ff}

/* ==================================================================== */
/* COSMOSIQ-SKY-PREMIUM: deep-field seriousness + command-center polish  */
/* ==================================================================== */
body.sky{
  background:
    radial-gradient(1200px 760px at 12% -10%, rgba(55,70,150,.28), transparent 58%),
    radial-gradient(900px 620px at 92% 12%, rgba(82,44,130,.22), transparent 60%),
    linear-gradient(180deg,#050611,#02030a 70%,#050611);
}
body.sky .status-strip{
  min-height:34px;
  background:linear-gradient(180deg,rgba(7,10,24,.9),rgba(7,10,24,.68));
  border-bottom:1px solid rgba(170,190,255,.16);
  box-shadow:0 1px 0 rgba(255,255,255,.04) inset,0 14px 36px rgba(0,0,0,.28);
  color:#b9c5f3;
}
body.sky .status-strip::after{
  content:"Reality Mesh";margin-left:auto;color:#7f8bc0;font-size:10px;
  text-transform:uppercase;letter-spacing:1.4px;
}
body.sky .command-bar{
  position:sticky;top:34px;z-index:49;
  background:linear-gradient(180deg,rgba(5,7,17,.78),rgba(5,7,17,.46));
  -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
  border-bottom:1px solid rgba(170,190,255,.1);
}
body.sky .brand{display:flex;align-items:baseline;gap:.65rem;margin-right:1.2rem}
body.sky .brand small{display:inline;color:#91a0d6}
body.sky .navlink{
  background:rgba(13,18,42,.58);box-shadow:0 1px 0 rgba(255,255,255,.04) inset;
}
.universe-hero{padding:0;background:#02030a}
.universe-hero .top-canvas{
  border-radius:0;border-left:0;border-right:0;
  box-shadow:0 28px 90px rgba(0,0,0,.62),0 0 0 1px rgba(160,180,255,.08) inset;
}
.viewport{
  background:
    radial-gradient(80% 60% at 45% 42%,rgba(32,25,80,.34),transparent 70%),
    linear-gradient(180deg,#050713,#010208 80%);
}
.deep-space-bg{filter:saturate(1.08) contrast(1.04) brightness(.92)}
.star-far,.star-mid,.star-near{mix-blend-mode:screen}
.star-near{animation:cosmos-twinkle 8s ease-in-out infinite}
@keyframes cosmos-twinkle{0%,100%{opacity:.42}50%{opacity:.62}}
.dust-lane{mix-blend-mode:multiply}
.scene-layer{transition:opacity .38s ease,filter .38s ease}
.scene-layer:not(.active){pointer-events:none;filter:blur(4px) saturate(.8)}
.scene-transform{transition:transform .18s cubic-bezier(.2,.8,.2,1)}
.canvas-bar{
  padding:.85rem 1rem;background:
    linear-gradient(180deg,rgba(4,6,16,.82),rgba(4,6,16,.28) 74%,transparent);
}
.breadcrumb{
  min-height:34px;padding:.38rem .85rem .38rem 2.15rem;position:relative;
  background:rgba(8,12,28,.68);box-shadow:0 1px 0 rgba(255,255,255,.05) inset;
}
.breadcrumb::before{
  content:"You are here";position:absolute;left:.75rem;top:50%;transform:translateY(-50%);
  color:#6470a8;font-size:9px;text-transform:uppercase;letter-spacing:1.1px;
}
.breadcrumb .crumb:first-child{margin-left:3.8rem}
.zoom-ctrl{
  min-height:32px;background:rgba(9,13,30,.72);
  box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 8px 24px rgba(0,0,0,.18);
}
.hint{
  background:rgba(8,12,28,.5);border:1px solid rgba(140,160,255,.1);
  border-radius:999px;padding:.28rem .6rem;color:#8e9bd0;
}
.level-universe .scene-transform{width:172%;height:138%;left:-36%;top:-18%}
.level-universe .body-label{font-size:10px;opacity:.78;transform:translateY(2px)}
.level-universe .cosmic-object:hover .body-label,
.level-universe .cosmic-object.selected .body-label{opacity:1}
.body-label{
  max-width:190px;overflow:hidden;text-overflow:ellipsis;
  background:linear-gradient(180deg,rgba(8,11,26,.78),rgba(8,11,26,.56));
  box-shadow:0 8px 28px rgba(0,0,0,.28);
}
.cosmic-object{transition:opacity .2s ease,filter .2s ease,z-index .2s ease}
.cosmic-object:hover{filter:saturate(1.12)}
.cosmic-object .body{
  transition:box-shadow .22s ease,transform .22s ease,filter .22s ease;
  isolation:isolate;
}
.celestial-img{
  display:block;width:100%;height:100%;object-fit:contain;pointer-events:none;
  filter:drop-shadow(0 0 12px rgba(160,190,255,.42));
}
.image-body{background:none!important;border-radius:0!important;overflow:visible}
.image-body::before,.image-body::after{display:none!important}
.body-milkyway .celestial-img{transform:scale(1.04);filter:drop-shadow(0 0 22px rgba(176,150,220,.48))}
.body-themecloud .celestial-img{transform:scale(1.08);filter:drop-shadow(0 0 18px rgba(150,185,255,.42))}
.body-nebula .celestial-img{transform:scale(1.08);filter:drop-shadow(0 0 20px rgba(255,175,90,.36))}
.body-star .celestial-img{transform:scale(1.18)}
.body-planet .celestial-img{transform:scale(1.08)}
.body-moon .celestial-img{transform:scale(1.05)}
.glow-1 .image-body,.glow-2 .image-body,.glow-3 .image-body,
.redshadow .image-body,.halo .image-body,.bottleneck-central .image-body,
.variant-comet .image-body,.variant-blackhole .image-body{
  box-shadow:none!important;outline:none!important;background:transparent!important;
}
.cosmic-object.magnitude-missing .image-body{outline:none!important}
.cosmic-object.magnitude-missing .celestial-img{
  filter:drop-shadow(0 0 10px rgba(255,191,135,.5)) drop-shadow(0 0 2px rgba(255,222,190,.45));
}
.glow-3 .celestial-img{filter:drop-shadow(0 0 22px rgba(255,170,90,.55)) drop-shadow(0 0 8px rgba(255,235,190,.5))}
.glow-2 .celestial-img{filter:drop-shadow(0 0 16px rgba(255,210,120,.4))}
.glow-1 .celestial-img{filter:drop-shadow(0 0 10px rgba(150,170,230,.3))}
.redshadow .celestial-img{filter:drop-shadow(0 0 16px rgba(255,46,99,.55)) drop-shadow(0 0 5px rgba(255,140,100,.36))}
.halo .celestial-img{filter:drop-shadow(0 0 18px rgba(255,201,112,.45))}
.cosmic-object.selected .image-body{
  box-shadow:none!important;outline:none!important;background:transparent!important;
}
.cosmic-object.selected .celestial-img{
  filter:drop-shadow(0 0 18px rgba(79,224,255,.72)) drop-shadow(0 0 4px rgba(234,252,255,.9));
}
.cosmic-object.selected .body:not(.image-body){
  transform:scale(1.18);
  box-shadow:0 0 0 1px #eafcff,0 0 0 7px rgba(79,224,255,.14),
    0 0 42px 14px rgba(79,224,255,.5);
}
.cosmic-object.focus-pulse .body{animation:focus-pulse 900ms ease-out 1}
@keyframes focus-pulse{
  0%{box-shadow:0 0 0 0 rgba(79,224,255,.52)}
  100%{box-shadow:0 0 0 24px rgba(79,224,255,0)}
}
.body-galaxy .body{
  border-radius:48% 52% 50% 50%;
  background:
    radial-gradient(circle at 50% 50%,#fffdf0 0%,#ffe3a6 10%,rgba(255,176,82,.78) 20%,transparent 28%),
    conic-gradient(from 24deg,transparent 0 16%,rgba(210,190,255,.36) 18%,transparent 34%,
      rgba(255,205,150,.34) 44%,transparent 58%,rgba(150,170,255,.28) 70%,transparent 84%),
    radial-gradient(ellipse at center,rgba(164,112,230,.55) 0%,rgba(75,64,160,.22) 62%,transparent 78%);
}
.body-galaxy .body::before{
  inset:-24%;background:
    conic-gradient(from 32deg,rgba(255,245,220,.36),transparent 18%,rgba(147,159,255,.25) 42%,
      transparent 64%,rgba(255,188,132,.28) 78%,transparent);
  filter:blur(8px);opacity:.86;
}
.body-galaxy .body::after{
  content:"";position:absolute;left:-16%;right:-16%;top:46%;height:12%;
  border-radius:50%;background:linear-gradient(90deg,transparent,rgba(2,2,8,.66),transparent);
  transform:rotate(-16deg);filter:blur(3px);opacity:.72;
}
.body-milkyway .body{
  border-radius:46% 54% 50% 50%;
  background:
    radial-gradient(circle at 50% 48%,#fff 0%,#cfe5ff 9%,transparent 15%),
    radial-gradient(ellipse at 50% 50%,rgba(150,185,255,.58) 0%,rgba(105,110,220,.22) 58%,transparent 76%);
}
.body-milkyway .body::before{
  inset:20% -38%;background:
    radial-gradient(circle at 24% 50%,rgba(255,255,255,.72) 0 1px,transparent 2px),
    radial-gradient(circle at 42% 44%,rgba(210,225,255,.6) 0 1px,transparent 2px),
    radial-gradient(circle at 64% 54%,rgba(255,235,205,.56) 0 1px,transparent 2px),
    linear-gradient(90deg,transparent,rgba(170,195,255,.26),transparent);
  border:0;filter:blur(.2px);opacity:.92;
}
.body-themecloud .body{
  background:
    radial-gradient(circle at 48% 48%,#fff 0%,#dcecff 9%,transparent 15%),
    radial-gradient(circle at 34% 38%,rgba(255,255,255,.72) 0 1px,transparent 2px),
    radial-gradient(circle at 68% 46%,rgba(212,228,255,.62) 0 1px,transparent 2px),
    radial-gradient(circle at 56% 66%,rgba(255,235,205,.52) 0 1px,transparent 2px),
    radial-gradient(ellipse at 50% 50%,rgba(120,170,255,.42) 0%,rgba(86,92,210,.18) 60%,transparent 78%);
}
.body-themecloud .body::before{
  content:"";position:absolute;inset:24% -24%;border-radius:50%;
  background:linear-gradient(90deg,transparent,rgba(190,215,255,.24),transparent);
  transform:rotate(-12deg);filter:blur(.4px);opacity:.9;
}
.body-themecloud .body::after{
  content:"";position:absolute;inset:39%;border-radius:50%;
  background:#fff;box-shadow:0 0 8px 2px rgba(210,230,255,.62);
}
.body-nebula .body,.variant-nebula .body{
  background:
    radial-gradient(circle at 45% 42%,rgba(220,245,255,.72),rgba(90,180,255,.22) 36%,transparent 68%),
    radial-gradient(circle at 60% 56%,rgba(170,100,230,.32),transparent 70%);
  filter:blur(4px) saturate(1.1);
}
.body-star .body{
  background:
    radial-gradient(circle,#fff 0%,#fff6d7 14%,#ffd27d 35%,rgba(255,147,54,.72) 56%,transparent 72%);
}
.body-star .body::before{width:2px;height:320%;opacity:.9}
.body-star .body::after{width:320%;height:2px;opacity:.82}
.bottleneck-central .body{
  box-shadow:0 0 72px 26px rgba(255,183,84,.62),0 0 120px 34px rgba(255,92,59,.22),
    0 0 0 1px rgba(255,235,188,.65);
}
.body-planet .body{
  background:
    radial-gradient(circle at 28% 24%,rgba(255,255,255,.95) 0%,rgba(255,255,255,.25) 10%,transparent 21%),
    radial-gradient(circle at 36% 32%,#d9e8ff 0%,#8ca1ed 32%,#36448e 62%,#111738 100%);
}
.body-planet .body::after{
  border-color:rgba(180,210,255,.4);box-shadow:0 0 12px rgba(120,160,255,.2);
}
.halo.body-planet .body::after{border-color:rgba(255,201,112,.72);box-shadow:0 0 18px rgba(255,177,58,.38)}
.variant-comet .body{box-shadow:0 0 24px 8px rgba(180,220,255,.42)}
.variant-comet .body::before{
  width:230%;height:28%;right:58%;top:34%;
  background:linear-gradient(90deg,rgba(150,210,255,0),rgba(190,230,255,.72),rgba(255,255,255,.88));
}
.variant-blackhole .body::after{
  content:"";position:absolute;inset:-44%;border-radius:50%;
  background:conic-gradient(from 20deg,transparent,rgba(255,80,120,.5),transparent 38%,
    rgba(255,180,80,.28),transparent 70%);
  filter:blur(4px);z-index:-1;
}
.body-moon .body{
  box-shadow:inset -4px -5px 8px rgba(0,0,0,.42),0 0 12px rgba(180,190,230,.18);
}
.body-tip{
  top:140%;width:254px;padding:.65rem .72rem;
  background:linear-gradient(180deg,rgba(14,20,44,.92),rgba(8,12,28,.88));
  border:1px solid rgba(170,190,255,.2);box-shadow:0 22px 70px rgba(0,0,0,.58);
}
.floating-preview{
  width:330px;background:linear-gradient(180deg,rgba(15,22,48,.74),rgba(8,12,28,.7));
  border-color:rgba(180,205,255,.18);box-shadow:0 28px 90px rgba(0,0,0,.56);
}
.floating-preview::before{
  content:"";position:absolute;left:0;right:0;top:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(160,230,255,.55),transparent);
}
.fp-type{color:#7ff0ff}
.fp-title{font-size:17px;line-height:1.2}
.fp-body{display:grid;gap:.14rem}
.fp-body .pv-name{padding-bottom:.35rem;margin-bottom:.25rem;border-bottom:1px solid rgba(140,160,255,.14)}
.fp-actions{border-top:1px solid rgba(140,160,255,.14);padding-top:.65rem}
.fp-btn{box-shadow:0 8px 24px rgba(79,224,255,.22)}
.legend{
  width:238px;background:linear-gradient(180deg,rgba(14,20,44,.72),rgba(8,12,28,.68));
  border-color:rgba(180,205,255,.16);
}
.intel-section{
  background:
    radial-gradient(900px 520px at 16% 0%,rgba(47,107,208,.14),transparent 62%),
    linear-gradient(180deg,#050713,#070a18 40%,#050611);
}
.exec-header,.brief-card,.glass-panel,.stat-card{
  box-shadow:0 1px 0 rgba(255,255,255,.04) inset,0 18px 52px rgba(0,0,0,.22);
}
@media(prefers-reduced-motion:reduce){
  .star-near,.body-galaxy .body,.body-planet.glow-3 .body,.bottleneck-central .body::after,
  .cosmic-object.focus-pulse .body{
    animation:none !important;
  }
  .scene-transform,.scene-layer,.floating-preview{transition:none !important}
}
@media(max-width:760px){
  body.sky .brand{width:100%;gap:.45rem}
  body.sky .command-bar{top:34px}
  .universe-hero{height:calc(100vh - 126px);min-height:520px;padding:0}
  .canvas-bar{align-items:flex-start}
  .zoom-controls{max-width:100%;overflow:auto;padding-bottom:.15rem}
  .hint{display:none}
  .breadcrumb{width:100%}
  .floating-preview{left:.75rem;top:5.2rem;width:min(330px,90vw)}
  .legend{display:none}
}
"""


NAV_JS = """
/* Universe UI -- navigation-ONLY behaviour: level zoom (show/hide), breadcrumb
   push/pop, back/up, bottom Intelligence Pane swap (copies a pre-rendered .intel-template
   by id into #intel-body), hash/query deep-link focus, AND continuous view zoom+pan
   (mouse wheel / +- buttons / drag) applied as a CSS transform on the active level's
   .scene-transform. NO network, NO form, NO action-taking affordance, NO
   hidden metric, NO random, NO data mutation. It only toggles visibility, copies pre-rendered
   DOM, and transforms the view -- it can never hide a data gap. */
(function(){
  function ready(fn){
    if(document.readyState!=='loading'){fn();}
    else{document.addEventListener('DOMContentLoaded',fn);}
  }
  function clamp(v,lo,hi){return v<lo?lo:(v>hi?hi:v);}
  ready(function(){
    /* ---- one zoomable cosmos canvas (only present on universe.html) ---- */
    var panels=document.querySelectorAll('.level-panel');
    if(panels.length){
      var breadcrumb=document.getElementById('breadcrumb');
      var intelBody=document.getElementById('intel-body');
      var backBtn=document.getElementById('zoom-back');
      var viewport=document.getElementById('viewport');
      var skybg=document.querySelector('.sky-bg');
      /* floating selected-object preview (the detail pane lives below the fold) */
      var fp=document.getElementById('floating-preview');
      var fpTitle=document.getElementById('fp-title');
      var fpType=document.getElementById('fp-type');
      var fpBody=document.getElementById('fp-body');
      var fpZoom=document.getElementById('fp-zoom');
      var fpCockpit=document.getElementById('fp-cockpit');
      var fpDetails=document.getElementById('fp-details');
      var fpClose=document.getElementById('fp-close');
      var current='universe';
      var view={scale:1,tx:0,ty:0};

      function panelByPath(p){
        for(var i=0;i<panels.length;i++){
          if(panels[i].getAttribute('data-path')===p){return panels[i];}
        }
        return null;
      }
      /* copy a pre-rendered intel template (by id) into the bottom pane; if the id
         is missing show a visible fallback -- never blank, never a silent failure */
      function setIntel(id){
        if(!intelBody){return;}
        if(!id){return;}
        var el=document.getElementById(id);
        if(el){intelBody.innerHTML=el.innerHTML;}
        else{intelBody.innerHTML='<div class="brief-card risk"><p class="micro">'
          +'Missing intelligence template: '+id+'</p></div>';}
      }
      function activeTransform(){
        var a=document.querySelector('.level-panel.active .scene-transform');
        return a;
      }
      function applyTransform(){
        var el=activeTransform();
        if(el){el.style.transform='translate('+view.tx+'px,'+view.ty+'px) scale('+view.scale+')';}
        /* flat universe: sky moves with the object field, with a tiny depth offset */
        if(skybg){
          skybg.style.transform='translate('+view.tx+'px,'+view.ty+'px) scale('+view.scale+')';
          var starLayers=skybg.querySelectorAll('.star-far,.star-mid,.star-near,.deep-space-bg');
          for(var b=0;b<starLayers.length;b++){
            starLayers[b].style.backgroundPosition=(view.tx*(b+1)*0.12)+'px '+(view.ty*(b+1)*0.08)+'px';
          }
        }
      }
      /* clear any persistent .selected ring so it can never go STALE across a level
         change or view reset (level-change / zoom-back / fit-all / locate / breadcrumb).
         Visibility-only: it removes a CSS class, never hides data or mutates state. */
      function clearSelection(){
        var ss=document.querySelectorAll('.cosmic-object.selected');
        for(var q=0;q<ss.length;q++){ss[q].classList.remove('selected');}
      }
      function pulseObject(obj){
        if(!obj){return;}
        obj.classList.remove('focus-pulse');
        void obj.offsetWidth;
        obj.classList.add('focus-pulse');
      }
      function resetView(){clearSelection();view.scale=1;view.tx=0;view.ty=0;applyTransform();}
      function zoomToObject(obj,scale){
        if(!viewport||!obj){return;}
        var vr=viewport.getBoundingClientRect();
        var r=obj.getBoundingClientRect();
        var cx=(r.left+r.right)/2-vr.left-vr.width/2;
        var cy=(r.top+r.bottom)/2-vr.top-vr.height/2;
        view.scale=clamp(scale||2.2,0.6,6);
        view.tx=-cx*view.scale;
        view.ty=-cy*view.scale;
        applyTransform();
      }
      /* update the floating preview card from a clicked object (existing fields only) */
      function updatePreview(obj){
        if(!fp){return;}
        if(fpTitle){fpTitle.textContent=obj.getAttribute('data-title')||'';}
        if(fpType){fpType.textContent=(obj.getAttribute('data-kind')||'object').replace(/_/g,' ');}
        if(fpBody){var tip=obj.querySelector('.body-tip');
          fpBody.innerHTML=tip?tip.innerHTML:'';}
        fp.classList.remove('dismissed');
        var tp=obj.getAttribute('data-target-path');
        if(fpZoom){
          if(tp){fpZoom.style.display='inline-block';fpZoom.setAttribute('data-goto',tp);}
          else{fpZoom.style.display='none';fpZoom.removeAttribute('data-goto');}
        }
        /* Open cockpit only for a planet that carries a cockpit link */
        var ck=obj.getAttribute('data-cockpit');
        if(fpCockpit){
          if(ck){fpCockpit.style.display='inline-block';fpCockpit.setAttribute('href',ck);}
          else{fpCockpit.style.display='none';fpCockpit.setAttribute('href','#');}
        }
      }
      if(fpDetails){fpDetails.addEventListener('click',function(e){
        e.preventDefault();
        var pane=document.getElementById('intel-pane');
        if(pane&&pane.scrollIntoView){pane.scrollIntoView({behavior:'smooth',block:'start'});}
      });}
      if(fpClose){fpClose.addEventListener('click',function(e){
        e.preventDefault(); if(fp){fp.classList.add('dismissed');}});}
      function buildCrumb(path){
        if(!breadcrumb){return;}
        var chain=[]; var node=panelByPath(path);
        while(node){chain.unshift(node); var par=node.getAttribute('data-parent');
          node=par?panelByPath(par):null;}
        var html='';
        for(var i=0;i<chain.length;i++){
          var c=chain[i]; var lbl=c.getAttribute('data-crumb'); var p=c.getAttribute('data-path');
          if(i>0){html+=' <span class="crumb-sep">&rsaquo;</span> ';}
          html+='<a class="crumb" data-goto="'+p+'" href="#path='+p+'">'+lbl+'</a>';
        }
        breadcrumb.innerHTML=html;
      }
      function showLevel(path){
        var target=panelByPath(path); if(!target){return;}
        for(var i=0;i<panels.length;i++){panels[i].classList.remove('active');}
        target.classList.add('active');
        current=path; buildCrumb(path);
        setIntel(target.getAttribute('data-intel'));  /* level's own intel -> bottom pane */
        if(backBtn){backBtn.style.display=target.getAttribute('data-parent')?'inline-block':'none';}
        resetView();  /* reset zoom/pan when the level changes */
      }
      var objs=document.querySelectorAll('.cosmic-object');
      for(var i=0;i<objs.length;i++){
        objs[i].addEventListener('click',function(){
          for(var s=0;s<objs.length;s++){objs[s].classList.remove('selected');}
          this.classList.add('selected');       /* persistent SELECTED state */
          pulseObject(this);
          updatePreview(this);                   /* floating preview inside the hero */
          var myIntel=this.getAttribute('data-intel');
          var tp=this.getAttribute('data-target-path');
          zoomToObject(this,2.25);                /* every click visibly zooms the chosen body */
          setIntel(myIntel);                      /* bottom pane immediately shows this object */
          if(tp && panelByPath(tp)){
            showLevel(tp);                        /* descend into the object */
            view.scale=1.45; applyTransform();    /* land inside the child system already zoomed in */
          }
          /* the clicked object's OWN intel wins -- set AFTER any level change so a
             level's intel can never overwrite the explicitly selected object; the
             below-the-fold intelligence pane updates from the SAME id */
          setIntel(myIntel);
        });
        objs[i].addEventListener('keydown',function(e){
          if(e.key==='Enter' || e.key===' '){e.preventDefault();this.click();}
        });
      }
      document.addEventListener('click',function(e){
        var t=e.target;
        var goto=(t && t.getAttribute)?t.getAttribute('data-goto'):null;
        if(goto){e.preventDefault(); showLevel(goto);}
      });
      if(backBtn){
        backBtn.addEventListener('click',function(e){
          e.preventDefault();
          var cur=panelByPath(current); var par=cur?cur.getAttribute('data-parent'):null;
          if(par){showLevel(par);}
        });
      }

      /* ---- continuous view ZOOM + PAN (Google-Earth feel), all CSS transforms ---- */
      var zin=document.getElementById('zoom-in');
      var zout=document.getElementById('zoom-out');
      var zreset=document.getElementById('zoom-reset');
      if(zin){zin.addEventListener('click',function(e){e.preventDefault();
        view.scale=clamp(view.scale*1.2,0.6,6);applyTransform();});}
      if(zout){zout.addEventListener('click',function(e){e.preventDefault();
        view.scale=clamp(view.scale/1.2,0.6,6);applyTransform();});}
      if(zreset){zreset.addEventListener('click',function(e){e.preventDefault();resetView();});}
      /* Fit-to-all: frame every body in the active level within the viewport */
      var zfit=document.getElementById('zoom-fit');
      var zloc=document.getElementById('zoom-locate');
      function fitToAll(){
        resetView();
        var t=activeTransform(); if(!t||!viewport){return;}
        var os=t.querySelectorAll('.cosmic-object'); if(!os.length){return;}
        var vr=viewport.getBoundingClientRect();
        var minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9,any=false;
        for(var k=0;k<os.length;k++){var r=os[k].getBoundingClientRect();
          if(r.width===0&&r.height===0){continue;} any=true;
          minx=Math.min(minx,r.left);miny=Math.min(miny,r.top);
          maxx=Math.max(maxx,r.right);maxy=Math.max(maxy,r.bottom);}
        var bw=maxx-minx,bh=maxy-miny; if(!any||bw<=0||bh<=0){return;}
        var s=clamp(Math.min(vr.width*0.82/bw,vr.height*0.82/bh),0.6,6);
        var bcx=(minx+maxx)/2-vr.left-vr.width/2;
        var bcy=(miny+maxy)/2-vr.top-vr.height/2;
        view.scale=s;view.tx=-bcx*s;view.ty=-bcy*s;applyTransform();
      }
      /* Locate: centre + zoom to the currently selected object (or first body) */
      function locateSelected(){
        if(!viewport){return;}
        var sel=document.querySelector('.level-panel.active .cosmic-object.selected')
              ||document.querySelector('.level-panel.active .cosmic-object');
        if(!sel){return;}
        resetView();
        zoomToObject(sel,2.2);
        pulseObject(sel);
      }
      if(zfit){zfit.addEventListener('click',function(e){e.preventDefault();fitToAll();});}
      if(zloc){zloc.addEventListener('click',function(e){e.preventDefault();locateSelected();});}
      if(viewport){
        viewport.addEventListener('wheel',function(e){
          e.preventDefault();
          var rect=viewport.getBoundingClientRect();
          var cx=e.clientX-rect.left-rect.width/2;
          var cy=e.clientY-rect.top-rect.height/2;
          var factor=(e.deltaY<0)?1.12:(1/1.12);
          var ns=clamp(view.scale*factor,0.6,6);
          var k=ns/view.scale;
          view.tx=cx-k*(cx-view.tx);   /* zoom toward the cursor */
          view.ty=cy-k*(cy-view.ty);
          view.scale=ns; applyTransform();
        },{passive:false});
        var dragging=false,sx=0,sy=0,moved=false;
        viewport.addEventListener('pointerdown',function(e){
          dragging=true;moved=false;sx=e.clientX;sy=e.clientY;
          viewport.classList.add('grabbing');
          if(viewport.setPointerCapture){try{viewport.setPointerCapture(e.pointerId);}catch(_e){}}
        });
        viewport.addEventListener('pointermove',function(e){
          if(!dragging){return;}
          var dx=e.clientX-sx,dy=e.clientY-sy; sx=e.clientX; sy=e.clientY;
          if(Math.abs(dx)+Math.abs(dy)>2){moved=true;}
          view.tx+=dx;
          view.ty+=dy;
          applyTransform();
        });
        function endDrag(){if(dragging){dragging=false;viewport.classList.remove('grabbing');}}
        viewport.addEventListener('pointerup',endDrag);
        viewport.addEventListener('pointerleave',endDrag);
        /* a pan drag must not also trigger click-to-descend */
        viewport.addEventListener('click',function(e){
          if(moved){e.stopPropagation();e.preventDefault();moved=false;}
        },true);
      }

      function focusFromLocation(){
        var h=window.location.hash||''; var q=window.location.search||''; var path=null;
        var m=h.match(/(?:focus|path)=([^&]+)/); if(m){path=decodeURIComponent(m[1]);}
        if(!path){var mq=q.match(/focus=([^&]+)/); if(mq){path=decodeURIComponent(mq[1]);}}
        if(path && panelByPath(path)){showLevel(path);} else {showLevel('universe');}
      }
      focusFromLocation();
      window.addEventListener('hashchange',focusFromLocation);
      window.addEventListener('resize',function(){applyTransform();});
      document.addEventListener('keydown',function(e){
        if(e.target && /input|textarea|select/i.test(e.target.tagName||'')){return;}
        if(e.key==='+' || e.key==='='){view.scale=clamp(view.scale*1.16,0.6,6);applyTransform();}
        else if(e.key==='-' || e.key==='_'){view.scale=clamp(view.scale/1.16,0.6,6);applyTransform();}
        else if(e.key==='0'){resetView();}
        else if(e.key==='f' || e.key==='F'){fitToAll();}
        else if(e.key==='l' || e.key==='L'){locateSelected();}
        else if(e.key==='ArrowLeft'){view.tx+=40;applyTransform();}
        else if(e.key==='ArrowRight'){view.tx-=40;applyTransform();}
        else if(e.key==='ArrowUp'){view.ty+=40;applyTransform();}
        else if(e.key==='ArrowDown'){view.ty-=40;applyTransform();}
        else if(e.key==='Escape'){clearSelection(); if(fp){fp.classList.add('dismissed');}}
      });
    }

    /* ---- expand / collapse -- visibility only; data gaps live outside these ---- */
    var heads=document.querySelectorAll('[data-collapse-target]');
    for(var mm=0;mm<heads.length;mm++){
      heads[mm].addEventListener('click',function(){
        var el=document.getElementById(this.getAttribute('data-collapse-target'));
        if(el){el.classList.toggle('collapsed');}
      });
    }
  });
})();
"""
