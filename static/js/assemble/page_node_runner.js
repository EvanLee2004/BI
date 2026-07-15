// node page.js runner: node page_node_runner.js <pack.json>
// pack = { fragments, views?, templates: {dashboard_body, page_shell} }
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const pack = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const sandbox = { window: {}, globalThis: {} };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
// rankings first (P0 shipped)
const rk = fs.readFileSync(path.join(__dirname, 'rankings.js'), 'utf8');
const pg = fs.readFileSync(path.join(__dirname, 'page.js'), 'utf8');
vm.runInNewContext(rk, sandbox);
vm.runInNewContext(pg, sandbox);
function unbrace(s){ return s.replace(/\{\{/g,'{').replace(/\}\}/g,'}'); }
const html = sandbox.assemblePage(pack.fragments, {
  dashboard_body: pack.templates.dashboard_body,
  page_shell: unbrace(pack.templates.page_shell)
}, pack.views || null);
process.stdout.write(html);
