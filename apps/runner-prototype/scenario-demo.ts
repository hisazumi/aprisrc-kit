import { loadScenarios, runScenario, saveTrace } from './service-scenarios.ts';
const directory = process.argv[2];
if (!directory || process.argv.length !== 3) throw new Error('Usage: node apps/runner-prototype/scenario-demo.ts TRACE_DIRECTORY');
if (!process.env.APRIS_PYTHON) throw new Error('Set APRIS_PYTHON to the server virtualenv Python');
for (const scenario of loadScenarios()) {
  const trace = await runScenario(scenario); saveTrace(trace, directory);
  console.log(`${scenario.id}: ${trace.passed ? 'PASS' : 'FAIL ' + trace.error}`);
  if (!trace.passed) process.exitCode = 1;
}
