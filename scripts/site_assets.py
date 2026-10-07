"""站点静态资源：样式、脚本、PWA 清单、Service Worker。

单独放一个文件，方便改版式时不用碰渲染逻辑。
"""

CSS = r"""
:root{
  --bg:#faf7f2; --fg:#1c1a17; --dim:#6b6660; --line:#e2dcd2;
  --card:#fffdf9; --accent:#b3261e; --accent2:#1d4ed8;
  --fact:#8a857e; --shadow:0 1px 2px rgba(0,0,0,.05),0 8px 24px rgba(0,0,0,.04);
  color-scheme: light;
}
html[data-theme="dark"]{
  --bg:#14130f; --fg:#e8e4dc; --dim:#9b958c; --line:#312e28;
  --card:#1c1a16; --accent:#e8736a; --accent2:#7ba0f5;
  --fact:#8f8a82; --shadow:0 1px 2px rgba(0,0,0,.4);
  color-scheme: dark;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.8 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  -webkit-text-size-adjust:100%;
}
a{color:inherit;text-decoration:none}
a:hover{text-decoration:underline}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}

/* 报头 */
.top{
  position:sticky; top:0; z-index:20; background:var(--bg);
  border-bottom:1px solid var(--line); padding:.6rem 1rem;
  display:flex; align-items:center; gap:.75rem; flex-wrap:wrap;
}
.brand{font-family:Georgia,"Songti SC","SimSun",serif; font-size:1.35rem;
  font-weight:700; letter-spacing:.08em; color:var(--accent)}
.tagline{color:var(--dim); font-size:.8rem; white-space:nowrap}
.grow{flex:1}
.dates{display:flex; align-items:center; gap:.35rem;
  border:1px solid var(--line); border-radius:999px; padding:.2rem .5rem; background:var(--card)}
.dates a,.dates button{padding:.15rem .4rem; color:var(--dim); border-radius:6px}
.dates a:hover,.dates button:hover{background:var(--line); text-decoration:none}
.dates .cur{font-size:.85rem; padding:0 .3rem; min-width:9.5rem; text-align:center}
.search{
  border:1px solid var(--line); border-radius:999px; padding:.4rem .9rem;
  background:var(--card); color:inherit; font-size:.85rem; width:13rem; outline:none;
}
.search:focus{border-color:var(--accent)}
.icon{width:2rem;height:2rem;border-radius:999px;border:1px solid var(--line);
  background:var(--card); display:grid;place-items:center;font-size:.9rem}
.icon:hover{background:var(--line)}

/* 分区标签 */
.tabs{
  position:sticky; top:3.4rem; z-index:19; background:var(--bg);
  display:flex; gap:.1rem; overflow-x:auto; padding:.5rem 1rem .6rem;
  border-bottom:1px solid var(--line); scrollbar-width:none;
}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:.25rem .7rem; border-radius:999px; color:var(--dim); white-space:nowrap; font-size:.9rem}
.tab b{font-weight:600; opacity:.6; margin-left:.25rem; font-size:.8rem}
.tab:hover{background:var(--line); text-decoration:none}
.tab.on{color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,transparent)}
.tab.on b{opacity:1}

main{max-width:46rem; margin:0 auto; padding:1.2rem 1rem 4rem}

/* 卡片与专栏 */
.card{background:var(--card); border:1px solid var(--line); border-radius:10px;
  box-shadow:var(--shadow); padding:1.1rem 1.2rem; margin-bottom:1.6rem}
.badges{display:flex; align-items:center; gap:.5rem; margin-bottom:.5rem; flex-wrap:wrap}
.badge{font-size:.75rem; padding:.1rem .5rem; border-radius:999px;
  background:var(--accent); color:#fff}
.badge.ghost{background:transparent;color:var(--dim);border:1px solid var(--line)}
.col-title{font-family:Georgia,"Songti SC","SimSun",serif; font-size:1.5rem;
  line-height:1.45; margin:.35rem 0 1rem; letter-spacing:.01em}
.ed h3{font-size:1rem; margin:1.6rem 0 .5rem}
.ed h3:first-child{margin-top:0}
.ed p{margin:.5rem 0}
.fact,.analysis{margin:.5rem 0; padding-left:.8rem}
.fact{border-left:3px solid var(--fact)}
.analysis{border-left:3px solid var(--accent2)}
.fact .tag,.analysis .tag{display:inline-block;margin-right:.5rem;padding:.05rem .45rem;
  border-radius:4px;font-size:.78rem;vertical-align:.08rem}
.fact .tag{background:color-mix(in srgb,var(--fact) 20%,transparent);color:var(--fact)}
.analysis .tag{background:color-mix(in srgb,var(--accent2) 20%,transparent);color:var(--accent2)}

.lead{background:color-mix(in srgb,var(--accent) 7%,transparent);
  border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
  padding:.9rem 1.1rem; margin:0 0 1.2rem; font-size:.95rem}
.lead p{margin:0}
.notice{background:color-mix(in srgb,#d19a1e 12%,transparent);
  border:1px solid color-mix(in srgb,#d19a1e 35%,transparent);
  border-radius:8px;padding:.6rem .9rem;margin:0 0 1.2rem;font-size:.85rem;color:var(--dim)}

/* 条目列表 */
.sec-head{display:flex; align-items:baseline; gap:.6rem;
  border-bottom:2px solid var(--fg); padding-bottom:.3rem; margin:2rem 0 .9rem}
.sec-head h2{font-size:1.15rem; margin:0; font-family:Georgia,"Songti SC","SimSun",serif}
.sec-head span{color:var(--dim); font-size:.8rem}
.item{position:relative; padding:.7rem 0 .7rem 0; border-bottom:1px solid var(--line)}
.item h3{font-size:1rem; font-weight:600; margin:0 0 .2rem; line-height:1.55}
.item .sum{color:var(--dim); font-size:.88rem; margin:.15rem 0 .25rem;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden}
.item .meta{color:var(--dim); font-size:.78rem}
.item .star{color:var(--accent); letter-spacing:-.05em}
.item .acts{position:absolute; right:0; top:.7rem; display:flex; gap:.3rem; opacity:0; transition:opacity .15s}
.item:hover .acts{opacity:1}
.item[data-read="1"] h3{color:var(--dim); font-weight:500}
.item[data-fav="1"] .fav{color:var(--accent)}
@media (hover:none){.item .acts{opacity:1}}
.empty{color:var(--dim); padding:2rem 0; text-align:center}

/* 索引页 */
.issues{list-style:none;padding:0;margin:0}
.issues li{border-bottom:1px solid var(--line)}
.issues a{display:flex;justify-content:space-between;align-items:baseline;
  padding:.8rem .2rem;gap:1rem}
.issues a:hover{text-decoration:none;color:var(--accent)}
.issues .d{font-family:Georgia,"Songti SC","SimSun",serif; font-size:1.05rem}
.issues .t{color:var(--dim); font-size:.85rem; flex:1;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.issues .n{color:var(--dim); font-size:.8rem; white-space:nowrap}

footer{max-width:46rem;margin:0 auto;padding:1rem 1rem 3rem;color:var(--dim);
  font-size:.78rem;border-top:1px solid var(--line)}
@media (max-width:600px){
  .tagline{display:none}
  .search{width:100%;order:9}
  .tabs{top:6.2rem}
  .col-title{font-size:1.3rem}
  main{padding:1rem .8rem 3rem}
}
"""

JS = r"""
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
"""

MANIFEST = """{
  "name": "每日新闻",
  "short_name": "每日新闻",
  "description": "每日国内外要闻聚合与主编专栏",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "background_color": "#faf7f2",
  "theme_color": "#faf7f2",
  "lang": "zh-CN",
  "icons": [
    {"src": "assets/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}
  ]
}
"""

ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="20" fill="#b3261e"/>
<text y="72" x="50" font-size="60" text-anchor="middle" fill="#fff"
 font-family="Georgia,serif">闻</text></svg>
"""

# 只缓存外壳，新闻内容始终走网络，避免读到过期的一期
SW = """const CACHE = 'dailynews-shell-v1';
const SHELL = ['./', 'assets/site.css', 'assets/site.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const isShell = SHELL.some(p => url.pathname.endsWith(p.replace('./', '')));
  if (!isShell) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
"""
