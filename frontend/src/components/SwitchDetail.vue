<template>
  <el-drawer v-model="drawerVisible" :title="`交换机 ${switchName}`" size="560px" direction="rtl">

    <el-tabs v-model="activeTab">

      <!-- ── 详情 ─────────────────────────────────────────── -->
      <el-tab-pane label="详情" name="detail">
        <template v-if="detail">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
            <el-descriptions-item label="IP">{{ detail.ip }}</el-descriptions-item>
            <el-descriptions-item label="端口">{{ detail.port }}</el-descriptions-item>
            <el-descriptions-item label="用户名">{{ detail.username }}</el-descriptions-item>
            <el-descriptions-item label="密码">{{ detail.password || '—' }}</el-descriptions-item>
            <el-descriptions-item label="系统类型">{{ detail.os_type || '—' }}</el-descriptions-item>
            <el-descriptions-item label="系统版本">{{ detail.os_version || '—' }}</el-descriptions-item>
            <el-descriptions-item label="补丁版本">{{ detail.patch_version || '—' }}</el-descriptions-item>
            <el-descriptions-item label="设备型号">{{ detail.board_type || '—' }}</el-descriptions-item>
            <el-descriptions-item label="主机名">{{ detail.hostname || '—' }}</el-descriptions-item>
            <el-descriptions-item label="运行时间">{{ detail.uptime || '—' }}</el-descriptions-item>
            <el-descriptions-item label="CPU 使用率">{{ detail.cpu != null ? detail.cpu + '%' : '—' }}</el-descriptions-item>
            <el-descriptions-item label="内存使用率">{{ detail.mem != null ? detail.mem + '%' : '—' }}</el-descriptions-item>
            <el-descriptions-item label="标签">{{ detail.tags || '—' }}</el-descriptions-item>
            <el-descriptions-item label="备注">{{ detail.description || '—' }}</el-descriptions-item>
            <el-descriptions-item label="关联服务器">
              <el-tag v-for="s in assocServers" :key="s.id" size="small" style="margin-right:4px">{{ s.ip }}</el-tag>
              <span v-if="!assocServers.length">—</span>
            </el-descriptions-item>
            <el-descriptions-item label="采集时间">{{ detail.cached_at || '—' }}</el-descriptions-item>
          </el-descriptions>

          <el-divider v-if="detail.interfaces?.length">网卡</el-divider>
          <el-table v-if="detail.interfaces?.length" :data="detail.interfaces" size="small" max-height="200">
            <el-table-column prop="name" label="网卡" width="90" />
            <el-table-column prop="ip" label="IP" min-width="120" />
            <el-table-column prop="mac" label="MAC" width="140" />
            <el-table-column prop="pci_addr" label="PCI 地址" width="110" show-overflow-tooltip />
            <el-table-column prop="pci_desc" label="PCI 设备" min-width="180" show-overflow-tooltip />
            <el-table-column prop="speed" label="速率" width="80" />
          </el-table>
          <el-empty v-else description="暂无网卡信息" />
        </template>

        <el-empty v-else-if="initialLoading" description="加载中…" />

        <div class="detail-actions">
          <el-button type="primary" size="small" @click="fetchDetail" :loading="fetchingDetail">
            <el-icon><Refresh /></el-icon> 重新采集
          </el-button>
          <el-button size="small" @click="checkStatus">检测状态</el-button>
          <el-button size="small" @click="openEdit">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteSwitch">删除</el-button>
        </div>
      </el-tab-pane>

      <!-- ── 日志 ──────────────────────────────────────────── -->
      <el-tab-pane label="日志" name="logs">
        <div class="log-toolbar">
          <el-button size="small" @click="loadLogs" :loading="loadingLogs">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
          <el-button size="small" type="danger" @click="clearLogs">
            清空日志
          </el-button>
        </div>

        <div class="log-container" v-loading="loadingLogs">
          <div v-if="logs.length === 0" class="log-empty">暂无日志记录</div>
          <div v-else class="log-list">
            <div v-for="(log, i) in logs" :key="i" class="log-line" :class="logClass(log)">
              <span class="log-time">{{ log.time || '—' }}</span>
              <span class="log-type">{{ log.type === 'status_check' ? '状态' : '详情' }}</span>
              <span class="log-status" :class="log.online ? 'online' : 'offline'">
                {{ log.online === true ? '在线' : log.online === false ? '离线' : '—' }}
              </span>
              <span v-if="log.cpu" class="log-info">CPU {{ log.cpu }}核</span>
              <span v-if="log.mem" class="log-info">内存 {{ log.mem }}MB</span>
              <span v-if="log.os_version" class="log-info">{{ log.os_version }}</span>
              <span v-if="log.error" class="log-error">{{ log.error }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>

    </el-tabs>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { switches as switchApi } from '../api/index.js'
import { serverSwitchAssoc } from '../api/index.js'
import { switchLogs } from '../api/index.js'

const props = defineProps({ switchId: { type: Number, default: null } })

const drawerVisible = computed({
  get: () => !!props.switchId,
  set: () => emit('close'),
})
const emit = defineEmits(['close', 'switch-updated'])

const activeTab = ref('detail')
const detail = ref(null)
const initialLoading = ref(true)
const fetchingDetail = ref(false)
const switchName = ref('')
const logs = ref([])
const loadingLogs = ref(false)
const assocServers = ref([])

// ── Detail load ──────────────────────────────────────────────────────────────────

const detailCache = new Map()
const CACHE_TTL = 60_000

watch(() => props.switchId, async (id) => {
  if (!id) return
  activeTab.value = 'detail'

  const cached = detailCache.get(id)
  if (cached) {
    detail.value = cached.detail
    switchName.value = cached.detail.name
    initialLoading.value = false
  } else {
    initialLoading.value = true
    detail.value = null
  }

  try {
    const data = await switchApi.getDetail(id)
    detail.value = data
    switchName.value = data.name
    detailCache.set(id, { detail: data, timestamp: Date.now() })
    try {
      assocServers.value = await switchApi.getServers(id)
    } catch {
      assocServers.value = []
    }
  } catch (e) {
    if (!cached) ElMessage.error('加载详情失败')
  } finally {
    initialLoading.value = false
  }
}, { immediate: true })

async function fetchDetail() {
  fetchingDetail.value = true
  try {
    detail.value = await switchApi.fetchDetail(props.switchId, true)
    switchName.value = detail.value.name
    detailCache.set(props.switchId, { detail: detail.value, timestamp: Date.now() })
    ElMessage.success('采集成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '采集失败')
  } finally {
    fetchingDetail.value = false
  }
}

async function checkStatus() {
  try {
    const result = await switchApi.checkStatus(props.switchId)
    if (detail.value) {
      detail.value.is_online = result.online
    }
    ElMessage.success(`${detail.value?.name || ''}: ${result.online ? '在线' : '离线'}`)
  } catch {
    ElMessage.error('检测失败')
  }
}

function openEdit() {
  emit('close')
  emit('open-edit', props.switchId)
}

async function deleteSwitch() {
  try {
    await ElMessageBox.confirm('确定删除该交换机？', '确认', { type: 'warning' })
    await switchApi.delete(props.switchId)
    ElMessage.success('已删除')
    emit('switch-updated')
    emit('close')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

// ── Logs ─────────────────────────────────────────────────────────────────────────

watch(activeTab, (tab) => {
  if (tab === 'logs') {
    loadLogs()
  }
})

async function loadLogs() {
  if (!props.switchId) return
  loadingLogs.value = true
  try {
    const data = await switchLogs.list(props.switchId, 200, 0)
    logs.value = data.logs
  } catch {
    ElMessage.error('加载日志失败')
  } finally {
    loadingLogs.value = false
  }
}

async function clearLogs() {
  try {
    await ElMessageBox.confirm('确定清空该交换机的所有日志？', '确认', { type: 'warning' })
    await switchLogs.clear(props.switchId)
    logs.value = []
    ElMessage.success('已清空')
  } catch {}
}

function logClass(log) {
  if (log.error) return 'log-error-row'
  if (log.online === false) return 'log-offline-row'
  return ''
}
</script>

<style scoped>
.detail-actions { display: flex; gap: 8px; margin-top: 16px; }

.log-toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.log-container { border: 1px solid var(--border); border-radius: 6px; max-height: 400px; overflow-y: auto; }
.log-empty { padding: 24px; text-align: center; color: var(--text-muted); }
.log-list { font-family: 'Consolas', monospace; font-size: 12px; }
.log-line { display: flex; align-items: center; gap: 8px; padding: 5px 10px; border-bottom: 1px solid var(--border-light); flex-wrap: wrap; }
.log-line:last-child { border-bottom: none; }
.log-offline-row { background: rgba(248, 81, 73, 0.08); }
.log-error-row { background: rgba(248, 81, 73, 0.05); }
.log-time { color: var(--text-muted); white-space: nowrap; }
.log-type { color: var(--accent); font-weight: 500; }
.log-status { font-size: 12px; }
.log-status.online { color: var(--online); }
.log-status.offline { color: var(--offline); }
.log-info { color: var(--text-secondary); }
.log-error { color: var(--offline); }
</style>