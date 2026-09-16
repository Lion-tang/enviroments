# Topology Controls and Compact Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-scoped topology rediscovery, hover explanations, a permanent ARP limitation notice, and a desktop topology layout that fits within the viewport.

**Architecture:** Keep rendering and request orchestration inside the existing `TopologyView.vue` component and reuse `topology.discover(serverIds)`. Extract the selected-server decision and shared UI copy into a small dependency-free module, test its observable inputs and outputs with Node's built-in test runner, then validate the compiled Vue application and rendered browser behavior.

**Tech Stack:** Vue 3 Composition API, Element Plus, Axios, scoped CSS, Node.js built-in test runner, Vite 5.

## Global Constraints

- `刷新当前服务器` is visible only while a server node is selected.
- Button explanations are hover tooltips; they are not permanently displayed text.
- The ARP/MAC-learning limitation is permanently visible above the canvas and cannot be closed.
- Desktop topology height is `clamp(500px, calc(100dvh - 300px), 740px)`.
- Use the existing `POST /api/v1/topology/discover` request with `server_ids`; do not add routes or change the database schema.
- Full and single-server rediscovery must not overlap.
- Do not refactor unrelated graph rendering, pan, zoom, or persistence code.

---

## File Map

- Create `frontend/src/views/topology-controls.js`: own topology help copy and derive a refreshable server/ID list from the selected node.
- Create `frontend/tests/topology-controls.test.js`: verify server and non-server selection behavior using Node's built-in test runner.
- Modify `frontend/src/views/TopologyView.vue`: render tooltips and the permanent alert from shared copy, add the server-only action and request state, and constrain the desktop layout height.

### Task 1: Topology controls and compact layout

**Files:**
- Create: `frontend/src/views/topology-controls.js`
- Create: `frontend/tests/topology-controls.test.js`
- Modify: `frontend/src/views/TopologyView.vue`

**Interfaces:**
- Consumes: `topologyApi.discover(serverIds = null) -> Promise<object>` from `frontend/src/api/index.js`.
- Produces: `selectedServerFromNode(node) -> node | null` and `discoveryServerIds(node) -> number[] | null` from `topology-controls.js`.
- Produces: `discoverLinks(serverIds = null) -> Promise<void>` and `discoverSelectedServer() -> Promise<void> | undefined` inside `TopologyView.vue`.

- [ ] **Step 1: Write the failing selected-server behavior test**

Create `frontend/tests/topology-controls.test.js`:

```js
import assert from 'node:assert/strict'
import test from 'node:test'

import { discoveryServerIds, selectedServerFromNode } from '../src/views/topology-controls.js'

test('selected server is the only topology discovery target', () => {
  const server = { id: 'server-42', type: 'server', entity_id: 42 }

  assert.strictEqual(selectedServerFromNode(server), server)
  assert.deepEqual(discoveryServerIds(server), [42])
})

test('switch or empty selection has no server discovery target', () => {
  assert.equal(selectedServerFromNode({ id: 'switch-7', type: 'switch', entity_id: 7 }), null)
  assert.equal(discoveryServerIds({ id: 'switch-7', type: 'switch', entity_id: 7 }), null)
  assert.equal(selectedServerFromNode(null), null)
  assert.equal(discoveryServerIds(null), null)
})
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
cd frontend
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test tests\topology-controls.test.js
```

Expected: RED because `topology-controls.js` and its selected-server behavior do not exist yet. If the initial run reports a missing module, add the two exported function stubs returning `null` and rerun until the server-target assertion fails for the expected behavioral reason.

- [ ] **Step 3: Implement the selected-server behavior and shared copy**

Create `frontend/src/views/topology-controls.js` with the minimal functions needed to satisfy the tests, plus `TOPOLOGY_HELP` and `TOPOLOGY_NOTICE` constants containing the exact approved copy. Rerun the focused Node tests and expect `2 passed`.

- [ ] **Step 4: Add tooltip and permanent-notice markup**

