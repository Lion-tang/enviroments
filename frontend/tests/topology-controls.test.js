import assert from 'node:assert/strict'
import test from 'node:test'

import { discoveryServerIds, selectedServerFromNode } from '../src/views/topology-controls.js'

test('selected server is the only topology discovery target', () => {
  const server = { id: 'server-42', type: 'server', entity_id: 42 }

  assert.strictEqual(selectedServerFromNode(server), server)
  assert.deepEqual(discoveryServerIds(server), [42])
})

test('switch or empty selection has no server discovery target', () => {
  const switchNode = { id: 'switch-7', type: 'switch', entity_id: 7 }

  assert.equal(selectedServerFromNode(switchNode), null)
  assert.equal(discoveryServerIds(switchNode), null)
  assert.equal(selectedServerFromNode(null), null)
  assert.equal(discoveryServerIds(null), null)
})
