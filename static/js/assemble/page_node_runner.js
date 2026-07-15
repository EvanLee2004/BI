const fs = require('fs');
const path = require('path');
const vm = require('vm');
const pack = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const code = fs.readFileSync(path.join(__dirname, 'page.js'), 'utf8');
const sandbox = { window: {}, globalThis: {} };
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.runInNewContext(code, sandbox);
function unbrace(s){ return s.replace(/\{\{/g,'{').replace(/\}\}/g,'}'); }
const html = sandbox.assemblePage(pack.fragments, {
  dashboard_body: pack.templates.dashboard_body,
  page_shell: unbrace(pack.templates.page_shell)
});
process.stdout.write(html);