In `TopologyView.vue`, wrap `刷新拓扑`, `重新生成拓扑图`, and conditional `重置视图` buttons in `el-tooltip`. Use these exact `content` values:

```text
读取已有拓扑结果，不重新扫描设备
扫描全部服务器并更新拓扑结果
恢复画布的缩放比例和位置
```

Insert this non-closable alert between `.topology-toolbar` and `.topology-layout`:

```vue
<el-alert class="topology-notice" type="info" :closable="false" show-icon>
  <template #title>
    拓扑发现方式：服务器通过每个 UP 状态的网口发送 ARP 探测，再到已关联的交换机查询是否学习到该接口的 MAC 地址。因此，发现的链路不能保证两端为物理直连。
  </template>
</el-alert>
```

- [ ] **Step 5: Add scoped rediscovery state and the server-only action**

Add a selected-server computed value and identify which request is active:

```js
const discoveringServerId = ref(null)
const selectedServer = computed(() => selectedServerFromNode(selectedNode.value))
```

Replace the existing discovery function and add the guarded action:

```js
async function discoverLinks(serverIds = null) {
  if (discovering.value) return
  discovering.value = true
  discoveringServerId.value = serverIds?.[0] ?? null
  try {
    await topologyApi.discover(serverIds)
    ElMessage.success(serverIds ? '当前服务器链路发现完成' : '链路发现完成')
    await loadTopology()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '链路发现失败')
  } finally {
    discovering.value = false
    discoveringServerId.value = null
  }
}

function discoverSelectedServer() {
  const serverIds = discoveryServerIds(selectedNode.value)
  if (!serverIds) return
  return discoverLinks(serverIds)
}
```

In `.panel-header`, group actions in `.panel-actions`. Add an `el-tooltip` with content `仅扫描右侧当前选中的服务器`, and render its button only with `v-if="selectedServer"`. Bind `@click="discoverSelectedServer"`, `:disabled="discovering"`, and a loading expression that is true only when `discoveringServerId === selectedServer.entity_id`. Keep the existing `详情` action.

Disable the full rediscovery action while `discovering` is true and keep the canvas loading mask bound to `loading || discovering`.

- [ ] **Step 6: Constrain the work area and make the inspector scroll internally**

Change the component spacing and desktop layout rules to:

```css
.topology-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.topology-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  height: clamp(500px, calc(100dvh - 300px), 740px);
  min-height: 0;
}

.topology-canvas,
.inspector-panel {
  height: 100%;
  min-height: 0;
}

.detail-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
```

At `max-width: 1100px`, restore natural stacked sizing:

```css
.topology-layout {
  height: auto;
}

.topology-canvas {
  min-height: 500px;
}

.inspector-panel {
  min-height: 420px;
}
```

- [ ] **Step 7: Run the focused behavior tests and verify GREEN**

Run:

```powershell
cd frontend
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test tests\topology-controls.test.js
```

Expected: `2 passed`.

- [ ] **Step 8: Run regression tests and the production build**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -v
cd ..\frontend
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' --test tests\topology-controls.test.js
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' '.\node_modules\vite\bin\vite.js' build
```

Expected: every backend test passes and Vite exits with code 0. Existing upstream deprecation warnings may remain, but there must be no new error.

- [ ] **Step 9: Verify in the running browser**

At `http://127.0.0.1:3000/`, verify:

1. The ARP notice is always visible above the canvas.
2. Every topology button shows its exact help text on hover.
3. Selecting a server displays `刷新当前服务器`; selecting a switch hides it.
4. Single-server refresh sends one server ID, finishes without clearing unrelated links, and preserves the selection.
5. At a desktop viewport of at least 768px height, the complete canvas and inspector fit without scrolling the page.
6. Long inspector link lists scroll inside the inspector.

- [ ] **Step 10: Commit the implementation**

```powershell
git add -- frontend/src/views/topology-controls.js frontend/tests/topology-controls.test.js frontend/src/views/TopologyView.vue
git commit -m "feat: improve topology controls and layout"
```
