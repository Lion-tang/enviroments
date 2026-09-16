<template>
  <div class="topology-page fade-in">
    <div class="toolbar topology-toolbar">
      <el-button type="primary" @click="loadTopology" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新拓扑
      </el-button>
      <el-button type="success" @click="discoverLinks" :loading="discovering">
        <el-icon><Connection /></el-icon> 重新生成拓扑图
      </el-button>
      <el-tag type="success">链路 {{ foundLinks.length }}</el-tag>
      <el-tag type="info">交换机 {{ switchNodes.length }}</el-tag>
      <el-tag type="info">服务器 {{ serverNodes.length }}</el-tag>
      <el-button v-if="!isDefaultView" size="small" @click="resetView">重置视图</el-button>
    </div>

    <div class="topology-layout">
      <section
        ref="canvasRef"
        class="topology-canvas"
        :class="{ dragging: isPanning }"
        v-loading="loading || discovering"
        @mousedown="onCanvasMouseDown"
        @wheel.prevent="onCanvasWheel"
      >
        <div class="canvas-viewport">
          <svg class="topology-svg" :viewBox="viewBoxStr" preserveAspectRatio="xMidYMin meet">
            <path
              v-for="edge in positionedEdges"
              :key="edge.id"
              :d="edge.pathD"
              class="topology-edge"
              :class="{ dim: !edge.related, active: edge.active }"
            />
            <path
              v-for="edge in positionedAssocEdges"
              :key="edge.id"
              :d="edge.pathD"
              class="topology-edge assoc-edge"
              :class="{ dim: !edge.related, active: edge.active }"
            />

            <g
              v-for="node in positionedNodes"
              :key="node.id"
              class="topology-node"
              :class="[node.type, { active: node.active, dim: !node.related, offline: node.online === false }]"
              :transform="`translate(${node.x}, ${node.y})`"
              @click.stop="selectNode(node)"
              @dblclick.stop="openDetail(node)"
            >
              <template v-if="node.type === 'switch'">
                <rect x="-82" y="-38" width="164" height="76" rx="8" />
                <text class="node-title" text-anchor="middle" y="-7">{{ node.label }}</text>
                <text class="node-sub" text-anchor="middle" y="14">{{ node.ip }}</text>
                <text class="node-sub" text-anchor="middle" y="32">{{ switchLinkCount(node.entity_id) }} links</text>
              </template>
              <template v-else>
                <rect x="-84" y="-44" width="168" :height="serverBoxHeight(node)" rx="8" />
                <text class="server-ip" text-anchor="middle" y="-15">{{ node.ip }}</text>
                <text
                  v-for="(line, index) in serverLinkLabels(node.entity_id)"
                  :key="`${node.id}-line-${index}`"
                  class="server-line"
                  text-anchor="middle"
                  :y="16 + index * 13"
                >
                  {{ line }}
                </text>
              </template>
            </g>
          </svg>
        </div>

        <div class="canvas-legend">
          <span><i class="legend-found"></i> 已发现链路</span>
          <span><i class="legend-assoc"></i> 已关联未发现</span>
          <span>滚轮缩放 · 按住拖拽 · 底部拖动条横向移动</span>
        </div>
        <div ref="scrollbarRef" class="canvas-scrollbar" @mousedown="onScrollbarMouseDown">
          <div ref="thumbRef" class="canvas-thumb" @mousedown.stop="onThumbMouseDown"></div>
        </div>
        <el-empty v-if="!nodes.length" description="暂无拓扑数据" />
      </section>

      <aside class="inspector-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">{{ selectedNodeTitle }}</div>
            <div class="panel-subtitle">{{ selectedNodeSubtitle }}</div>
          </div>
          <el-button
            v-if="selectedNode"
            size="small"
            @click="openDetail(selectedNode)"
          >
            详情
          </el-button>
        </div>

        <div v-if="selectedRows.length" class="detail-list">
          <div v-for="row in selectedRows" :key="row.id" class="detail-row">
            <strong>{{ row.title }}</strong>
            <span>{{ row.vlan }}</span>
            <span>{{ row.description }}</span>
          </div>
        </div>
        <el-empty v-else description="点击交换机或服务器查看接口详情" />

        <div class="panel-footer">
          <div class="footer-item">
            <span>多链路服务器</span>
            <strong>{{ multiLinkServerCount }}</strong>
          </div>
          <div class="footer-item">
            <span>VLAN 数</span>
            <strong>{{ vlanCount }}</strong>
          </div>
        </div>
      </aside>
    </div>

    <ServerDetail :serverId="activeServerId" @close="activeServerId = null" @server-updated="loadTopology" />
    <SwitchDetail :switchId="activeSwitchId" @close="activeSwitchId = null" @switch-updated="loadTopology" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Refresh } from '@element-plus/icons-vue'
