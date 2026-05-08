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
      <el-button v-if="zoom !== 1" size="small" @click="resetView">重置视图</el-button>
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
          <svg class="topology-svg" :viewBox="`0 0 ${svgW} ${svgH}`" preserveAspectRatio="xMidYMid meet">
            <g :transform="`scale(${zoom}) translate(${panX}, ${panY})`">
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
import { computed, ref, onMounted, nextTick } from 'vue'
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

// 画布状态
const canvasRef = ref(null)
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStart = { x: 0, y: 0 }
const panStartOffset = { x: 0, y: 0 }

// SVG 画布固定尺寸（单位：px，viewBox 坐标空间）
const svgW = 1400
const svgH = 800

// 节点半径
const NODE_R = 34
// 左边交换机列 x 坐标，右边服务器列 x 坐标
const COL_SWITCH_X = 220
const COL_SERVER_X = 1180
// top padding（顶部留间隙）
const TOP_PAD = 60
// 节点之间最小间距
const NODE_GAP = 90

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundEdges = computed(() => edges.value.filter(e => e.kind === 'discovered' && e.status === 'found'))
const associationEdges = computed(() => edges.value.filter(e => e.kind === 'association'))

/** 节点从顶部 startY 向下排布 */
function verticalLayout(list, startX) {
  const count = list.length
  if (count === 0) return []
  // 计算总高度，用 SVG 高度兜底
  const totalH = count * (NODE_R * 2 + NODE_GAP) - NODE_GAP
  const offsetY = TOP_PAD
  return list.map((node, i) => ({
    ...node,
    x: startX,
    y: offsetY + i * (NODE_R * 2 + NODE_GAP) + NODE_R,
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

/**
 * 从圆心到圆边的交点
 * 从 (cx,cy) 到 (tx,ty) 方向缩短 radius 距离
 */
function circleEdge(cx, cy, tx, ty, radius) {
  const dx = tx - cx
  const dy = ty - cy
  const len = Math.sqrt(dx * dx + dy * dy)
  if (len === 0) return { x: cx, y: cy }
  const ratio = radius / len
  return {
    x: cx + dx * ratio,
    y: cy + dy * ratio,
  }
}

const positionedEdges = computed(() => {
  const r = NODE_R
  return edges.value
    .map(edge => {
      const source = nodeMap.value.get(edge.source)
      const target = nodeMap.value.get(edge.target)
      if (!source || !target) return null

      // 只保留 found 和 association
      if (edge.status === 'not_found') return null

      // 从圆心坐标 => 圆边坐标
      const s = circleEdge(source.x, source.y, target.x, target.y, r)
      const t = circleEdge(target.x, target.y, source.x, source.y, r)

      const mx = (s.x + t.x) / 2
      const my = (s.y + t.y) / 2

      return {
        ...edge,
        source, target,
        sx: s.x, sy: s.y,
        tx: t.x, ty: t.y,
        labelX: Math.round(mx),
        labelY: Math.round(my),
        pathD: `M${s.x},${s.y} L${t.x},${t.y}`,
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
  if (event.button !== 0) return
  isPanning.value = true
  panStart.x = event.clientX
  panStart.y = event.clientY
  panStartOffset.x = panX.value
  panStartOffset.y = panY.value
}

function onCanvasMouseMove(event) {
  if (!isPanning.value) return
  panX.value = panStartOffset.x + (panStart.x - event.clientX) / (svgW * zoom.value * 0.0015)
  panY.value = panStartOffset.y + (panStart.y - event.clientY) / (svgW * zoom.value * 0.0015)
}

function onCanvasMouseUp() {
  isPanning.value = false
}

function onCanvasWheel(event) {
  const delta = event.deltaY > 0 ? -0.12 : 0.12
  zoom.value = Math.max(0.3, Math.min(5, zoom.value + delta))
}

function resetView() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

function publishStats() {
  emit('stats', {
    found: foundEdges.value.length,
    pending: edges.value.filter(e => e.status !== 'found').length,
  })
}

async function loadTopology() {
  loading.value = true
  zoom.value = 1
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
