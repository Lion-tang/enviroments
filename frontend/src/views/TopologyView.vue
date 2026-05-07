<template>
  <div class="topology-page fade-in">
    <div class="toolbar topology-toolbar">
      <el-button type="primary" @click="loadTopology" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新拓扑
      </el-button>
      <el-button type="success" @click="discoverLinks" :loading="discovering">
        <el-icon><Connection /></el-icon> 发现链路
      </el-button>
      <el-tag type="success">端口链路 {{ foundEdges.length }}</el-tag>
      <el-tag type="info">关联线 {{ associationEdges.length }}</el-tag>
      <el-divider direction="vertical" />
      <span class="legend">
        <svg width="40" height="14" class="legend-svg"><line x1="0" y1="7" x2="40" y2="7" stroke="var(--online)" stroke-width="3" /></svg>
        已链接
        <svg width="40" height="14" class="legend-svg legend-dash"><line x1="0" y1="7" x2="40" y2="7" stroke="var(--warning)" stroke-width="2" stroke-dasharray="8 8" /></svg>
        未学习到
        <svg width="40" height="14" class="legend-svg"><line x1="0" y1="7" x2="40" y2="7" stroke="var(--text-muted)" stroke-width="2" stroke-dasharray="6 8" /></svg>
        仅关联
      </span>
    </div>

    <div class="topology-layout">
      <section
        class="topology-canvas"
        v-loading="loading || discovering"
        @mousedown="onCanvasMouseDown"
        @mousemove="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        @mouseleave="onCanvasMouseUp"
      >
        <div class="canvas-viewport" :style="{ width: canvasWidth + 'px', height: canvas.height + 'px' }">
          <svg class="topology-svg" :viewBox="viewBox">
            <!-- 连线 -->
            <path
              v-for="edge in positionedEdges"
              :key="edge.id"
              :d="edge.pathD"
              :class="['topology-edge', edge.kind, edge.status]"
            />
            <!-- 连线标签 -->
            <g
              v-for="edge in positionedEdges"
              :key="`${edge.id}-label`"
              class="edge-label"
              :transform="`translate(${edge.labelX}, ${edge.labelY})`"
            >
              <rect x="-70" y="-14" width="140" height="28" rx="6" />
              <text text-anchor="middle" dominant-baseline="middle">
                {{ edgeLabel(edge) }}
              </text>
            </g>
            <!-- 节点 -->
            <g
              v-for="node in positionedNodes"
              :key="node.id"
              class="topology-node"
              :class="[node.type, { offline: node.online === false }]"
              :transform="`translate(${node.x}, ${node.y})`"
              @click.stop="openNode(node)"
            >
              <circle r="34" />
              <text class="node-ip-in-circle" text-anchor="middle" dominant-baseline="central">{{ node.ip }}</text>
            </g>
          </svg>
        </div>
        <el-empty v-if="!nodes.length" description="暂无拓扑数据" />
      </section>

      <aside class="link-panel">
        <div class="panel-title">链路结果</div>
        <div v-if="links.length" class="link-list">
          <button
            v-for="link in links"
            :key="link.id"
            class="link-row"
            :class="link.status"
          >
            <span class="link-status">{{ statusText(link.status) }}</span>
            <strong>{{ serverName(link.server_id) }}</strong>
            <span>{{ link.server_interface }} / {{ link.server_mac }}</span>
            <span>{{ switchName(link.switch_id) }} · {{ link.switch_interface || '未学习到端口' }}</span>
            <small v-if="link.vlan">VLAN {{ link.vlan }}</small>
            <small v-if="link.error">{{ link.error }}</small>
          </button>
        </div>
        <el-empty v-else description="还没有发现记录" />
      </aside>
    </div>

    <ServerDetail :serverId="activeServerId" @close="activeServerId = null" @server-updated="loadTopology" />
    <SwitchDetail :switchId="activeSwitchId" @close="activeSwitchId = null" @switch-updated="loadTopology" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
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
const activeServerId = ref(null)
const activeSwitchId = ref(null)

