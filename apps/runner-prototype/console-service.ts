import { myService } from '../pwa/src/missions/myService.ts';
import { runConsoleService } from './console-connection.ts';
const token = process.env.APRIS_CONSOLE_TOKEN;
if (!token) throw new Error('Set APRIS_CONSOLE_TOKEN to the token in the printed console URL fragment');
console.log(JSON.stringify(await runConsoleService(myService, token, { launchId: process.env.APRIS_LAUNCH_ID, origin: process.env.APRIS_CONSOLE_ORIGIN }), null, 2));
