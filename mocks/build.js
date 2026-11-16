// Concatenates src/* into mocks/ledgerlight.html (artifact fragment) and mocks/ledgerlight.preview.html (full document for local checks).
const fs = require('fs'), path = require('path');
const r = f => fs.readFileSync(path.join(__dirname, 'src', f), 'utf8');
const js = ['data.js', 'ui.js', 'detail.js', 's1.js', 's2.js', 's3.js', 's4.js', 's5.js', 's6.js', 's7.js', 's8.js', 'main.js'].map(r).join('\n');
fs.writeFileSync(path.join(__dirname, 'src', '_bundle.js'), js);
const fonts = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@600;700;800&display=swap">';
const body = `<title>Ledgerlight</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n${fonts}\n<style>\n${r('styles.css')}\n</style>\n<div id="root"></div>\n<script>\n${js}\n</script>\n`;
fs.writeFileSync(path.join(__dirname, 'ledgerlight.html'), body);
const skeleton = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style></head><body>${body}</body></html>`;
fs.writeFileSync(path.join(__dirname, 'ledgerlight.preview.html'), skeleton);
console.log('built', (body.length / 1024).toFixed(0) + ' KB');
