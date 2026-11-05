import { runPythonTrial } from './python-experiment.ts';
const result = await runPythonTrial();
console.log(JSON.stringify(result, null, 2));
if (!result.events.some(e => e.kind === 'service-result' && e.status === 'completed')) process.exitCode = 1;
