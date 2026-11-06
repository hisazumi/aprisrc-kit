// Explicit fake-only scenario: recognition, operator presence and answers are synthetic.
import { myService } from '../pwa/src/missions/myService.ts';
import { runFakeService } from './service-host.ts';
const report = await runFakeService(myService, {
  recoveryClearance: true,
  operatorPresent: () => true,
  waitForPerson: async () => {},
  prompt: async q => ({ value: q.choices[0], humanClear: q.stationary }),
  say: () => {},
});
console.log(JSON.stringify({ target: 'fake-only', ...report }, null, 2));
