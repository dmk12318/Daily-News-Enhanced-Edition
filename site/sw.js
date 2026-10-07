const CACHE = 'dailynews-shell-v1';
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
