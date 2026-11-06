// Explicit planar simulator scenario: recognition, operator presence and answers are synthetic.
import { myService } from '../pwa/src/missions/myService.ts';
import { runFakeService } from './service-host.ts';
const report = await runFakeService(myService, {
  recoveryClearance: true,
  operatorPresent: () => true,
  waitForPerson: async () => {},
  prompt: async q => ({ value: q.choices[0], humanClear: q.stationary }),
  say: () => {},
}, { backend: 'simulator' });
console.log(JSON.stringify({ target: 'planar-simulator', ...report }, null, 2));
