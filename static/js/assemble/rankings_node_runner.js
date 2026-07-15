// node rankings.js runner: node rankings_node_runner.js <view.json>
const fs = require('fs');
const path = require('path');
const view = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
// load rankings.js into sandbox
const code = fs.readFileSync(path.join(__dirname, 'rankings.js'), 'utf8');
const sandbox = { window: {}, globalThis: {} };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
const vm = require('vm');
vm.runInNewContext(code + '\nthis.result = assembleRankings(view);', Object.assign(sandbox, {view}));
process.stdout.write(sandbox.result);
