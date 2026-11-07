import { registeredDelivery } from '../pwa/src/missions/registeredDelivery.ts';
import { myService } from '../pwa/src/missions/myService.ts';
import { runConsoleService } from './console-connection.ts';
const token = process.env.APRIS_CONSOLE_TOKEN;
if (!token) throw new Error('Set APRIS_CONSOLE_TOKEN to the token in the printed console URL fragment');
const name = process.env.APRIS_SERVICE ?? 'carry';
if (!['carry', 'registered-delivery'].includes(name)) throw new Error('unknown-service');
const definition = name === 'registered-delivery' ? registeredDelivery : myService;
console.log(JSON.stringify(await runConsoleService(definition, token, { launchId: process.env.APRIS_LAUNCH_ID, origin: process.env.APRIS_CONSOLE_ORIGIN }), null, 2));
