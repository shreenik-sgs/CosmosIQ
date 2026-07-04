
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
