// Local test harness over stdin/stdout; not an authenticated UI or robot protocol.
import { createInterface } from 'node:readline';
import { Runtime } from './runtime.ts';
const runtime = new Runtime();
const write = (value: unknown) => process.stdout.write(JSON.stringify(value) + '\n');
const input = createInterface({ input: process.stdin });
input.on('line', line => {
  let id: unknown;
  try {
    const request = JSON.parse(line);
    id = request.id;
    let value: unknown;
    switch (request.type) {
      case 'start':
        if (typeof request.service !== 'string' || !request.service) throw new Error('invalid-service');
        value = runtime.start(request.service); break;
      case 'move': {
        const operation = runtime.move(request.scope, request.duration);
        value = operation.token;
        void operation.result.then(result => write({ operation: operation.token, result }));
        break;
      }
      case 'cancel': runtime.cancel(request.scope); break;
      case 'pause': runtime.paused = true; break;
      case 'resume': runtime.paused = false; break;
      case 'step': runtime.step(request.dt); break;
      case 'reset': runtime.reset(); break;
      case 'stop': runtime.globalStop(); break;
      case 'snapshot': value = runtime.snapshot(); break;
      default: throw new Error('unknown-command');
    }
    write({ id, ok: true, value });
  } catch (error) { write({ id, ok: false, error: String(error) }); }
});
input.on('close', () => runtime.globalStop());
