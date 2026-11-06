import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runPythonTrial } from './python-experiment.ts';

async function within<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([promise, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('trial-did-not-settle')), ms);
    })]);
  } finally { clearTimeout(timer!); }
}

test('missing Python executable rejects and cleans up promptly', { timeout: 4000 }, async () => {
  const previous = process.env.APRIS_PYTHON;
  process.env.APRIS_PYTHON = join(tmpdir(), 'apris-no-such-python-executable');
  try {
    await assert.rejects(within(runPythonTrial(), 1500), /ENOENT/);
  } finally {
    if (previous === undefined) delete process.env.APRIS_PYTHON; else process.env.APRIS_PYTHON = previous;
  }
});

test('batched acceptance and immediate terminal preserve the real failure', { timeout: 7000, skip: process.platform === 'win32' }, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'apris-batched-port-'));
  const executable = join(dir, 'port.cjs');
  // Behaves like the JSON-lines port. No Python dependency. One write contains both lines.
  await writeFile(executable, '#!' + process.execPath + '\n' + String.raw`
const { createInterface } = require('node:readline');
createInterface({ input: process.stdin }).on('line', line => {
  const r = JSON.parse(line);
  const token = { session: 'session-1', generation: 1 };
  let value = r.action === 'admit' ? 'session-1' : null;
  if (r.action === 'snapshot') value = { target: 'fake-only', moving: false };
  if (r.action === 'move') value = token;
  const reply = { kind: 'reply', id: r.id, ok: true, value };
  const terminal = { kind: 'terminal', event: { token, status: 'failed', reason: 'runtime-rejected' } };
  process.stdout.write(JSON.stringify(reply) + '\n' + (r.action === 'move' ? JSON.stringify(terminal) + '\n' : ''));
});
`, { mode: 0o755 });
  const previous = process.env.APRIS_PYTHON;
  process.env.APRIS_PYTHON = executable;
  try {
    const trial = await within(runPythonTrial(), 5000);
    const result = trial.events.find(e => e.kind === 'service-result');
    assert.equal(result?.status, 'failed');
    assert.match(result.reason, /failed/);
    assert.doesNotMatch(result.reason, /timeout/);
  } finally {
    if (previous === undefined) delete process.env.APRIS_PYTHON; else process.env.APRIS_PYTHON = previous;
    await rm(dir, { recursive: true, force: true });
  }
});