import { topology as topologyApi } from '../api/index.js'
import ServerDetail from '../components/ServerDetail.vue'
import SwitchDetail from '../components/SwitchDetail.vue'

const emit = defineEmits(['stats'])

const loading = ref(false)
const discovering = ref(false)
const nodes = ref([])
const edges = ref([])
const links = ref([])
const selectedNodeId = ref(null)
const activeServerId = ref(null)
const activeSwitchId = ref(null)

const canvasRef = ref(null)
const scrollbarRef = ref(null)
const thumbRef = ref(null)
const view = ref({ x: 0, y: 0, w: 2200, h: 1040 })
const world = ref({ width: 2200, height: 1040 })
const isPanning = ref(false)
const isDraggingThumb = ref(false)
const panStart = { x: 0, y: 0, vx: 0, vy: 0 }

const SWITCH_GAP = 560
const SWITCH_Y = 120
const SERVER_START_Y = 310
const SERVER_COL_GAP = 240
const SERVER_ROW_GAP = 118
const SERVER_COLS = 2

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundLinks = computed(() => links.value.filter(link => link.status === 'found'))
const viewBoxStr = computed(() => `${view.value.x} ${view.value.y} ${view.value.w} ${view.value.h}`)
const isDefaultView = computed(() => view.value.x === 0 && view.value.y === 0 && view.value.w === world.value.width)

const nodeMap = computed(() => {
  const map = new Map()
  nodes.value.forEach(node => map.set(node.id, node))
  return map
})

const selectedNode = computed(() => nodeMap.value.get(selectedNodeId.value) || null)

const serverPrimarySwitch = computed(() => {
  const map = new Map()
  for (const link of foundLinks.value) {
    if (!map.has(link.server_id)) map.set(link.server_id, link.switch_id)
  }
  for (const edge of edges.value) {
    if (edge.kind === 'association') {
      const serverId = Number(String(edge.target).replace('server-', ''))
      const switchId = Number(String(edge.source).replace('switch-', ''))
      if (!map.has(serverId)) map.set(serverId, switchId)
    }
  }
  return map
})

const linksByServer = computed(() => {
  const map = new Map()
  for (const link of foundLinks.value) {
    if (!map.has(link.server_id)) map.set(link.server_id, [])
    map.get(link.server_id).push(link)
  }
  return map
})

const linksBySwitch = computed(() => {
  const map = new Map()
  for (const link of foundLinks.value) {
    if (!map.has(link.switch_id)) map.set(link.switch_id, [])
    map.get(link.switch_id).push(link)
  }
  return map
})

const positionedSwitches = computed(() =>
  switchNodes.value.map((node, index) => ({
    ...node,
    x: 245 + index * SWITCH_GAP,
    y: SWITCH_Y,
  }))
)

