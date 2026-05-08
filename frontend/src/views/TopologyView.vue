<template>
  <div class="topology-page fade-in">
    <div class="toolbar topology-toolbar">
      <el-button type="primary" @click="loadTopology" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新拓扑
      </el-button>
      <el-button type="success" @click="discoverLinks" :loading="discovering">
        <el-icon><Connection /></el-icon> 重新生成拓扑图
      </el-button>
      <el-tag type="success">端口链路 {{ foundEdges.length }}</el-tag>
      <el-tag type="info">关联线 {{ associationEdges.length }}</el-tag>
      <el-button v-if="!(zoom === 1 && panX === 0 && panY === 0)" size="small" @click="resetView">重置视图</el-button>
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
        ref="canvasRef"
        class="topology-canvas"
        v-loading="loading || discovering"
        @mousedown="onCanvasMouseDown"
        @mousemove="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        @mouseleave="onCanvasMouseUp"
        @wheel.prevent="onCanvasWheel"
      >
        <div class="canvas-viewport">
          <svg class="topology-svg" :viewBox="viewBoxStr" preserveAspectRatio="xMinYMin meet">
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
import { computed, ref, onMounted } from 'vue'
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

// 画布状态 — viewBox 直接控制
const canvasRef = ref(null)
const vbx = ref(0)    // viewBox x
const vby = ref(0)    // viewBox y
const vbw = ref(1400) // viewBox width
const vbh = ref(800)  // viewBox height
const isPanning = ref(false)
const panStart = { x: 0, y: 0 }
const panStartBox = { x: 0, y: 0 }

const NODE_R = 34
const COL_SWITCH_X = 220
const COL_SERVER_X = 1180
const TOP_PAD = 60
const NODE_GAP = 90

// 从 viewBox 推导 zoom（相对于基准宽度 1400）
const zoom = computed(() => +(1400 / vbw.value).toFixed(2))

const viewBoxStr = computed(() => `${vbx.value} ${vby.value} ${vbw.value} ${vbh.value}`)

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundEdges = computed(() => edges.value.filter(e => e.kind === 'discovered' && e.status === 'found'))
const associationEdges = computed(() => edges.value.filter(e => e.kind === 'association'))

/** 节点从顶部向下排布 */
function verticalLayout(list, startX) {
  const count = list.length
  if (count === 0) return []
  return list.map((node, i) => ({
    ...node,
    x: startX,
    y: TOP_PAD + i * (NODE_R * 2 + NODE_GAP) + NODE_R,
  }))
}

const positionedNodes = computed(() => {
  return [
    ...verticalLayout(switchNodes.value, COL_SWITCH_X),
    ...verticalLayout(serverNodes.value, COL_SERVER_X),
  ]
})

const nodeMap = computed(() => {
  const map = new Map()
  positionedNodes.value.forEach(node => map.set(node.id, node))
  return map
})

/** 计算圆边交点 */
function circleEdge(cx, cy, tx, ty, radius) {
  const dx = tx - cx
  const dy = ty - cy
  const len = Math.sqrt(dx * dx + dy * dy)
  if (len === 0) return { x: cx, y: cy }
  const ratio = radius / len
  return { x: cx + dx * ratio, y: cy + dy * ratio }
}

