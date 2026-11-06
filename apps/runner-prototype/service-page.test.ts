import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { JSDOM } = createRequire(import.meta.url)('jsdom');
const dir = new URL('../server/src/apris_server/operator_console/', import.meta.url);
test('service page answers only the current scoped question, never clears handover or renews authority', async () => {
  const dom = new JSDOM(readFileSync(new URL('service.html', dir), 'utf8'), {
    url: 'http://127.0.0.1:8766/app#test', runScripts: 'outside-only', pretendToBeVisual: true,
  });
  try {
    const w = dom.window; w.AbortSignal = AbortSignal; w.setInterval = () => 1;
    const requests: { path: string; body: any }[] = [];
    const state: any = { live: true, runEpoch: 'run-epoch', prompt: { id: 'q1', message: '<img src=x>',
      choices: ['Done'], stationary: true }, answered: null, guardId: 'guard', messages: ['Welcome'] };
    w.fetch = async (path: string, options: any) => {
      const body = options.body && JSON.parse(options.body); requests.push({ path, body });
      if (path.endsWith('/answer')) state.answered = { questionId: 'q1', value: 'Done' };
      return { ok: true, json: async () => structuredClone(path.endsWith('/view') ? { viewId: 'view-1' } : state) };
    };
    await w.eval('(async () => {' + readFileSync(new URL('service.js', dir), 'utf8') + '\n})()');
    assert.equal(w.document.getElementById('question').textContent, '<img src=x>');
    assert.equal(w.document.querySelector('img'), null);
    await w.document.querySelector('button').onclick();
    const answer = requests.find(r => r.path.endsWith('/answer'))!;
    assert.deepEqual(answer.body, { viewId: 'view-1', runEpoch: 'run-epoch', questionId: 'q1', value: 'Done' });
    assert.match(w.document.getElementById('result').textContent, /退避確認/);
    assert.ok(requests.every(r => r.path.startsWith('/api/service/')));
    assert.ok(!requests.some(r => r.body?.humanClear || r.body?.kind));
  } finally { dom.window.close(); }
});

test('service page distinguishes completion, interruption, failure and not started', async () => {
  for (const [status, label] of [['completed', '正常終了'], ['interrupted', '中断しました'], ['failed', '失敗して終了'], [null, '未開始']]) {
    const dom = new JSDOM(readFileSync(new URL('service.html', dir), 'utf8'), {
      url: 'http://127.0.0.1:8766/app#test', runScripts: 'outside-only',
    });
    try {
      const w = dom.window; w.AbortSignal = AbortSignal; w.setInterval = () => 1;
      w.fetch = async (path: string) => ({ ok: true, json: async () => path.endsWith('/view') ? { viewId: 'v' } : {
        live: false, messages: [], prompt: null, answered: null, result: status ? { status, reason: 'test-reason' } : null,
      } });
      await w.eval('(async () => {' + readFileSync(new URL('service.js', dir), 'utf8') + '\n})()');
      assert.equal(w.document.getElementById('connection').textContent, label);
      assert.doesNotMatch(w.document.getElementById('question').textContent, /質問を待って/);
      assert.equal(w.document.querySelectorAll('button').length, 0);
    } finally { dom.window.close(); }
  }
});
