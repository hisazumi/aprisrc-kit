// Local orchestrator: policy and motion authority remain in the separate Python port.
import { spawn, fork } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { myService } from '../pwa/src/missions/myService.ts';
export type TrialMode = 'normal' | 'decline' | 'kill' | 'block' | 'disconnect' | 'missing-evidence' | 'delayed-evidence';
async function joinBounded(closed: Promise<unknown>, kill: () => void, graceMs: number) {
  let escalation: ReturnType<typeof setTimeout> | undefined;
  let deadline: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([closed, new Promise<never>((_, reject) => {
      escalation = setTimeout(kill, graceMs);
      deadline = setTimeout(() => reject(new Error('child-cleanup-timeout')), graceMs + 500);
    })]);
  } finally { clearTimeout(escalation); clearTimeout(deadline); }
}
export async function runPythonTrial(mode: TrialMode = 'normal') {
  const python = spawn(process.env.APRIS_PYTHON ?? 'python3', ['-m', 'apris_server.runner_port_experiment'], {
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const events: any[] = [];
  let stderr = '';
  python.stderr.on('data', chunk => { stderr += chunk; });
  // close is also emitted when spawn fails and no exit event is possible.
  const exited = new Promise(resolve => python.once('close', resolve));
  let closing = false;
  let failure: Error | undefined;
  const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  let id = 0;
  const command = (action: string, data: object = {}) => new Promise<any>((resolve, reject) => {
    if (closing || failure) { reject(failure ?? new Error('trial-closed')); return; }
    const key = ++id; pending.set(key, { resolve, reject });
    python.stdin.write(JSON.stringify({ id: key, action, ...data }) + '\n');
  });
  const worker = fork(new URL('./service-worker.ts', import.meta.url), [], { stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
  worker.stderr?.on('data', chunk => { stderr += chunk; });
  const workerExit = new Promise(resolve => worker.once('close', resolve));
  const send = (message: unknown) => { if (worker.connected) worker.send(message as object, () => {}); };
  let settle!: () => void;
  let fail!: (e: Error) => void;
  const finished = new Promise<void>((resolve, reject) => { settle = resolve; fail = reject; });
  // Observe rejection even when a startup request is still pending.
  void finished.catch(() => {});
  const abort = (error: Error) => {
    if (closing) return;
    failure ??= error;
    for (const p of pending.values()) p.reject(error);
    pending.clear(); fail(error);
  };
  python.on('error', abort);
  python.on('close', code => { if (!closing) abort(new Error('Python closed: ' + code + ': ' + stderr)); });
  python.stdin.on('error', abort);
  worker.on('error', abort);
  const timeout = setTimeout(() => abort(new Error('trial-timeout: ' + stderr)), 6000);
  const lines = createInterface({ input: python.stdout });
  lines.on('line', line => {
    const message = JSON.parse(line);
    if (message.kind === 'reply') {
      const p = pending.get(message.id); if (!p) return;
      pending.delete(message.id);
      if (message.ok) p.resolve(message.value); else p.reject(new Error(message.error));
    } else {
      events.push(message); send(message);
      if (message.kind === 'terminal' && message.event.status === 'interrupted') settle();
    }
  });
  let session = '';
  worker.on('disconnect', () => {
    if (!closing && !failure && !python.stdin.destroyed && session) void command('revoke', { reason: 'runner-disconnected' }).catch(() => {});
  });
  worker.on('message', async (message: any) => {
    try {
      if (message.session !== session) throw new Error('wrong-session');
      if (message.kind === 'heartbeat') {
        await command('heartbeat', { session, token: message.token });
      } else if (message.kind === 'request') {
        let value: unknown;
        if (message.action === 'person') {
          await command('heartbeat', { session }); value = { source: 'synthetic' };
        } else if (message.action === 'prompt') {
          await command('heartbeat', { session }); events.push({ kind: 'prompt', message: message.message });
          const following = message.choices.includes('We have arrived');
          if (following && ['kill', 'block', 'disconnect'].includes(mode)) {
            if (mode === 'kill') worker.kill('SIGKILL'); else send({ kind: mode });
            return;
          }
          if (following && mode === 'missing-evidence') await command('fixture', { evidenceDelay: 'missing' });
          if (following && mode === 'delayed-evidence') await command('fixture', { evidenceDelay: 0.1 });
          if (message.stationary) await command('clear', { session, confirmed: true });
          value = mode === 'decline' && message.choices.includes('No') ? 'No' : message.choices[0];
        } else {
          value = await command(message.action, { session, token: message.token, duration: message.duration });
        }
        send({ kind: 'reply', id: message.id, ok: true, value });
      } else if (message.kind === 'say') {
        events.push(message);
      } else if (message.kind === 'service-result') {
        events.push(message); await command('revoke', { reason: 'service-' + message.status }); settle();
      }
    } catch (error) {
      if (message.kind === 'request') send({ kind: 'reply', id: message.id, ok: false, error: String(error) });
    }
  });
  try {
    // Synthetic environment fixture is explicit and separate from student capability calls.
    await command('fixture', { front: 'CLEAR' });
    session = await command('admit');
    send({ kind: 'start', session });
    await finished;
    const state = await command('snapshot');
    return { service: myService.title, mode, events, state };
  } finally {
    closing = true;
    clearTimeout(timeout);
    for (const p of pending.values()) p.reject(failure ?? new Error('trial-closed'));
    pending.clear();
    worker.kill('SIGKILL'); python.stdin.end();
    try {
      await Promise.all([
        joinBounded(workerExit, () => { worker.kill('SIGKILL'); }, 500),
        joinBounded(exited, () => { python.kill('SIGKILL'); }, 1000),
      ]);
    } finally { lines.close(); }
  }
}
