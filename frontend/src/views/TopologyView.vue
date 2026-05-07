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
      <el-tag v-if="dragNodeId" type="warning">拖拽中...</el-tag>
    </div>

    <div class="topology-layout">
      <section class="topology-canvas" v-loading="loading || discovering">
        <svg
          v-if="nodes.length"
          class="topology-svg"
          :viewBox="`0 0 ${canvas.width} ${canvas.height}`"
          :style="{ height: canvas.height + 'px' }"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
        >
          <!-- 连线 -->
          <line
            v-for="edge in positionedEdges"
            :key="edge.id"
            :x1="edge.source.x"
            :y1="edge.source.y"
            :x2="edge.target.x"
            :y2="edge.target.y"
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
          <!-- 节点（可拖拽） -->
          <g
            v-for="node in positionedNodes"
            :key="node.id"
            class="topology-node"
            :class="[node.type, { offline: node.online === false, dragging: dragNodeId === node.id }]"
            :transform="`translate(${node.x}, ${node.y})`"
            @mousedown.prevent="onNodeDragStart(node.id, $event)"
            @click.stop="openNode(node)"
          >
            <circle r="34" />
            <text class="node-icon" text-anchor="middle" y="-3">{{ node.type === 'switch' ? 'SW' : 'SRV' }}</text>
            <text class="node-ip-label" text-anchor="middle" y="52">{{ node.ip }}</text>
            <text class="node-label-tiny" text-anchor="middle" y="70">{{ node.label }}</text>
          </g>
        </svg>
        <el-empty v-else description="暂无拓扑数据" />
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
import { computed, onMounted, reactive, ref } from 'vue'
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

// 拖拽状态
const dragNodeId = ref(null)
const dragOffset = { x: 0, y: 0 }
const nodePositions = reactive({})  // { nodeId: { x, y } }

const canvasWidth = 1120

const canvas = computed(() => {
  const count = Math.max(nodes.value.length, 1)
  const height = Math.max(680, count * 120 + 80)
  return { width: canvasWidth, height }
})

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundEdges = computed(() => edges.value.filter(e => e.kind === 'discovered' && e.status === 'found'))
const associationEdges = computed(() => edges.value.filter(e => e.kind === 'association'))

/**
 * 初始布局：左列交换机，右列服务器，自适应间距
 */
function computeInitialPositions() {
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
}

/**
 * 根据 nodePositions（含拖拽偏移）+ 未拖拽过的节点自动取初始布局
 */
const positionedNodes = computed(() => {
  const initial = computeInitialPositions()
  return initial.map(node => {
    const pos = nodePositions[node.id]
    if (pos) {
      return { ...node, x: pos.x, y: pos.y }
    }
    return node
  })
})

const nodeMap = computed(() => {
  const map = new Map()
  positionedNodes.value.forEach(node => map.set(node.id, node))
  return map
})

const positionedEdges = computed(() => edges.value
  .map(edge => {
    const source = nodeMap.value.get(edge.source)
    const target = nodeMap.value.get(edge.target)
    if (!source || !target) return null
    return {
      ...edge,
      source,
      target,
      labelX: Math.round((source.x + target.x) / 2),
      labelY: Math.round((source.y + target.y) / 2),
    }
  })
  .filter(Boolean)
)

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

// ── 拖拽逻辑 ──
function onNodeDragStart(nodeId, event) {
  // 阻止点击穿透导致打开详情
  event.stopPropagation()
  dragNodeId.value = nodeId
  const pos = nodePositions[nodeId] || {}
  const nodeEl = positionedNodes.value.find(n => n.id === nodeId)
  if (nodeEl) {
    dragOffset.x = event.offsetX - (nodeEl.x - (pos.x || 0))
    dragOffset.y = event.offsetY - (nodeEl.y - (pos.y || 0))
  }
}

function onMouseMove(event) {
  if (!dragNodeId.value) return
  const svg = event.currentTarget
  const rect = svg.getBoundingClientRect()
  const scaleX = canvas.value.width / rect.width
  const scaleY = canvas.value.height / rect.height
  const svgX = Math.round((event.clientX - rect.left) * scaleX - dragOffset.x)
  const svgY = Math.round((event.clientY - rect.top) * scaleY - dragOffset.y)
  nodePositions[dragNodeId.value] = { x: svgX, y: svgY }
}

function onMouseUp() {
  dragNodeId.value = null
}

function publishStats() {
  emit('stats', {
    found: foundEdges.value.length,
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
    // 重置拖拽位置（拓扑变了，旧位置不适用）
    Object.keys(nodePositions).forEach(k => delete nodePositions[k])
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
}

.topology-svg {
  width: 100%;
  display: block;
  overflow-x: auto;
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
  cursor: grab;
  transition: none;
}

.topology-node:active {
  cursor: grabbing;
}

.topology-node.dragging circle {
  stroke-width: 4;
  filter: drop-shadow(0 2px 8px rgba(0,0,0,0.3));
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

.node-icon {
  fill: var(--text-primary);
  font-weight: 700;
  font-size: 13px;
}

.node-ip-label {
  fill: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.node-label-tiny {
  fill: var(--text-muted);
  font-size: 11px;
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

@media (max-width: 1000px) {
  .topology-layout {
    grid-template-columns: 1fr;
  }

  .link-panel {
    max-height: 340px;
  }
}
</style>
