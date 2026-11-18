// 塑价365 service worker：页面走网络优先（离线时用上次缓存），静态资源走缓存优先
var V='p365-v1';
self.addEventListener('install',function(e){self.skipWaiting()});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k!==V}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener('fetch',function(e){var r=e.request;if(r.method!=='GET')return;var u=new URL(r.url);if(u.origin!==location.origin)return;
 if(/^\/assets\/.+\.[0-9a-f]{8}\.js$/.test(u.pathname)||u.pathname.indexOf('/img/')===0||/\.(png|webp|ico)$/.test(u.pathname)){
  e.respondWith(caches.open(V).then(function(c){return c.match(r).then(function(m){return m||fetch(r).then(function(res){if(res.ok)c.put(r,res.clone());return res})})}));return}
 if(r.mode==='navigate'){e.respondWith(fetch(r).then(function(res){if(res.ok){var cp=res.clone();caches.open(V).then(function(c){c.put(r,cp)})}return res}).catch(function(){return caches.match(r).then(function(m){return m||caches.match('/')})}))}
});
