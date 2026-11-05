// Automated synthetic inputs only: never use these answers for a real handover.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
const child = spawn(process.execPath, [fileURLToPath(new URL('./process-experiment.ts', import.meta.url))], {
  stdio: ['pipe', 'pipe', 'inherit'],
});
let id = 0;
let completed = false;
const command = (type: string, data: object = {}) => child.stdin.write(JSON.stringify({ id: ++id, type, ...data }) + '\n');
const timeout = setTimeout(() => { console.error('Demo timeout'); child.stdin.end(); process.exitCode = 1; }, 4000);
const lines = createInterface({ input: child.stdout });
lines.on('line', line => {
  const message = JSON.parse(line);
  if (message.value?.runnerPid) console.log('Gateway PID ' + message.value.gatewayPid + '; runner PID ' + message.value.runnerPid);
  if (message.event === 'prompt') {
    const answer = message.choices[0];
    console.log('Synthetic answer: ' + message.message + ' -> ' + answer);
    command('answer', { promptId: message.id, session: message.session, answer, clearToMove: message.stationary });
  }
  if (message.event === 'terminal') console.log('Motion: ' + message.status + ' (' + message.reason + ')');
  if (message.event === 'say') console.log('Service: ' + message.message);
  if (message.event === 'service-result') {
    completed = message.status === 'completed';
    console.log('Service result: ' + message.status); child.stdin.end();
  }
  if (message.ok === false) { console.error(message.error); child.stdin.end(); }
});
child.on('exit', code => { clearTimeout(timeout); lines.close(); if (!completed || code !== 0) process.exitCode = 1; });
command('start');