const positionedServers = computed(() => {
  const switchIndex = new Map(positionedSwitches.value.map((node, index) => [node.entity_id, index]))
  const grouped = new Map()
  for (const server of serverNodes.value) {
    const switchId = serverPrimarySwitch.value.get(server.entity_id)
    if (!switchId) continue
    if (!grouped.has(switchId)) grouped.set(switchId, [])
    grouped.get(switchId).push(server)
  }

  const positioned = []
  for (const [switchId, servers] of grouped.entries()) {
    const index = switchIndex.get(switchId)
    if (index == null) continue
    const switchX = 245 + index * SWITCH_GAP
    const startX = switchX - 120
    servers
      .slice()
      .sort((a, b) => naturalCompare(a.ip, b.ip))
      .forEach((server, serverIndex) => {
        positioned.push({
          ...server,
          x: startX + (serverIndex % SERVER_COLS) * SERVER_COL_GAP,
          y: SERVER_START_Y + Math.floor(serverIndex / SERVER_COLS) * SERVER_ROW_GAP,
        })
      })
  }
  return positioned
})

const positionedNodes = computed(() => {
  const items = [...positionedSwitches.value, ...positionedServers.value]
  return items.map(node => ({
    ...node,
    active: node.id === selectedNodeId.value,
    related: isNodeRelated(node),
  }))
})

const positionedNodeMap = computed(() => {
  const map = new Map()
  positionedNodes.value.forEach(node => map.set(node.id, node))
  return map
})

function makeEdgePath(source, target, offsetY = 0) {
  const sx = source.x
  const sy = source.y + 38
  const tx = target.x
  const ty = target.y - 44
  const midY = sy + 70 + offsetY
  return `M${sx},${sy} C${sx},${midY} ${tx},${midY} ${tx},${ty}`
}

const positionedEdges = computed(() =>
  foundLinks.value
    .map(link => {
      const source = positionedNodeMap.value.get(`switch-${link.switch_id}`)
      const target = positionedNodeMap.value.get(`server-${link.server_id}`)
      if (!source || !target) return null
      const samePairLinks = foundLinks.value.filter(item =>
        item.switch_id === link.switch_id && item.server_id === link.server_id
      )
      const pairIndex = samePairLinks.findIndex(item => item.id === link.id)
      const offset = samePairLinks.length > 1 ? (pairIndex - (samePairLinks.length - 1) / 2) * 18 : 0
      return {
        ...link,
        id: `link-${link.id}`,
        source,
        target,
        active: selectedNodeId.value === source.id || selectedNodeId.value === target.id,
        related: isLinkRelated(link),
        pathD: makeEdgePath(source, target, offset),
      }
    })
    .filter(Boolean)
)

const positionedAssocEdges = computed(() =>
  edges.value
    .filter(e => e.kind === 'association')
    .map(edge => {
      const source = positionedNodeMap.value.get(edge.source)
      const target = positionedNodeMap.value.get(edge.target)
      if (!source || !target) return null
      const sid = Number(String(edge.source).replace('switch-', ''))
      const tid = Number(String(edge.target).replace('server-', ''))
      return {
        ...edge,
        source,
        target,
        active: selectedNodeId.value === edge.source || selectedNodeId.value === edge.target,
        related: isAssocRelated(edge),
        pathD: makeEdgePath(source, target, 0),
      }
    })
    .filter(Boolean)
)

const selectedNodeTitle = computed(() => {
  const node = selectedNode.value
  if (!node) return '选择节点'
  return node.type === 'server' ? node.ip : node.label
})

const selectedNodeSubtitle = computed(() => {
  const node = selectedNode.value
  if (!node) return '点击交换机或服务器查看接口详情'
  if (node.type === 'server') {
    const rows = linksByServer.value.get(node.entity_id) || []
    return `${rows.length} 条接口链路`
  }
  const rows = linksBySwitch.value.get(node.entity_id) || []
  return `${node.ip} · ${rows.length} 条链路`
})

const selectedRows = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  const rows = node.type === 'server'
    ? linksByServer.value.get(node.entity_id) || []
    : linksBySwitch.value.get(node.entity_id) || []
  return rows.map(link => {
    const switchNode = nodeMap.value.get(`switch-${link.switch_id}`)
    const serverNode = nodeMap.value.get(`server-${link.server_id}`)
    const device = link.server_device_model ? ` ${link.server_device_model}` : ''
    return {
      id: link.id,
      title: node.type === 'server'
        ? `${switchNode?.label || '交换机'} ${link.switch_interface || '-'} → ${link.server_interface || '-'}${device}`
        : `${link.switch_interface || '-'} → ${serverNode?.ip || '服务器'} ${link.server_interface || '-'}${device}`,
      vlan: link.vlan ? `VLAN ${link.vlan}` : 'VLAN -',
      description: link.server_mac || '端口链路',
    }
  })
})

