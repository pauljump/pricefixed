// pricefixed.polyfeeds.dev — static launch page for the pricefixed OSS repo.
// Zero-dep Node static server (str/jumpbank showcase pattern). Site source
// lives in the public repo on purpose: the page is part of the project.
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 7540;
const PUB = __dirname;

const MIME = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain' };

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  let p = url.pathname === '/' ? '/index.html' : url.pathname;
  p = path.normalize(p).replace(/^(\.\.[/\\])+/, '');
  const file = path.join(PUB, p);
  // never serve the server itself; everything else in site/ is public
  if (!file.startsWith(PUB) || path.basename(file) === 'server.js') { res.writeHead(404); return res.end('not found'); }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end('not found'); }
    const ext = path.extname(file);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': 'public, max-age=60' });
    res.end(data);
  });
});

server.listen(PORT, '127.0.0.1', () => console.log(`pricefixed-site on 127.0.0.1:${PORT}`));
