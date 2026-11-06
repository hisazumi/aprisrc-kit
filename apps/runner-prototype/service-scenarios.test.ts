import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScenarios, parseScenarios, runScenario, saveTrace } from './service-scenarios.ts';
const cases = loadScenarios();
for (const scenario of cases) test('scenario: ' + scenario.id, { skip: !process.env.APRIS_PYTHON, timeout: 22000 }, async () => {
  const trace = await runScenario(scenario);
  if (process.env.APRIS_SCENARIO_TRACE_DIR) saveTrace(trace, process.env.APRIS_SCENARIO_TRACE_DIR);
  assert.equal(trace.passed, true, JSON.stringify(trace));
});
test('scenario validation rejects unsafe names, extra operations, invalid expectations and duplicate IDs', () => {
  for (const change of [{ id: '../escape' }, { action: 'drive' }, { arrivalDelayMs: Infinity },
    { expected: { ...cases[0].expected, minX: NaN } }])
    assert.throws(() => parseScenarios([{ ...cases[0], ...change }]));
  assert.throws(() => parseScenarios([cases[0], cases[0]]));
});
