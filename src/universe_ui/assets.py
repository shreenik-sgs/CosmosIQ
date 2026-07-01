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
.top-canvas{position:relative;border:1px solid #1c2350;border-radius:16px;padding:.9rem;
  min-height:60vh;overflow:hidden}
.intel-pane{background:linear-gradient(160deg,#0c1130,#141a3d);border:1px solid var(--line);
  border-radius:16px;padding:1rem 1.2rem}
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
.viewport{position:relative;overflow:hidden;min-height:64vh;border:0;padding:0;border-radius:14px;
  background:
    radial-gradient(130% 100% at 50% 12%, #241155 0%, #140a3a 32%, #08061c 62%, #030210 88%, #010007 100%)}
.starfield{position:absolute;inset:0;z-index:0;pointer-events:none}
.star{position:absolute;border-radius:50%;background:#ffffff;
  box-shadow:0 0 3px 1px rgba(180,205,255,.55);animation:twinkle 4.5s ease-in-out infinite}
.star.sl0{background:#cfe0ff}
.star.sl2{background:#fff4e0;box-shadow:0 0 5px 1px rgba(255,225,180,.6)}
@keyframes twinkle{0%,100%{transform:scale(1)}50%{transform:scale(.45)}}
.nebula{position:absolute;border-radius:50%;filter:blur(70px);pointer-events:none;z-index:0}
.neb-1{width:46%;height:52%;left:-8%;top:-12%;opacity:.38;
  background:radial-gradient(circle,#7b3ff2 0%,rgba(123,63,242,0) 66%)}
.neb-2{width:54%;height:56%;right:-12%;top:14%;opacity:.30;
  background:radial-gradient(circle,#2f6bd0 0%,rgba(47,107,208,0) 66%)}
.neb-3{width:44%;height:50%;left:26%;bottom:-16%;opacity:.28;
  background:radial-gradient(circle,#c0397a 0%,rgba(192,57,122,0) 66%)}
.vignette{position:absolute;inset:0;z-index:1;pointer-events:none;
  box-shadow:inset 0 0 200px 70px rgba(0,0,0,.78)}

.scene-layer{position:absolute;inset:0;z-index:2}
.scene-caption{position:absolute;left:1rem;top:.7rem;z-index:6;max-width:64%}
.scene-caption h2{margin:.1rem 0;font-size:1.1rem;text-shadow:0 2px 14px #000}
.scene-caption .level-head{margin:0}
.scene-bodies{position:absolute;inset:0;z-index:3}

/* a cosmic body positioned in space (absolute; NOT a grid card) */
.cosmic-object{position:absolute;transform:translate(-50%,-50%);cursor:pointer;
  text-align:center;z-index:3}
.cosmic-object:hover{z-index:9}
.cosmic-object .body{position:relative;margin:0 auto;border-radius:50%;
  transition:box-shadow .2s ease,transform .2s ease}
.cosmic-object:hover .body{transform:scale(1.14);
  box-shadow:0 0 46px 14px rgba(150,185,255,.55)}
.cosmic-object.ev-low{opacity:.72}.cosmic-object.ev-sparse{opacity:.5}
.cosmic-object.dashed-outline .body{outline:2px dashed #ffbf87;outline-offset:3px}

.body-label{margin-top:.35rem;font-size:.72rem;font-weight:700;color:#e4ebff;
  text-shadow:0 1px 8px #000,0 0 3px #000;position:relative;white-space:nowrap}
.body-tip{display:none;position:absolute;left:50%;top:130%;transform:translateX(-50%);
  background:#0b1130;border:1px solid var(--line);border-radius:8px;padding:.45rem .6rem;
  width:230px;font-weight:600;font-size:.7rem;color:#cdd6ff;white-space:normal;
  text-shadow:none;z-index:30}
.body-tip .badge{margin:.1rem .15rem}
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
"""


NAV_JS = """
/* Universe UI -- navigation-ONLY behaviour. Zoom-state transitions, breadcrumb
   push/pop, back/up, selected-object detail panel, hover/click highlight,
   expand/collapse, hash/query deep-link focus. NO network, NO form, NO submit,
   NO trade-execution affordance, NO scoring, NO data mutation. It only shows/hides pre-rendered
   DOM and copies pre-rendered detail text -- it can never hide a data gap. */
(function(){
  function ready(fn){
    if(document.readyState!=='loading'){fn();}
    else{document.addEventListener('DOMContentLoaded',fn);}
  }
  ready(function(){
    /* ---- one zoomable cosmos canvas (only present on universe.html) ---- */
    var panels=document.querySelectorAll('.level-panel');
    if(panels.length){
      var breadcrumb=document.getElementById('breadcrumb');
      var detailBody=document.getElementById('detail-body');
      var backBtn=document.getElementById('zoom-back');
      var current='universe';
      function panelByPath(p){
        for(var i=0;i<panels.length;i++){
          if(panels[i].getAttribute('data-path')===p){return panels[i];}
        }
        return null;
      }
      function setDetail(html){ if(detailBody){detailBody.innerHTML=html;} }
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
        var det=target.querySelector('.level-detail'); if(det){setDetail(det.innerHTML);}
        if(backBtn){backBtn.style.display=target.getAttribute('data-parent')?'inline-block':'none';}
        if(window.scrollTo){window.scrollTo(0,0);}
      }
      var objs=document.querySelectorAll('.cosmic-object');
      for(var i=0;i<objs.length;i++){
        objs[i].addEventListener('click',function(){
          var det=this.querySelector('.object-detail'); if(det){setDetail(det.innerHTML);}
          var tp=this.getAttribute('data-target-path');
          if(tp && panelByPath(tp)){showLevel(tp);}
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
      function focusFromLocation(){
        var h=window.location.hash||''; var q=window.location.search||''; var path=null;
        var m=h.match(/(?:focus|path)=([^&]+)/); if(m){path=decodeURIComponent(m[1]);}
        if(!path){var mq=q.match(/focus=([^&]+)/); if(mq){path=decodeURIComponent(mq[1]);}}
        if(path && panelByPath(path)){showLevel(path);} else {showLevel('universe');}
      }
      focusFromLocation();
      window.addEventListener('hashchange',focusFromLocation);
    }

    /* ---- expand / collapse -- visibility only; data gaps live outside these ---- */
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
