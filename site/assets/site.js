
(function(){
  var root=document.documentElement;
  var KEY='dailynews.v1';
  function load(){try{return JSON.parse(localStorage.getItem(KEY))||{}}catch(e){return {}}}
  function save(s){try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}}
  var state=load();
  state.read=state.read||{}; state.fav=state.fav||{};

  /* 主题 */
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

  /* 日期下拉：进页面就是最新一期，点日期才展开往期 */
  var pick=document.querySelector('.datepick');
  if(pick){
    var btn=pick.querySelector('.datebtn');
    btn.onclick=function(e){e.stopPropagation();pick.classList.toggle('open');};
    document.addEventListener('click',function(){pick.classList.remove('open');});
    document.addEventListener('keydown',function(e){
      if(e.key==='Escape') pick.classList.remove('open');
    });
  }

  /* 条目筛选（搜索 + 未读 + 收藏） */
  var items=[].slice.call(document.querySelectorAll('.item'));
  function apply(){
    var q=(document.querySelector('.js-q')||{}).value||'';
    q=q.trim().toLowerCase();
    var onlyUnread=document.querySelector('.tab[data-filter=unread]');
    var onlyFav=document.querySelector('.tab[data-filter=fav]');
    var u=onlyUnread&&onlyUnread.classList.contains('on');
    var f=onlyFav&&onlyFav.classList.contains('on');
    items.forEach(function(el){
      var ok=(!q||(el.dataset.text||'').indexOf(q)>=0)
           &&(!u||state.read[el.dataset.id]!==1)
           &&(!f||state.fav[el.dataset.id]===1);
      el.hidden=!ok;
    });
    [].forEach.call(document.querySelectorAll('.sec'),function(s){
      s.hidden=![].slice.call(s.querySelectorAll('.item')).some(function(i){return !i.hidden;});
    });
  }
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
  if(q) q.addEventListener('input',apply);
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q&&q.focus();}
    if(e.key==='Escape'&&q){q.value='';apply();q.blur();}
  });

  /* 栏目：点击跳转 + 滚动时高亮当前栏目（常驻，不隐藏） */
  var tabLinks=[].slice.call(document.querySelectorAll('.tab[data-sec]'));
  var secs=[].slice.call(document.querySelectorAll('.sec'));
  function markCurrent(){
    var y=window.scrollY+140, cur=null;
    secs.forEach(function(s){ if(s.hidden) return;
      if(s.offsetTop<=y) cur=s; });
    var name=cur?cur.dataset.sec:'';
    tabLinks.forEach(function(t){
      t.classList.toggle('on', t.dataset.sec===(cur?name:'all'));
    });
  }
  window.addEventListener('scroll',markCurrent,{passive:true});
  window.addEventListener('resize',markCurrent);
  markCurrent();

  items.forEach(function(el){
    var id=el.dataset.id, r=el.querySelector('.js-read'), f=el.querySelector('.js-fav');
    if(state.read[id]===1) el.dataset.read='1';
    if(state.fav[id]===1) el.dataset.fav='1';
    if(r) r.onclick=function(e){e.preventDefault();
      var on=state.read[id]===1?(delete state.read[id],0):(state.read[id]=1,1);
      el.dataset.read=on?'1':'0'; save(state); apply();};
    if(f) f.onclick=function(e){e.preventDefault();
      var on=state.fav[id]===1?(delete state.fav[id],0):(state.fav[id]=1,1);
      el.dataset.fav=on?'1':'0'; save(state); apply();};
    var a=el.querySelector('h3 a');
    if(a) a.addEventListener('click',function(){
      state.read[id]=1;save(state);el.dataset.read='1';});
  });

  if('serviceWorker' in navigator){
    window.addEventListener('load',function(){
      navigator.serviceWorker.register('sw.js').catch(function(){});
    });
  }
})();