// 画布平移
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStart = { x: 0, y: 0 }
const panStartOffset = { x: 0, y: 0 }

const canvasWidth = 1120
const canvasHeight = 660

const canvas = computed(() => {
  const count = Math.max(nodes.value.length, 1)
  const height = Math.max(680, count * 120 + 80)
  return { width: canvasWidth, height }
})

const viewBox = computed(() => {
  const w = canvas.value.width
  const h = canvas.value.height
  return `${panX.value} ${panY.value} ${w} ${h}`
})

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundEdges = computed(() => edges.value.filter(e => e.kind === 'discovered' && e.status === 'found'))
const associationEdges = computed(() => edges.value.filter(e => e.kind === 'association'))

const positionedNodes = computed(() => {
  const result = []
  const sw = switchNodes.value
  const sv = serverNodes.value
  const h = canvas.value.height

  const swGap = sw.length > 1 ? (h - 80) / (sw.length - 1) : h / 2
  const svGap = sv.length > 1 ? (h - 80) / (sv.length - 1) : h / 2

  sw.forEach((node, i) => {
    result.push({
      ...node,
      x: 260,
      y: sw.length > 1 ? Math.round(40 + swGap * i) : Math.round(h / 2),
    })
  })
  sv.forEach((node, i) => {
    result.push({
      ...node,
      x: 820,
      y: sv.length > 1 ? Math.round(40 + svGap * i) : Math.round(h / 2),
    })
  })
  return result
})

const nodeMap = computed(() => {
  const map = new Map()
  positionedNodes.value.forEach(node => map.set(node.id, node))
  return map
})

const positionedEdges = computed(() => {
  // 统计同一对 (source, target) 的 edge 数量，用于计算偏移
  const pairCount = {}
  const pairIndex = {}
  edges.value.forEach(edge => {
    const key = `${edge.source}|${edge.target}`
    if (!pairCount[key]) pairCount[key] = 0
    pairCount[key]++
  })
  edges.value.forEach(edge => {
    const key = `${edge.source}|${edge.target}`
    if (!(key in pairIndex)) pairIndex[key] = 0
    pairIndex[key]++
  })

  return edges.value
    .map(edge => {
      const source = nodeMap.value.get(edge.source)
      const target = nodeMap.value.get(edge.target)
      if (!source || !target) return null

      const key = `${edge.source}|${edge.target}`
      const total = pairCount[key] || 1
      const idx = pairIndex[key]--   // 从大到小
      const offset = total > 1 ? (idx - (total + 1) / 2) * 18 : 0

      const mx = (source.x + target.x) / 2
      const my = (source.y + target.y) / 2
      const dx = target.x - source.x
      const dy = target.y - source.y
      const len = Math.sqrt(dx * dx + dy * dy)
      // 垂直方向单位向量
      const ux = len > 0 ? -dy / len : 0
      const uy = len > 0 ? dx / len : 0

      // 两端偏移
      const sx = source.x + ux * offset
      const sy = source.y + uy * offset
      const tx = target.x + ux * offset
      const ty = target.y + uy * offset

      return {
        ...edge,
        source,
        target,
        sx, sy, tx, ty,
        labelX: Math.round(mx + ux * offset),
        labelY: Math.round(my + uy * offset),
        pathD: `M${sx},${sy} L${tx},${ty}`,
      }
    })
    .filter(Boolean)
})

const entityNames = computed(() => {
  const servers = new Map()
  const switches = new Map()
  nodes.value.forEach(node => {
    if (node.type === 'server') servers.set(node.entity_id, node.ip)
    if (node.type === 'switch') switches.set(node.entity_id, node.label || node.ip)
  })
  return { servers, switches }
})

function edgeLabel(edge) {
  if (edge.kind === 'association') return '关联'
  if (edge.status === 'found') return `${edge.switch_interface || '端口'} / ${edge.server_interface}`
  if (edge.status === 'error') return '查询失败'
  return '未学习到'
}

