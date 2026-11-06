import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseControlMessage } from './control-contract.ts';
const cases = JSON.parse(readFileSync(new URL('./fixtures/control-v1.json', import.meta.url), 'utf8'));
for (const c of cases) {
  test('control wire fixture: ' + c.name, () => {
    if (c.valid) assert.deepEqual(parseControlMessage(c.message), c.message);
    else assert.throws(() => parseControlMessage(c.message));
  });
}