const multiLinkServerCount = computed(() =>
  [...linksByServer.value.values()].filter(rows => rows.length > 1).length
)

const vlanCount = computed(() => {
  const vlans = new Set(foundLinks.value.map(link => link.vlan).filter(Boolean))
  return vlans.size
})

function naturalCompare(a, b) {
  return String(a || '').localeCompare(String(b || ''), undefined, { numeric: true, sensitivity: 'base' })
}

function switchLinkCount(id) {
  return (linksBySwitch.value.get(id) || []).length
}

function serverLinkLabels(id) {
  const rows = (linksByServer.value.get(id) || []).slice(0, 3)
  if (!rows.length) return ['未发现端口']
  return rows.map(link => {
    const device = link.server_device_model ? ` ${link.server_device_model}` : ''
    return `${link.switch_interface || '-'} ↔ ${link.server_interface || '-'}${device}`
  })
}

function serverBoxHeight(node) {
  const count = Math.max(1, Math.min(3, (linksByServer.value.get(node.entity_id) || []).length))
  return count > 1 ? 100 : 82
}

function isLinkRelated(link) {
  if (!selectedNodeId.value) return true
  const selected = selectedNode.value
  if (!selected) return true
  if (selected.type === 'switch') return link.switch_id === selected.entity_id
  return link.server_id === selected.entity_id
}

function isAssocRelated(edge) {
  if (!selectedNodeId.value) return true
  const selected = selectedNode.value
  if (!selected) return true
  const sid = Number(String(edge.source).replace('switch-', ''))
  const tid = Number(String(edge.target).replace('server-', ''))
  if (selected.type === 'switch') return sid === selected.entity_id
  return tid === selected.entity_id
}

function isNodeRelated(node) {
  if (!selectedNodeId.value) return true
  const selected = selectedNode.value
  if (!selected) return true
  if (node.id === selected.id) return true
  if (selected.type === 'switch') {
    if (node.type === 'switch') return node.entity_id === selected.entity_id
    return (linksBySwitch.value.get(selected.entity_id) || []).some(link => link.server_id === node.entity_id)
  }
  if (selected.type === 'server') {
    if (node.type === 'server') return node.entity_id === selected.entity_id
    return (linksByServer.value.get(selected.entity_id) || []).some(link => link.switch_id === node.entity_id)
  }
  return true
}

function selectNode(node) {
  selectedNodeId.value = node.id
}

function openDetail(node) {
  if (node.type === 'server') activeServerId.value = node.entity_id
  if (node.type === 'switch') activeSwitchId.value = node.entity_id
}

function calcWorld() {
  const width = Math.max(980, 500 + Math.max(switchNodes.value.length - 1, 0) * SWITCH_GAP)
  let maxServerRows = 1
  for (const switchNode of switchNodes.value) {
    const count = serverNodes.value.filter(server =>
      serverPrimarySwitch.value.get(server.entity_id) === switchNode.entity_id
    ).length
    maxServerRows = Math.max(maxServerRows, Math.ceil(count / SERVER_COLS))
  }
  const height = Math.max(760, SERVER_START_Y + maxServerRows * SERVER_ROW_GAP + 120)
  world.value = { width, height }
}

function resetView() {
  calcWorld()
  view.value = { x: 0, y: 0, w: world.value.width, h: world.value.height }
  nextTick(updateScrollbar)
}

function clampView() {
  const current = view.value
  current.w = Math.max(520, current.w)
  current.h = Math.max(360, current.h)
  current.x = Math.max(0, Math.min(world.value.width - current.w, current.x))
  current.y = Math.max(0, Math.min(world.value.height - current.h, current.y))
}

function applyView() {
  clampView()
  view.value = { ...view.value }
  nextTick(updateScrollbar)
}

