const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
http.createServer((req, res) => {
  if (req.url === '/favicon.ico') { res.writeHead(204); return res.end(); }
  if (req.url === '/frontend/js/workspace-ui.js') {
    res.writeHead(200, {'Content-Type':'application/javascript; charset=utf-8','Cache-Control':'no-store'});
    return res.end(fs.readFileSync(path.join(__dirname,'../../frontend/js/workspace-ui.js')));
  }
  const assets = {'/':'index.html', '/index.html':'index.html', '/design-v2.css':'design-v2.css'};
  const file = assets[req.url];
  if (!file) { res.writeHead(404); return res.end('Not found'); }
  res.writeHead(200, {'Content-Type':file.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/html; charset=utf-8', 'Cache-Control':'no-store'});
  res.end(fs.readFileSync(path.join(__dirname, file)));
}).listen(4318, '127.0.0.1', () => console.log('Design preview: http://127.0.0.1:4318'));