function statusText(status) {
  if (status === 'found') return '已链接'
  if (status === 'error') return '失败'
  return '未找到'
}

function serverName(id) {
  return entityNames.value.servers.get(id) || `服务器 #${id}`
}

function switchName(id) {
  return entityNames.value.switches.get(id) || `交换机 #${id}`
}

function openNode(node) {
  if (node.type === 'server') activeServerId.value = node.entity_id
  if (node.type === 'switch') activeSwitchId.value = node.entity_id
}

// ── 画布拖拽平移 ──
function onCanvasMouseDown(event) {
  isPanning.value = true
  panStart.x = event.clientX
  panStart.y = event.clientY
  panStartOffset.x = panX.value
  panStartOffset.y = panY.value
}

function onCanvasMouseMove(event) {
  if (!isPanning.value) return
  panX.value = panStartOffset.x + (panStart.x - event.clientX)
  panY.value = panStartOffset.y + (panStart.y - event.clientY)
}

function onCanvasMouseUp() {
  isPanning.value = false
}

function publishStats() {
  emit('stats', {
    found: foundEdges.value.length,
    pending: edges.value.filter(e => e.status !== 'found').length,
  })
}

async function loadTopology() {
  loading.value = true
  panX.value = 0
  panY.value = 0
  try {
    const data = await topologyApi.get()
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    links.value = data.links || []
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

onMounted(loadTopology)
</script>

<style scoped>
.topology-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.topology-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 2px;
}

.topology-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 14px;
  min-height: 680px;
}

.topology-canvas,
.link-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.topology-canvas {
  min-height: 680px;
  overflow: hidden;
  position: relative;
  cursor: grab;
}

.topology-canvas:active {
  cursor: grabbing;
}

.canvas-viewport {
  overflow: hidden;
}

.topology-svg {
  width: 100%;
  height: 100%;
  display: block;
  user-select: none;
}

.topology-edge {
  stroke: var(--text-muted);
  stroke-width: 2;
}

.topology-edge.discovered.found {
  stroke: var(--online);
  stroke-width: 3;
}

.topology-edge.discovered.not_found,
.topology-edge.discovered.error {
  stroke: var(--warning);
  stroke-dasharray: 8 8;
}

.topology-edge.association {
  stroke-dasharray: 6 8;
  opacity: 0.7;
}

.edge-label rect {
  fill: var(--bg-surface);
  stroke: var(--border);
}

.edge-label text {
  fill: var(--text-secondary);
  font-size: 12px;
}

.topology-node {
  cursor: pointer;
}

.topology-node circle {
  fill: var(--bg-surface);
  stroke: var(--aurora-green);
  stroke-width: 2;
}

.topology-node.switch circle {
  stroke: #58a6ff;
}

.topology-node.offline circle {
  stroke: var(--offline);
  opacity: 0.75;
}

.node-ip-in-circle {
  fill: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
}

.link-panel {
  padding: 14px;
  overflow: auto;
}

.panel-title {
  color: var(--text-primary);
  font-weight: 700;
  margin-bottom: 12px;
}

.link-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.link-row {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  color: var(--text-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
}

.link-row strong {
  color: var(--text-primary);
}

.link-row.found {
  border-color: rgba(55, 216, 57, 0.45);
}

.link-row.error {
  border-color: rgba(248, 81, 73, 0.45);
}

.link-status {
  color: var(--aurora-green);
  font-size: 12px;
  font-weight: 700;
}

.link-row.not_found .link-status {
  color: var(--warning);
}

.link-row.error .link-status {
  color: var(--offline);
}

.link-row small {
  color: var(--text-muted);
}

.legend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.legend .legend-svg {
  vertical-align: middle;
  margin: 0 2px 0 6px;
}

.legend .legend-svg:first-of-type {
  margin-left: 0;
}

@media (max-width: 1000px) {
  .topology-layout {
    grid-template-columns: 1fr;
  }

  .link-panel {
    max-height: 340px;
  }
}
</style>
