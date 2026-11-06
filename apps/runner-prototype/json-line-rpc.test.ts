import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { JsonLineRpc } from './json-line-rpc.ts';
function pair(options = {}) {
  const input = new PassThrough(); const output = new PassThrough();
  const rpc = new JsonLineRpc(input, output, options);
  return { input, output, rpc };
}
test('fragmented/batched replies preserve events before a reply', async () => {
  const h = pair(); const events: unknown[] = []; h.rpc.onEvent(v => events.push(v));
  const p = h.rpc.request('snapshot');
  h.input.write('{"kind":"event","value":1}\n{"kind":"rep');
  h.input.write('ly","id":1,"ok":true,"value":"ok"}\n');
  assert.equal(await p, 'ok'); assert.equal(events.length, 1); h.rpc.close();
});
test('oversized unterminated frame fails outstanding requests', async () => {
  const h = pair({ maxFrameBytes: 64 }); const p = h.rpc.request('x');
  h.input.write('x'.repeat(65)); await assert.rejects(p, /frame/); assert.ok(h.rpc.signal.aborted);
});
test('outbound frame size rejects before writing', async () => {
  const h = pair({ maxFrameBytes: 64 });
  await assert.rejects(h.rpc.request('x', { data: 'x'.repeat(100) }), /frame/);
  assert.equal(h.output.readableLength, 0); h.rpc.close();
});
test('capacity rejection does not disturb admitted work', async () => {
  const h = pair({ maxPending: 1 }); const p = h.rpc.request('x');
  await assert.rejects(h.rpc.request('y'), /capacity/);
  h.input.write('{"kind":"reply","id":1,"ok":true,"value":1}\n');
  assert.equal(await p, 1); h.rpc.close();
});
test('timeout closes connection; late response cannot revive it', async () => {
  const h = pair({ requestMs: 10 }); const p = h.rpc.request('x');
  await assert.rejects(p, /timeout/);
  h.input.write('{"kind":"reply","id":1,"ok":true,"value":1}\n');
  await assert.rejects(h.rpc.request('y'), /closed/);
});
test('malformed JSON and EOF make outstanding requests uncertain', async () => {
  for (const mode of ['malformed', 'end']) {
    const h = pair(); const p = h.rpc.request('x');
    if (mode === 'malformed') h.input.write('oops\n'); else h.input.end();
    await assert.rejects(p, /uncertain/);
  }
});

test('write backpressure is bounded instead of accumulating commands', async () => {
  const { Writable } = await import('node:stream');
  const input = new PassThrough();
  const output = new Writable({ write(_chunk, _encoding, _callback) { /* stalled writer */ } });
  const rpc = new JsonLineRpc(input, output, { maxWriteBytes: 50 });
  const first = rpc.request('x');
  const observed = assert.rejects(first, /write-buffer/);
  await assert.rejects(rpc.request('second-command'), /write-buffer/); await observed;
  output.destroy(); input.destroy();
});
