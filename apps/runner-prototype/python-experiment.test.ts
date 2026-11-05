import test from 'node:test';
import assert from 'node:assert/strict';
import { runPythonTrial, type TrialMode } from './python-experiment.ts';
// Explicit opt-in because the original runner experiment requires Node only.
for (const mode of ['normal', 'decline', 'kill', 'block', 'disconnect', 'missing-evidence', 'delayed-evidence'] as TrialMode[]) {
  test('Python RoverRuntime port: ' + mode, { skip: !process.env.APRIS_PYTHON, timeout: 10000 }, async () => {
    const result = await runPythonTrial(mode);
    assert.equal(result.state.target, 'fake-only'); assert.equal(result.state.moving, false);
    const terminals = result.events.filter(e => e.kind === 'terminal').map(e => e.event);
    assert.ok(terminals.length > 0);
    if (['normal', 'decline', 'delayed-evidence'].includes(mode)) {
      assert.ok(result.events.some(e => e.kind === 'service-result' && e.status === 'completed'));
    } else if (mode === 'missing-evidence') {
      assert.ok(terminals.some(e => e.status === 'stop-unconfirmed'));
      assert.equal(result.state.inhibited, true);
      assert.ok(result.events.some(e => e.kind === 'service-result' && e.status === 'failed'));
    } else {
      assert.ok(terminals.some(e => e.status === 'interrupted'));
      assert.equal(result.state.session, null);
    }
  });
}