function updateScrollbar() {
  const scrollbar = scrollbarRef.value
  const thumb = thumbRef.value
  if (!scrollbar || !thumb) return
  const rect = scrollbar.getBoundingClientRect()
  const ratio = view.value.w / world.value.width
  const thumbW = Math.max(54, rect.width * ratio)
  const maxLeft = rect.width - thumbW
  const left = world.value.width === view.value.w ? 0 : (view.value.x / (world.value.width - view.value.w)) * maxLeft
  thumb.style.width = `${thumbW}px`
  thumb.style.left = `${left}px`
}

function onCanvasMouseDown(event) {
  if (event.button !== 0) return
  isPanning.value = true
  panStart.x = event.clientX
  panStart.y = event.clientY
  panStart.vx = view.value.x
  panStart.vy = view.value.y
}

function onWindowMouseMove(event) {
  if (isPanning.value) {
    const rect = canvasRef.value?.getBoundingClientRect()
    if (!rect) return
    view.value.x = panStart.vx + (panStart.x - event.clientX) * (view.value.w / rect.width)
    view.value.y = panStart.vy + (panStart.y - event.clientY) * (view.value.h / rect.height)
    applyView()
  }
  if (isDraggingThumb.value) {
    const rect = scrollbarRef.value?.getBoundingClientRect()
    const thumbRect = thumbRef.value?.getBoundingClientRect()
    if (!rect || !thumbRect) return
    const maxLeft = rect.width - thumbRect.width
    const left = Math.max(0, Math.min(maxLeft, event.clientX - rect.left - thumbRect.width / 2))
    view.value.x = maxLeft <= 0 ? 0 : (left / maxLeft) * (world.value.width - view.value.w)
    applyView()
  }
}

function onWindowMouseUp() {
  isPanning.value = false
  isDraggingThumb.value = false
}

function onCanvasWheel(event) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const mx = view.value.x + (event.clientX - rect.left) / rect.width * view.value.w
  const my = view.value.y + (event.clientY - rect.top) / rect.height * view.value.h
  const factor = event.deltaY > 0 ? 1.025 : 1 / 1.025
  const newW = view.value.w * factor
  const newH = view.value.h * factor
  view.value.x = mx - (event.clientX - rect.left) / rect.width * newW
  view.value.y = my - (event.clientY - rect.top) / rect.height * newH
  view.value.w = newW
  view.value.h = newH
  applyView()
}

function onThumbMouseDown() {
  isDraggingThumb.value = true
}

function onScrollbarMouseDown(event) {
  if (event.target === thumbRef.value) return
  const rect = scrollbarRef.value?.getBoundingClientRect()
  const thumbRect = thumbRef.value?.getBoundingClientRect()
  if (!rect || !thumbRect) return
  const maxLeft = rect.width - thumbRect.width
  const left = Math.max(0, Math.min(maxLeft, event.clientX - rect.left - thumbRect.width / 2))
  view.value.x = maxLeft <= 0 ? 0 : (left / maxLeft) * (world.value.width - view.value.w)
  applyView()
}

function publishStats() {
  emit('stats', {
    found: foundLinks.value.length,
    pending: edges.value.filter(e => e.status !== 'found').length,
  })
}

async function loadTopology() {
  loading.value = true
  try {
    const data = await topologyApi.get()
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    links.value = data.links || []
    if (!selectedNodeId.value && nodes.value.length) {
      selectedNodeId.value = switchNodes.value[0]?.id || serverNodes.value[0]?.id || null
    }
    resetView()
    publishStats()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载拓扑失败')
  } finally {
    loading.value = false
  }
}

async function discoverLinks() {
  discovering.value = true
  try {
    await topologyApi.discover()
    ElMessage.success('链路发现完成')
    await loadTopology()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '链路发现失败')
  } finally {
    discovering.value = false
  }
}

onMounted(() => {
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
  window.addEventListener('resize', updateScrollbar)
  loadTopology()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
  window.removeEventListener('resize', updateScrollbar)
})
</script>

