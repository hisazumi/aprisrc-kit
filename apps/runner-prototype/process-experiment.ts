// Fake safety gateway and operator harness. Service runs in a separate process.
import { fork, type ChildProcess } from 'node:child_process';
import { createInterface } from 'node:readline';
import { performance } from 'node:perf_hooks';
import { Gateway } from './gateway-core.ts';
const gateway = new Gateway(() => performance.now() / 1000);
let worker: ChildProcess | undefined;
let prompt: { id: number; session: string; choices: string[]; stationary: boolean } | undefined;
let ending = false;
const write = (event: unknown) => process.stdout.write(JSON.stringify(event) + '\n');
const send = (message: unknown) => { if (worker?.connected) worker.send(message as object, () => {}); };
const reply = (id: number, value?: unknown, error?: string) => send({ kind: 'reply', id, ok: !error, value, error });
gateway.terminal = event => { send({ kind: 'terminal', event }); write({ event: 'terminal', ...event }); };
gateway.revoked = reason => { prompt = undefined; send({ kind: 'revoked', reason }); write({ event: 'revoked', reason }); };
function launch() {
  if (worker) throw new Error('worker-still-running');
  const session = gateway.admit();
  const child = fork(new URL('./service-worker.ts', import.meta.url), [], { stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
  worker = child;
  child.stderr?.on('data', chunk => process.stderr.write(chunk));
  child.on('error', error => { gateway.revoke('runner-error'); write({ event: 'runner-error', reason: String(error) }); });
  child.on('message', (message: any) => {
    if (worker !== child) return;
    try {
      if (message.session !== session) throw new Error('wrong-session');
      if (message.kind === 'heartbeat') {
        gateway.heartbeat(session);
        if (message.token) gateway.renew(message.token);
      } else if (message.kind === 'request') {
        gateway.heartbeat(session);
        switch (message.action) {
          case 'move': reply(message.id, gateway.begin(session, message.duration)); break;
          case 'stop': gateway.stop(message.token); reply(message.id); break;
          case 'hold': gateway.hold(session); reply(message.id); break;
          case 'person': reply(message.id, { source: 'synthetic', clock: 'host-monotonic', time: performance.now() / 1000 }); break;
          case 'prompt':
            if (prompt) throw new Error('prompt-busy');
            if (!Array.isArray(message.choices) || !message.choices.length || message.choices.some((v: unknown) => typeof v !== 'string')) throw new Error('invalid-choices');
            prompt = { id: message.id, session, choices: message.choices, stationary: message.stationary === true };
            write({ event: 'prompt', ...prompt, message: message.message }); break;
          default: throw new Error('unsupported-request');
        }
      } else if (message.kind === 'say') {
        gateway.heartbeat(session); write({ event: 'say', message: message.message });
      } else if (message.kind === 'service-result') {
        write({ event: 'service-result', status: message.status, reason: message.reason });
        gateway.revoke('service-' + message.status);
      }
    } catch (error) {
      if (message.kind === 'request') reply(message.id, undefined, String(error));
      // A renewal can race terminal delivery; rejection must not revive motion.
    }
  });
  child.on('disconnect', () => { if (worker === child) gateway.revoke('runner-disconnected'); });
  child.on('exit', () => {
    if (worker === child) { gateway.revoke('runner-exited'); worker = undefined; }
    write({ event: 'worker-exited' });
  });
  child.send({ kind: 'start', session });
  return { session, runnerPid: child.pid, gatewayPid: process.pid };
}
const timer = setInterval(() => gateway.tick(), 10);
const input = createInterface({ input: process.stdin });
input.on('line', line => {
  let id: unknown;
  try {
    const request = JSON.parse(line); id = request.id;
    let value: unknown;
    switch (request.type) {
      case 'start': value = launch(); break;
      case 'snapshot': value = { ...gateway.snapshot(), runnerPid: worker?.pid }; break;
      case 'answer': {
        const p = prompt;
        if (!p || p.id !== request.promptId || p.session !== request.session || !p.choices.includes(request.answer)) throw new Error('invalid-or-stale-answer');
        gateway.heartbeat(p.session);
        if (p.stationary) gateway.clear(p.session, request.clearToMove === true);
        prompt = undefined; reply(p.id, request.answer); break;
      }
      case 'stop': gateway.revoke('operator-stop'); break;
      case 'recover': gateway.recover(request.confirmed === true); break;
      case 'pause': gateway.setPause(true); break;
      case 'resume': gateway.setPause(false); break;
      case 'fault':
        if (request.mode === 'kill') worker?.kill('SIGKILL');
        else if (request.mode === 'block' || request.mode === 'disconnect') send({ kind: request.mode });
        else if (request.mode === 'missing-evidence') gateway.evidenceDelay = Infinity;
        else if (request.mode === 'delayed-evidence') gateway.evidenceDelay = 0.1;
        else if (request.mode === 'normal-evidence') gateway.evidenceDelay = 0;
        else if (request.mode === 'stalled') gateway.stalled = true;
        else throw new Error('unknown-fault');
        break;
      default: throw new Error('unknown-command');
    }
    write({ id, ok: true, value });
  } catch (error) { write({ id, ok: false, error: String(error) }); }
});
function shutdown() {
  if (ending) return;
  ending = true; gateway.revoke('harness-exit'); worker?.kill();
  setTimeout(() => { gateway.tick(); clearInterval(timer); worker?.kill('SIGKILL'); }, 250);
}
input.on('close', shutdown);
process.on('SIGTERM', shutdown);
