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
    </div>

    <div class="topology-layout">
      <section class="topology-canvas" v-loading="loading || discovering">
        <svg
          v-if="nodes.length"
          class="topology-svg"
          :viewBox="`0 0 ${canvas.width} ${canvas.height}`"
          :style="{ height: canvas.height + 'px' }"
          role="img"
        >
          <line
            v-for="edge in positionedEdges"
            :key="edge.id"
            :x1="edge.source.x"
            :y1="edge.source.y"
            :x2="edge.target.x"
            :y2="edge.target.y"
            :class="['topology-edge', edge.kind, edge.status]"
          />
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
          <g
            v-for="node in positionedNodes"
            :key="node.id"
            class="topology-node"
            :class="[node.type, { offline: node.online === false }]"
            :transform="`translate(${node.x}, ${node.y})`"
            @click="openNode(node)"
          >
            <circle r="34" />
            <text class="node-icon" text-anchor="middle" y="-3">{{ node.type === 'switch' ? 'SW' : 'SRV' }}</text>
            <text class="node-label" text-anchor="middle" y="54">{{ node.label }}</text>
            <text class="node-ip" text-anchor="middle" y="72">{{ node.ip }}</text>
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

const nodeRadius = 34
const nodeSpacing = 120   // 纵向间距
const canvasWidth = 1120

const canvas = computed(() => {
  const count = Math.max(nodes.value.length, 1)
  const height = Math.max(680, count * nodeSpacing + 80)
  return { width: canvasWidth, height }
})

const switchNodes = computed(() => nodes.value.filter(n => n.type === 'switch'))
const serverNodes = computed(() => nodes.value.filter(n => n.type === 'server'))
const foundEdges = computed(() => edges.value.filter(e => e.kind === 'discovered' && e.status === 'found'))
const associationEdges = computed(() => edges.value.filter(e => e.kind === 'association'))

/**
 * 自适应布局：根据每个节点的 assoc_count + 连接数决定 Y 坐标
 * 交换机列居左 (x=260)，服务器列居右 (x=820)
 * 每列节点按顺序均匀分布，间距自适应
 */
const positionedNodes = computed(() => {
  const result = []
  const swCount = switchNodes.value.length
  const svCount = serverNodes.value.length
  const h = canvas.value.height

  const switchGap = swCount > 1 ? (h - 80) / (swCount - 1) : h / 2
  const serverGap = svCount > 1 ? (h - 80) / (svCount - 1) : h / 2

  switchNodes.value.forEach((node, index) => {
    result.push({
      ...node,
      x: 260,
      y: swCount > 1 ? Math.round(40 + switchGap * index) : Math.round(h / 2),
    })
  })
  serverNodes.value.forEach((node, index) => {
    result.push({
      ...node,
      x: 820,
      y: svCount > 1 ? Math.round(40 + serverGap * index) : Math.round(h / 2),
    })
  })
  return result
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
    if (node.type === 'server') servers.set(node.entity_id, node.label || node.ip)
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
  if (status === 'found') return '已发现'
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
}

.topology-canvas {
  overflow-x: auto;
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

.node-icon {
  fill: var(--text-primary);
  font-weight: 700;
  font-size: 13px;
}

.node-label {
  fill: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.node-ip {
  fill: var(--text-muted);
  font-size: 12px;
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