<style scoped>
.topology-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.topology-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.topology-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  min-height: calc(100vh - 180px);
}

.topology-canvas,
.inspector-panel {
  background: var(--bg-card);
  border: 3px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

.topology-canvas {
  min-height: calc(100vh - 180px);
  overflow: hidden;
  position: relative;
  cursor: grab;
  display: flex;
}

.topology-canvas.dragging {
  cursor: grabbing;
}

.canvas-viewport {
  overflow: hidden;
  width: 100%;
  height: 100%;
  display: flex;
}

.topology-svg {
  width: 100%;
  height: 100%;
  display: block;
  user-select: none;
}

.topology-edge {
  fill: none;
  stroke: var(--online);
  stroke-width: 2.2;
  stroke-linecap: round;
  opacity: 0.55;
}

.topology-edge.dim {
  opacity: 0.08;
}

.topology-edge.active {
  stroke-width: 3.4;
  opacity: 1;
}

.topology-node {
  cursor: pointer;
}

.topology-node rect {
  fill: #fff;
  stroke: var(--border);
  stroke-width: 3;
  rx: 18;
}

.topology-node.switch rect {
  stroke: var(--online);
  fill: rgba(0, 184, 148, 0.08);
}

.topology-node.active rect {
  stroke: var(--online);
  stroke-width: 3;
}

.topology-node.dim {
  opacity: 0.26;
}

.topology-node.offline rect {
  stroke: var(--offline);
}

.node-title {
  fill: var(--text-primary);
  font-size: 18px;
  font-weight: 800;
}

.node-sub {
  fill: var(--text-secondary);
  font-size: 14px;
}

.server-ip {
  fill: var(--text-primary);
  font-size: 18px;
  font-weight: 800;
}

.server-line {
  fill: var(--text-secondary);
  font-size: 13px;
}

.canvas-legend {
  position: absolute;
  left: 18px;
  bottom: 34px;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 9px 12px;
  border: 2px solid var(--border);
  border-radius: 999px;
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
}

.topology-edge.assoc-edge {
  stroke: var(--sky);
  stroke-width: 2.2;
  stroke-dasharray: 6 4;
  opacity: 0.5;
}

.topology-edge.assoc-edge.active {
  stroke-width: 2.5;
  opacity: 1;
}

.topology-edge.assoc-edge.dim {
  opacity: 0.08;
}

.canvas-legend i {
  width: 30px;
  height: 3px;
  border-radius: 3px;
  background: var(--online);
  display: inline-block;
  margin-right: 6px;
  vertical-align: middle;
}

.canvas-legend i.legend-assoc {
  background: var(--sky);
}

.canvas-scrollbar {
  position: absolute;
  left: 20px;
  right: 20px;
  bottom: 14px;
  height: 14px;
  border-radius: 999px;
  background: var(--cream-strong);
  border: 2px solid var(--border);
  cursor: pointer;
}

.canvas-thumb {
  position: absolute;
  top: 2px;
  height: 8px;
  min-width: 54px;
  border-radius: 999px;
  background: var(--accent);
  cursor: grab;
}

.canvas-thumb:active {
  cursor: grabbing;
}

.inspector-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 180px);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 2px solid var(--border-light);
}

.panel-title {
  color: var(--text-primary);
  font-weight: 800;
  font-size: 19px;
}

.panel-subtitle {
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 3px;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 14px;
  overflow: auto;
}

.detail-row {
  background: #fffaf6;
  border: 2px solid var(--border);
  border-radius: 18px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-row strong {
  color: var(--text-primary);
  font-size: 13px;
}

.detail-row span {
  color: var(--text-secondary);
  font-size: 12px;
}

.panel-footer {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 2px solid var(--border-light);
}

.footer-item {
  background: #fffaf6;
  border: 2px solid var(--border);
  border-radius: 18px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
}

.footer-item strong {
  color: var(--text-primary);
}

@media (max-width: 1100px) {
  .topology-layout {
    grid-template-columns: 1fr;
  }

  .inspector-panel {
    min-height: 420px;
  }
}
</style>