const positionedEdges = computed(() => {
  const r = NODE_R

  // 统计同一对 (source, target) 的发现链路数量
  const pairCount = {}
  const pairIndex = {}
  edges.value.forEach(edge => {
    if (edge.status === 'not_found') return
    if (edge.kind !== 'discovered') return
    const key = `${edge.source}|${edge.target}`
    if (!pairCount[key]) pairCount[key] = 0
    pairCount[key]++
  })
  edges.value.forEach(edge => {
    if (edge.status === 'not_found') return
    if (edge.kind !== 'discovered') return
    const key = `${edge.source}|${edge.target}`
    if (!(key in pairIndex)) pairIndex[key] = 0
    pairIndex[key]++
  })

  return edges.value
    .map(edge => {
      const source = nodeMap.value.get(edge.source)
      const target = nodeMap.value.get(edge.target)
      if (!source || !target) return null
      if (edge.status === 'not_found') return null

      // 计算偏移（仅 discovered 多线偏移，association 不偏移）
      let offset = 0
      if (edge.kind === 'discovered') {
        const key = `${edge.source}|${edge.target}`
        const total = pairCount[key] || 1
        const idx = pairIndex[key]
        if (pairIndex[key] !== undefined) pairIndex[key]--
        offset = total > 1 ? (idx - (total + 1) / 2) * 28 : 0
      }

      // 从圆心算起，先算圆边交点
      const sCenter = circleEdge(source.x, source.y, target.x, target.y, r)
      const tCenter = circleEdge(target.x, target.y, source.x, source.y, r)

      // 加上垂直偏移
      const dx = target.x - source.x
      const dy = target.y - source.y
      const len = Math.sqrt(dx * dx + dy * dy)
      const ux = len > 0 ? -dy / len : 0
      const uy = len > 0 ? dx / len : 0

      const sx = sCenter.x + ux * offset
      const sy = sCenter.y + uy * offset
      const tx = tCenter.x + ux * offset
      const ty = tCenter.y + uy * offset

      const mx = (sx + tx) / 2
      const my = (sy + ty) / 2

      return {
        ...edge,
        source, target,
        sx, sy, tx, ty,
        labelX: Math.round(mx),
        labelY: Math.round(my),
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

// ── 画布拖拽平移（viewBox 直接偏移） ──
function onCanvasMouseDown(event) {
  if (event.button !== 0) return
  isPanning.value = true
  panStart.x = event.clientX
  panStart.y = event.clientY
  panStartBox.x = vbx.value
  panStartBox.y = vby.value
}

function onCanvasMouseMove(event) {
  if (!isPanning.value) return
  // 鼠标拖拽方向与 viewBox 偏移方向一致
  const container = canvasRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  // 像素到 viewBox 坐标的比例
  const scaleX = vbw.value / rect.width
  const scaleY = vbh.value / rect.height
  vbx.value = panStartBox.x + (panStart.x - event.clientX) * scaleX
  vby.value = panStartBox.y + (panStart.y - event.clientY) * scaleY
}

function onCanvasMouseUp() {
  isPanning.value = false
}

function onCanvasWheel(event) {
  const container = canvasRef.value
  if (!container) return
  const rect = container.getBoundingClientRect()
  // 鼠标在 viewBox 坐标系中的位置
  const mx = vbx.value + (event.clientX - rect.left) / rect.width * vbw.value
  const my = vby.value + (event.clientY - rect.top) / rect.height * vbh.value

  const factor = event.deltaY > 0 ? 1.2 : 1 / 1.2
  const newW = Math.max(400, Math.min(8000, vbw.value * factor))
  const newH = Math.max(300, Math.min(6000, vbh.value * factor))

  // 保持鼠标位置不变
  vbx.value = mx - (event.clientX - rect.left) / rect.width * newW
  vby.value = my - (event.clientY - rect.top) / rect.height * newH
  vbw.value = newW
  vbh.value = newH
}

function resetView() {
  vbx.value = 0
  vby.value = 0
  vbw.value = 1400
  vbh.value = 800
}

function calcSvgHeight() {
  const maxCount = Math.max(switchNodes.value.length, serverNodes.value.length)
  const h = TOP_PAD + maxCount * (NODE_R * 2 + NODE_GAP) + 80
  return Math.max(800, h)
}

function publishStats() {
  emit('stats', {
    found: foundEdges.value.length,
    pending: edges.value.filter(e => e.status !== 'found').length,
  })
}

async function loadTopology() {
  loading.value = true
  resetView()
  try {
    const data = await topologyApi.get()
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    links.value = data.links || []
    // 根据节点数量动态调整 viewBox 高度
    const h = calcSvgHeight()
    vbw.value = 1400
    vbh.value = h
    vbx.value = 0
    vby.value = 0
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
  display: flex;
  align-items: stretch;
}

.topology-canvas:active {
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
