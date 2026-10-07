
(function(){
  var root=document.documentElement;
  var KEY='dailynews.v1';
  function load(){try{return JSON.parse(localStorage.getItem(KEY))||{}}catch(e){return {}}}
  function save(s){try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}}
  var state=load();
  state.theme=state.theme||'';
  state.read=state.read||{};
  state.fav=state.fav||{};

  // 主题
  if(state.theme){root.dataset.theme=state.theme;}
  var themeBtn=document.querySelector('.js-theme');
  if(themeBtn){
    themeBtn.textContent=root.dataset.theme==='dark'?'☀':'◐';
    themeBtn.onclick=function(){
      var next=root.dataset.theme==='dark'?'light':'dark';
      root.dataset.theme=next; state.theme=next; save(state);
      themeBtn.textContent=next==='dark'?'☀':'◐';
      var m=document.querySelector('meta[name=theme-color]');
      if(m) m.content=next==='dark'?'#14130f':'#faf7f2';
    };
  }

  var items=[].slice.call(document.querySelectorAll('.item'));
  function apply(){
    var q=(document.querySelector('.js-q')||{}).value||'';
    q=q.trim().toLowerCase();
    var sec=(document.querySelector('.tab.on')||{}).dataset ?
            document.querySelector('.tab.on').dataset.sec : 'all';
    var onlyUnread=document.querySelector('.tab[data-filter=unread]')?.classList.contains('on');
    var onlyFav=document.querySelector('.tab[data-filter=fav]')?.classList.contains('on');
    var shown=0;
    items.forEach(function(el){
      var txt=el.dataset.text||'';
      var okQ=!q||txt.indexOf(q)>=0;
      var okS=sec==='all'||el.dataset.sec===sec;
      var okU=!onlyUnread||state.read[el.dataset.id]!==1;
      var okF=!onlyFav||state.fav[el.dataset.id]===1;
      var ok=okQ&&okS&&okU&&okF;
      el.hidden=!ok; if(ok) shown++;
    });
    [].forEach.call(document.querySelectorAll('.sec'),function(s){
      var vis=[].slice.call(s.querySelectorAll('.item')).filter(function(i){return !i.hidden;});
      s.hidden=vis.length===0;
    });
    var e=document.querySelector('.js-empty'); if(e) e.hidden=shown>0;
  }

  document.querySelectorAll('.tab[data-sec]').forEach(function(t){
    t.onclick=function(){
      document.querySelectorAll('.tab[data-sec]').forEach(function(x){x.classList.remove('on')});
      t.classList.add('on'); apply();
    };
  });
  document.querySelectorAll('.tab[data-filter]').forEach(function(t){
    t.onclick=function(){
      var on=t.classList.toggle('on');
      if(on){
        var other=t.dataset.filter==='unread'?'fav':'unread';
        var o=document.querySelector('.tab[data-filter='+other+']');
        if(o) o.classList.remove('on');
      }
      apply();
    };
  });
  var q=document.querySelector('.js-q');
  if(q){ q.addEventListener('input',apply); }
  document.addEventListener('keydown',function(ev){
    if(ev.key==='/'&&document.activeElement!==q){ev.preventDefault();q&&q.focus();}
    if(ev.key==='Escape'&&q){q.value='';apply();q.blur();}
  });

  items.forEach(function(el){
    var id=el.dataset.id;
    var r=el.querySelector('.js-read'), f=el.querySelector('.js-fav');
    if(state.read[id]===1) el.dataset.read='1';
    if(state.fav[id]===1) el.dataset.fav='1';
    if(r) r.onclick=function(e){e.preventDefault();
      var on=state.read[id]===1?(delete state.read[id],0):(state.read[id]=1,1);
      el.dataset.read=on?'1':'0'; save(state); apply();};
    if(f) f.onclick=function(e){e.preventDefault();
      var on=state.fav[id]===1?(delete state.fav[id],0):(state.fav[id]=1,1);
      el.dataset.fav=on?'1':'0'; save(state); apply();};
    var a=el.querySelector('h3 a');
    if(a) a.addEventListener('click',function(){state.read[id]=1;save(state);
      el.dataset.read='1';});
  });
  apply();

  // PWA
  if('serviceWorker' in navigator){
    window.addEventListener('load',function(){navigator.serviceWorker.register('sw.js').catch(function(){});});
  }
})();
