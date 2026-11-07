import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
const { JSDOM } = createRequire(import.meta.url)('jsdom');
const dir = new URL('../server/src/apris_server/operator_console/', import.meta.url);
async function screen() {
  const dom = new JSDOM(readFileSync(new URL('index.html', dir), 'utf8'), {
    url: 'http://127.0.0.1:8766/console#test-token', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  const w = dom.window;
  const state: any = { controlEpoch: 'epoch', backend: 'simulator', moving: false,
    control: { operatorId: null, runEpoch: null, runId: null, guardId: null, inhibited: true, stopPending: false },
    state: { pose: { x: 0, y: 0, yaw: 0 } }, events: [] };
  const requests: { path: string; body: any }[] = [];
  let tick = async () => {};
  w.setInterval = (fn: typeof tick) => { tick = fn; return 1; };
  w.AbortSignal = AbortSignal;
  Object.defineProperty(w.crypto, 'randomUUID', { value: randomUUID });
  w.fetch = async (path: string, options: any) => {
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    const body = options.body && JSON.parse(options.body);
    requests.push({ path, body });
    if (body?.kind === 'openOperator') state.control.operatorId = 'operator';
    if (body?.kind === 'recover') state.control.inhibited = false;
    if (body?.kind === 'globalStop') { state.control.inhibited = true; state.control.runEpoch = null; }
    return { ok: true, json: async () => structuredClone(path === '/api/state' ? state : state.control) };
  };
  await w.eval('(async () => {' + readFileSync(new URL('console.js', dir), 'utf8') + '\n})()');
  return { dom, w, state, requests, tick: () => tick(), el: (id: string) => w.document.getElementById(id) };
}
test('operator page starts read-only; recovery needs fresh explicit clearance', async () => {
  const h = await screen();
  try {
    assert.equal(h.w.location.hash, '');
    assert.ok(h.requests.every(r => r.path === '/api/state'));
    assert.equal(h.el('recover').disabled, true);
    await h.el('connect').onclick();
    h.el('clearance').checked = true; h.el('clearance').onchange();
    await h.el('recover').onclick();
    assert.ok(h.requests.some(r => r.body?.kind === 'recover' && r.body.confirmed === true));
    assert.equal(h.el('clearance').checked, false);
    assert.ok(!h.requests.some(r => r.path === '/api/motion'));
    h.el('clearance').checked = true;
    h.state.control.guardId = 'new-question'; await h.tick();
    assert.equal(h.el('clearance').checked, false);
    assert.equal(h.el('clear').disabled, true);
  } finally { h.dom.window.close(); }
});
test('hidden page renews acquired authority; restart does not reacquire or replay', async () => {
  const h = await screen();
  try {
    await h.el('connect').onclick();
    h.requests.length = 0;
    Object.defineProperty(h.w.document, 'hidden', { value: true, configurable: true });
    await h.tick();
    assert.ok(h.requests.some(r => r.body?.kind === 'operatorHeartbeat'));
    assert.ok(!h.requests.some(r => r.path === '/api/motion'));
    h.requests.length = 0;
    Object.defineProperty(h.w.document, 'hidden', { value: false, configurable: true });
    h.state.controlEpoch = 'new-epoch'; h.state.control.operatorId = null;
    await h.tick();
    assert.deepEqual(h.requests.map(r => r.path), ['/api/state']);
    assert.equal(h.el('start').disabled, true);
    assert.equal(h.el('recover').disabled, true);
  } finally { h.dom.window.close(); }
});

test('service buttons scope start/stop and show failed launch without reusing old completion', async () => {
  const h = await screen();
  try {
    await h.el('connect').onclick();
    h.el('clearance').checked = true; await h.el('recover').onclick();
    assert.equal(h.el('service-start').disabled, false);
    await h.el('service-start').onclick();
    assert.ok(h.requests.some(r => r.path === '/api/service/launch' && r.body.operatorId === 'operator'));
    h.state.serviceProcess = { id: 'launch', active: true, status: 'starting', runEpoch: null };
    await h.tick();
    assert.equal(h.el('service-start').disabled, true);
    assert.equal(h.el('service-stop').disabled, false);
    await h.el('service-stop').onclick();
    assert.ok(h.requests.some(r => r.path === '/api/service/stop' && r.body.launchId === 'launch'));
    h.state.serviceProcess = { id: 'launch', active: false, status: 'failed', runEpoch: null, reason: 'node-missing' };
    h.state.serviceRunEpoch = 'old-run';
    h.state.serviceResult = { status: 'completed', reason: 'old-completion' };
    await h.tick();
    assert.match(h.el('service-status').textContent, /失敗.*node-missing/);
    assert.doesNotMatch(h.el('service-status').textContent, /正常終了/);
    assert.equal(h.el('service-start').textContent, '再実行');
  } finally { h.dom.window.close(); }
});

test('map mode requires placement confirmation and never initializes or recovers automatically', async () => {
  const h = await screen();
  try {
    h.state.localization = { blocked: true, reason: 'initialization-required', localizationEpoch: 'loc1', snapshot: null };
    h.state.state = null;
    await h.tick();
    assert.equal(h.el('localization-panel').hidden, false);
    assert.match(h.el('pose').textContent, /取得待ち/);
    await h.el('connect').onclick();
    h.el('clearance').checked = true; h.el('clearance').onchange();
    assert.equal(h.el('recover').disabled, true);
    assert.equal(h.el('localize').disabled, true);
    assert.ok(!h.requests.some(r => r.path === '/api/localization/initialize'));
    h.el('placement').checked = true; h.el('placement').onchange();
    assert.equal(h.el('localize').disabled, false);
    await h.el('localize').onclick();
    const call = h.requests.find(r => r.path === '/api/localization/initialize');
    assert.deepEqual(call?.body, { controlEpoch: 'epoch', operatorId: 'operator', localizationEpoch: 'loc1', candidateId: 'start-placement', confirmed: true });
    assert.equal(h.el('placement').checked, false);
    assert.ok(!h.requests.some(r => r.body?.kind === 'recover' || r.path === '/api/motion'));
    h.el('placement').checked = true;
    h.state.moving = true; await h.tick();
    assert.equal(h.el('placement').checked, false);
  } finally { h.dom.window.close(); }
});

test('route controls require a localized test run and exclude direct motion', async () => {
  const h = await screen();
  try {
    await h.el('connect').onclick();
    h.state.localization = { blocked: false, localizationEpoch: 'loc', snapshot: {quality: {status: 'tracking'}} };
    h.state.control.inhibited = false;
    await h.tick();
    assert.equal(h.el('route-start').disabled, true);
    h.state.control.runEpoch = 'run-epoch'; h.state.control.runId = 'run';
    await h.tick();
    assert.equal(h.el('route-start').disabled, false);
    await h.el('route-start').onclick();
    const request = h.requests.find(r => r.path === '/api/route/start');
    assert.equal(request?.body.targetId, 'start-to-desk');
    assert.equal(request?.body.runEpoch, 'run-epoch');
    h.state.route = { id: 'route-1', runEpoch: 'run-epoch', status: 'running', waypoint: 1 };
    await h.tick();
    assert.equal(h.el('move').disabled, true);
    assert.equal(h.el('route-start').disabled, true);
    await h.el('route-cancel').onclick();
    assert.deepEqual(h.requests.find(r => r.path === '/api/route/cancel')?.body, {id: 'route-1', runEpoch: 'run-epoch'});
  } finally { h.dom.window.close(); }
});
