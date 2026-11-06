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
test('hidden page does not renew; restart does not reacquire operator or replay motion', async () => {
  const h = await screen();
  try {
    await h.el('connect').onclick();
    h.requests.length = 0;
    Object.defineProperty(h.w.document, 'hidden', { value: true, configurable: true });
    await h.tick(); assert.equal(h.requests.length, 0);
    Object.defineProperty(h.w.document, 'hidden', { value: false, configurable: true });
    h.state.controlEpoch = 'new-epoch'; h.state.control.operatorId = null;
    await h.tick();
    assert.deepEqual(h.requests.map(r => r.path), ['/api/state']);
    assert.equal(h.el('start').disabled, true);
    assert.equal(h.el('recover').disabled, true);
  } finally { h.dom.window.close(); }
});
