export default {
  async fetch(req) {
    const u = new URL(req.url);
    let p = decodeURIComponent(u.pathname);
    let f = F[p] || F[p.replace(/\/?$/, '/') + 'index.html'] || F[p + '.html'];
    // legacy URLs (GSC 404s) -> 301
    const R = {'/tool': '/tools/', '/tool/': '/tools/'};
    if (!f && (R[p] || p.startsWith('/tool/'))) return Response.redirect(u.origin + (R[p] || '/tools/'), 301);
    if (!f && !p.endsWith('/') && F[p + '/index.html']) return Response.redirect(u.origin + p + '/', 301);
    if (!f) return new Response((F['/404.html']||F['/index.html'])[0], {status: 404, headers: {'content-type': 'text/html; charset=utf-8'}});
    const body = f[2] ? Uint8Array.from(atob(f[0]), c => c.charCodeAt(0)) : f[0];
    return new Response(body, {headers: {'content-type': f[1], 'cache-control': (p.startsWith('/img/') || /^\/assets\/.+\.[0-9a-f]{8}\.js$/.test(p)) ? 'public, max-age=31536000, immutable' : (p === '/sw.js' ? 'no-cache' : 'public, max-age=600')}});
  }
};