// Local orchestrator: policy and motion authority remain in the separate Python port.
import { spawn, fork } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { myService } from '../pwa/src/missions/myService.ts';
export type TrialMode = 'normal' | 'decline' | 'kill' | 'block' | 'disconnect' | 'missing-evidence' | 'delayed-evidence';
export async function runPythonTrial(mode: TrialMode = 'normal') {
  const python = spawn(process.env.APRIS_PYTHON ?? 'python3', ['-m', 'apris_server.runner_port_experiment'], {
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const events: any[] = [];
  let stderr = '';
  python.stderr.on('data', chunk => { stderr += chunk; });
  const exited = new Promise(resolve => python.once('exit', resolve));
  const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  let id = 0;
  const command = (action: string, data: object = {}) => new Promise<any>((resolve, reject) => {
    const key = ++id; pending.set(key, { resolve, reject });
    python.stdin.write(JSON.stringify({ id: key, action, ...data }) + '\n');
  });
  const worker = fork(new URL('./service-worker.ts', import.meta.url), [], { stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
  worker.stderr?.on('data', chunk => { stderr += chunk; });
  const workerExit = new Promise(resolve => worker.once('exit', resolve));
  const send = (message: unknown) => { if (worker.connected) worker.send(message as object, () => {}); };
  let settle!: () => void;
  let fail!: (e: Error) => void;
  const finished = new Promise<void>((resolve, reject) => { settle = resolve; fail = reject; });
  // Observe rejection even when a startup request is still pending.
  void finished.catch(() => {});
  const abort = (error: Error) => {
    for (const p of pending.values()) p.reject(error);
    pending.clear(); fail(error);
  };
  python.on('error', abort);
  python.on('exit', code => { if (pending.size) abort(new Error('Python exited: ' + code + ': ' + stderr)); });
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
    if (!python.stdin.destroyed && session) void command('revoke', { reason: 'runner-disconnected' }).catch(() => {});
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
    clearTimeout(timeout); worker.kill('SIGKILL'); await workerExit;
    python.stdin.end();
    const kill = setTimeout(() => python.kill('SIGKILL'), 1000);
    await exited; clearTimeout(kill); lines.close();
  }
}
