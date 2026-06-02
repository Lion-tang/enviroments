<template>
  <div class="server-card fade-in">
    <!-- Toolbar -->
    <div class="toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索 IP / 标签 / 系统版本 / 备注…"
        style="width: 260px"
        clearable
        :prefix-icon="Search"
        autocomplete="off"
      />
      <el-button type="primary" @click="openAdd">
        <el-icon><Plus /></el-icon> 添加服务器
      </el-button>
      <el-button @click="checkAllStatus" :loading="checkingAll">
        <el-icon><Refresh /></el-icon> 检测全部
      </el-button>
      <el-button :type="showFavoritesOnly ? 'warning' : 'default'" @click="showFavoritesOnly = !showFavoritesOnly">
        {{ showFavoritesOnly ? '显示全部' : '只看收藏' }}
      </el-button>
    </div>

    <!-- Server Table -->
    <el-table :data="filteredServers" v-loading="loading" class="server-table" style="width: 100%; table-layout: fixed; overflow-x: auto">
      <el-table-column label="状态" min-width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_online ? 'success' : 'danger'" size="small">
            {{ row.is_online ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP 地址" min-width="160" />
      <el-table-column prop="cached_os_version" label="系统版本" min-width="160" show-overflow-tooltip />
      <el-table-column prop="cached_cpu_model" label="CPU 型号" min-width="180" show-overflow-tooltip />
      <el-table-column prop="tags" label="标签" min-width="160">
        <template #default="{ row }">
          <template v-if="editingTagsId === row.id">
            <el-input
              v-model="editingTagsValue"
              size="small"
              style="width: 140px"
              @keyup.enter="saveTags(row.id)"
              @blur="saveTags(row.id)"
              ref="tagsInputRef"
              placeholder="多个标签用逗号分隔" autocomplete="off"
            />
          </template>
          <template v-else>
            <span class="tags-cell" @mousedown.prevent="startEditTags(row)" title="点击编辑标签">{{ row.tags || '—' }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="备注" width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="editingDescId === row.id">
            <el-input
              v-model="editingDescValue"
              type="textarea"
              size="small"
              :rows="3"
              :autosize="{ minRows: 3, maxRows: 6 }"
              class="inline-desc-editor"
              @keydown.enter.ctrl.prevent="saveDesc(row.id)"
              @blur="saveDesc(row.id)"
              ref="descInputRef"
              placeholder="备注，Ctrl + Enter 保存"
              autocomplete="off"
            />
          </template>
          <template v-else>
            <span class="tags-cell desc-cell" @mousedown.prevent="startEditDesc(row)" title="点击编辑备注">{{ row.description || '—' }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="DPU" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="editingDpuId === row.id">
            <el-input
              v-model="editingDpuValue"
              size="small"
              style="width: 140px"
              @keyup.enter="saveDpu(row.id)"
              @blur="saveDpu(row.id)"
              ref="dpuInputRef"
              placeholder="DPU 型号/信息" autocomplete="off"
            />
          </template>
          <template v-else>
            <span class="tags-cell" @mousedown.prevent="startEditDpu(row)" title="点击编辑DPU">{{ row.dpu || '—' }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="bmc_ip" label="BMC IP" min-width="150" show-overflow-tooltip />
      <el-table-column prop="bmc_username" label="BMC 用户名" min-width="120" show-overflow-tooltip />
      <el-table-column prop="bmc_password" label="BMC 密码" min-width="120" show-overflow-tooltip />
      <el-table-column label="使用人" min-width="150" align="center">
        <template #default="{ row }">
          <div v-if="row.occupied_by" class="occupy-cell">
            <span class="occupy-info">
              <span class="occupied-by" :title="`当前占用人：${row.occupied_by}`">{{ row.occupied_by }}</span>
              <span v-if="row.occupied_at" class="occupied-at">{{ formatOccupyTime(row.occupied_at) }}</span>
            </span>
            <el-link
              v-if="row.occupied_by === currentUsername"
              type="warning"
              @click="handleRelease(row)"
            >释放</el-link>
            <el-link
              v-else
              type="danger"
              @click="handleOccupy(row)"
            >强制占用</el-link>
          </div>
          <el-link v-else type="primary" @click="handleOccupy(row)">占用</el-link>
        </template>
      </el-table-column>
      <el-table-column label="关联交换机" min-width="120" align="center">
        <template #default="{ row }">
          <el-link type="primary" @click="openAssocDialog(row)">{{ row.assoc_switch_count ?? '—' }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="200" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openDetail(row)">查看详情</el-button>
          <el-button size="small" type="success" @click="openTerminal(row)">Web SSH</el-button>
        </template>
      </el-table-column>
      <el-table-column label="收藏" width="70" align="center">
        <template #default="{ row }">
          <button
            class="favorite-button"
            :class="{ active: row.is_favorite }"
            :title="row.is_favorite ? '取消收藏' : '收藏服务器'"
            @click.stop="toggleFavorite(row)"
          >
            {{ row.is_favorite ? '★' : '☆' }}
          </button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add/Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editing ? '编辑服务器' : '添加服务器'" width="520px">
      <el-form :model="form" label-width="100" ref="formRef">
        <el-form-item label="IP 地址" required>
          <el-input v-model="form.ip" placeholder="e.g. 192.168.1.10" />
        </el-form-item>
        <el-form-item label="SSH 端口" required>
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="系统类型" required>
          <el-radio-group v-model="form.os_type">
            <el-radio value="linux">Linux</el-radio>
            <el-radio value="windows">Windows</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="SSH 用户名" required>
          <el-input v-model="form.ssh_username" placeholder="e.g. root" @keyup.enter="saveServer" />
        </el-form-item>
        <el-form-item label="SSH 密码">
          <el-input v-model="form.ssh_password" show-password placeholder="留空则使用密钥" @keyup.enter="saveServer" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="e.g. 生产,Web,北京" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.description" type="textarea" rows="2" />
        </el-form-item>
        <el-form-item label="DPU">
          <el-input v-model="form.dpu" placeholder="DPU 型号/信息" />
        </el-form-item>
        <el-form-item label="BMC IP">
          <el-input v-model="form.bmc_ip" placeholder="e.g. 192.168.5.1" />
        </el-form-item>
        <el-form-item label="BMC 用户名">
          <el-input v-model="form.bmc_username" placeholder="e.g. admin" />
        </el-form-item>
        <el-form-item label="BMC 密码">
          <el-input v-model="form.bmc_password" placeholder="BMC 密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveServer" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Detail Drawer -->
    <ServerDetail :serverId="activeServerId" @close="activeServerId = null" @server-updated="loadServers" @open-edit="openEditById" />

    <!-- Assoc Dialog -->
    <el-dialog v-model="showAssocDialog" :title="`关联交换机 — ${assocTargetServer?.ip}`" width="480px">
      <el-select v-model="selectedSwitchIds" multiple placeholder="选择关联的交换机" style="width: 100%">
        <el-option v-for="sw in allSwitches" :key="sw.id" :label="`${sw.name} (${sw.ip})`" :value="sw.id" />
      </el-select>
      <template #footer>
        <el-button @click="showAssocDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAssoc" :loading="savingAssoc">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { servers as serverApi, switches as switchApi, serverSwitchAssoc } from '../api/index.js'
import ServerDetail from '../components/ServerDetail.vue'

const emit = defineEmits(['stats'])

const loading = ref(false)
const showAssocDialog = ref(false)
const savingAssoc = ref(false)
const assocTargetServer = ref(null)
const selectedSwitchIds = ref([])
const allSwitches = ref([])
const checkingAll = ref(false)
const showAddDialog = ref(false)
const servers = ref([])
const editing = ref(null)
const saving = ref(false)
const activeServerId = ref(null)
const searchQuery = ref('')
const showFavoritesOnly = ref(false)
const currentUsername = localStorage.getItem('username') || ''

const filteredServers = computed(() => {
  const source = showFavoritesOnly.value
    ? servers.value.filter(s => s.is_favorite)
    : servers.value
  if (!searchQuery.value.trim()) return source
  const q = searchQuery.value.trim().toLowerCase()
  return source.filter(s =>
    s.ip?.toLowerCase().includes(q) ||
    s.tags?.toLowerCase().includes(q) ||
    s.cached_os_version?.toLowerCase().includes(q) ||
    s.cached_cpu_model?.toLowerCase().includes(q) ||
    s.description?.toLowerCase().includes(q)
  )
})

const defaultForm = () => ({
  ip: '',
  port: 22,
  os_type: 'linux',
  ssh_username: '',
  ssh_password: '',
  ssh_key_file: null,
  description: '',
  tags: '',
  dpu: '',
  bmc_ip: '',
  bmc_username: '',
  bmc_password: '',
})

const form = ref(defaultForm())
const formRef = ref(null)
const editingTagsId = ref(null)
const editingTagsValue = ref('')
const tagsInputRef = ref(null)
const editingDescId = ref(null)
const editingDescValue = ref('')
const descInputRef = ref(null)

const editingDpuId = ref(null)
const editingDpuValue = ref('')
const dpuInputRef = ref(null)

function startEditDesc(row) {
  editingDescId.value = row.id
  editingDescValue.value = row.description || ''
  nextTick(() => descInputRef.value?.focus())
}

async function saveDesc(id) {
  if (editingDescId.value !== id) return
  const idx = servers.value.findIndex(s => s.id === id)
  if (idx === -1) return
  try {
    await serverApi.update(id, { description: editingDescValue.value })
    servers.value[idx] = { ...servers.value[idx], description: editingDescValue.value }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存备注失败')
  } finally {
    editingDescId.value = null
  }
}

function startEditDpu(row) {
  editingDpuId.value = row.id
  editingDpuValue.value = row.dpu || ''
  nextTick(() => dpuInputRef.value?.focus())
}

async function saveDpu(id) {
  if (editingDpuId.value !== id) return
  const server = servers.value.find(s => s.id === id)
  if (!server) return
  try {
    await serverApi.update(id, { dpu: editingDpuValue.value })
    server.dpu = editingDpuValue.value
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存DPU信息失败')
  } finally {
    editingDpuId.value = null
  }
}

function startEditTags(row) {
  editingTagsId.value = row.id
  editingTagsValue.value = row.tags || ''
  nextTick(() => tagsInputRef.value?.focus())
}

async function saveTags(id) {
  if (editingTagsId.value !== id) return
  const server = servers.value.find(s => s.id === id)
  if (!server) return
  try {
    await serverApi.update(id, { tags: editingTagsValue.value })
    server.tags = editingTagsValue.value
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存标签失败')
  } finally {
    editingTagsId.value = null
  }
}

async function loadServers() {
  loading.value = true
  try {
    const data = await serverApi.list()
    servers.value = data.servers
    emit('stats', {
      total: data.servers.length,
      online: data.servers.filter(s => s.is_online).length,
      offline: data.servers.filter(s => !s.is_online).length,
    })
  } catch {
    ElMessage.error('加载服务器列表失败')
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  activeServerId.value = row.id
}

function openTerminal(row) {
  const label = encodeURIComponent(row.ip)
  window.open(`/#/ssh/server/${row.id}/${label}`, '_blank')
}

function openAdd() {
  editing.value = null
  form.value = defaultForm()
  showAddDialog.value = true
}

function openEditById(id) {
  openEdit(servers.value.find(s => s.id === id))
}

function openEdit(row) {
  editing.value = row.id
  form.value = {
    ip: row.ip,
    port: row.port,
    os_type: row.os_type,
    ssh_username: row.ssh_username,
    ssh_password: row.ssh_password,
    ssh_key_file: row.ssh_key_file,
    description: row.description || '',
    tags: row.tags || '',
    dpu: row.dpu || '',
    bmc_ip: row.bmc_ip || '',
    bmc_username: row.bmc_username || '',
    bmc_password: row.bmc_password || '',
  }
  showAddDialog.value = true
}

async function saveServer() {
  if (saving.value) return
  saving.value = true
  try {
    if (editing.value) {
      await serverApi.update(editing.value, form.value)
      ElMessage.success('更新成功')
      showAddDialog.value = false
      editing.value = null
      form.value = defaultForm()
      await loadServers()
    } else {
      const created = await serverApi.create(form.value)
      ElMessage.success('添加成功')
      showAddDialog.value = false
      form.value = defaultForm()
      await refreshCreatedServerStatus(created.id)
      await loadServers()
      openDetail({ id: created.id })
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function refreshCreatedServerStatus(serverId) {
  try {
    await serverApi.checkStatus(serverId)
    await serverApi.fetchDetail(serverId, true)
  } catch (e) {
    ElMessage.warning('服务器已添加，但自动采集详情失败，可稍后手动重新采集')
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除服务器 "${row.ip}"？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await serverApi.delete(row.id)
    ElMessage.success('已删除')
    if (activeServerId.value === row.id) activeServerId.value = null
    await loadServers()
  } catch {}
}

async function checkAllStatus() {
  checkingAll.value = true
  const promises = servers.value.map(s => serverApi.checkStatus(s.id).catch(() => null))
  const results = await Promise.all(promises)
  await loadServers()
  checkingAll.value = false
  const online = results.filter(r => r?.online).length
  ElMessage.info(`检测完成：${online}/${results.length} 在线`)
}

async function handleOccupy(row) {
  try {
    const previousUser = row.occupied_by
    if (previousUser && previousUser !== currentUsername) {
      await ElMessageBox.confirm(
        `服务器 "${row.ip}" 当前由 ${previousUser} 占用，确定要强制占用吗？`,
        '确认强制占用',
        { type: 'warning', confirmButtonText: '强制占用', cancelButtonText: '取消' }
      )
    }
    const updated = await serverApi.occupy(row.id)
    const idx = servers.value.findIndex(s => s.id === row.id)
    if (idx !== -1) servers.value[idx] = { ...servers.value[idx], occupied_by: updated.occupied_by, occupied_at: updated.occupied_at }
    ElMessage.success(previousUser && previousUser !== currentUsername ? `已从 ${previousUser} 强制占用 ${row.ip}` : `已占用 ${row.ip}`)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '占用失败')
  }
}

async function handleRelease(row) {
  try {
    await ElMessageBox.confirm(`确定释放服务器 "${row.ip}" 吗？`, '确认释放', { type: 'warning' })
    const updated = await serverApi.release(row.id)
    const idx = servers.value.findIndex(s => s.id === row.id)
    if (idx !== -1) servers.value[idx] = { ...servers.value[idx], occupied_by: updated.occupied_by, occupied_at: updated.occupied_at }
    ElMessage.success('已释放')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '释放失败')
  }
}

function formatOccupyTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function toggleFavorite(row) {
  const nextValue = !row.is_favorite
  const previousValue = row.is_favorite
  row.is_favorite = nextValue
  try {
    const updated = nextValue
      ? await serverApi.favorite(row.id)
      : await serverApi.unfavorite(row.id)
    const idx = servers.value.findIndex(s => s.id === row.id)
    if (idx !== -1) {
      servers.value[idx] = { ...servers.value[idx], is_favorite: updated.is_favorite }
    }
  } catch (e) {
    row.is_favorite = previousValue
    ElMessage.error(e.response?.data?.detail || '收藏状态更新失败')
  }
}

async function openAssocDialog(row) {
  assocTargetServer.value = row
  selectedSwitchIds.value = []
  showAssocDialog.value = true
  try {
    const [assocData, allSwitchData] = await Promise.all([
      serverSwitchAssoc.get(row.id),
      switchApi.list(),
    ])
    selectedSwitchIds.value = (assocData.switches || []).map(s => s.id)
    allSwitches.value = allSwitchData.switches || []
  } catch (e) {
    ElMessage.error('加载交换机列表失败')
  }
}

async function saveAssoc() {
  if (!assocTargetServer.value) return
  savingAssoc.value = true
  try {
    await serverSwitchAssoc.set(assocTargetServer.value.id, selectedSwitchIds.value)
    const idx = servers.value.findIndex(s => s.id === assocTargetServer.value.id)
    if (idx !== -1) {
      servers.value[idx] = { ...servers.value[idx], assoc_switch_count: selectedSwitchIds.value.length }
    }
    ElMessage.success('关联已保存')
    showAssocDialog.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存关联失败')
  } finally {
    savingAssoc.value = false
  }
}

onMounted(loadServers)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar .el-input { --el-input-bg-color: #fff; }

.server-card {
  background: var(--bg-card);
  border: 3px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  padding: 18px;
  box-shadow: var(--shadow-md);
}

.server-table {
  border-radius: 18px;
  --el-table-bg-color: transparent;
}

.favorite-button {
  border: 2px solid var(--border);
  background: #fffaf6;
  color: #c9a391;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  transition: var(--transition);
}
.favorite-button.active,
.favorite-button:hover {
  color: #f6a623;
  background: #fff3d5;
  transform: rotate(-8deg) scale(1.04);
}

.tags-cell {
  cursor: pointer;
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: 999px;
  transition: var(--transition);
  font-weight: 700;
}
.tags-cell:hover {
  background: var(--cream-strong);
  color: var(--orange-dark);
}

.desc-cell {
  display: block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-desc-editor { width: 160px; }

.occupy-cell {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.occupy-info {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
  line-height: 1.15;
}
.occupied-by { color: var(--warning); font-weight: 800; }
.occupied-at {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
}
</style>
