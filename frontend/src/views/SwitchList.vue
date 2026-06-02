<template>
  <div class="switch-card fade-in">
    <!-- Toolbar -->
    <div class="toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索名称 / IP / 标签 / 备注…"
        style="width: 260px"
        clearable
        :prefix-icon="Search"
        autocomplete="off"
      />
      <el-button type="primary" @click="openAdd">
        <el-icon><Plus /></el-icon> 添加交换机
      </el-button>
    </div>

    <!-- Switch Table -->
    <el-table :data="filteredSwitches" stripe border v-loading="loading" style="width: 100%; table-layout: fixed; overflow-x: auto">
      <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP 地址" min-width="160" />
      <el-table-column prop="board_type" label="交换机型号" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.board_type || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="连接方式" min-width="100" align="center">
        <template #default>
          <el-tag size="small" type="success">SSH</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip />
      <el-table-column prop="password" label="密码" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.password || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="port" label="端口" min-width="80" align="center" />
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
      <el-table-column prop="description" label="备注" min-width="120">
        <template #default="{ row }">
          <template v-if="editingDescId === row.id">
            <el-input
              v-model="editingDescValue"
              size="small"
              style="width: 100px"
              @keyup.enter="saveDesc(row.id)"
              @blur="saveDesc(row.id)"
              placeholder="备注" autocomplete="off"
            />
          </template>
          <template v-else>
            <span class="tags-cell" @mousedown.prevent="startEditDesc(row)" title="点击编辑备注">{{ row.description || '—' }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="关联服务器" min-width="120" align="center">
        <template #default="{ row }">
          <el-link type="primary" @click="openAssocDialog(row)">{{ row.assoc_server_count ?? '—' }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="200" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openDetail(row)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add/Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingSwitch ? '编辑交换机' : '添加交换机'" width="520px">
      <el-form :model="form" label-width="100" ref="formRef">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="e.g. Switch-A-01" />
        </el-form-item>
        <el-form-item label="IP 地址" required>
          <el-input v-model="form.ip" placeholder="e.g. 192.168.1.1" />
        </el-form-item>
        <el-form-item label="端口" required>
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="e.g. admin" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" show-password placeholder="密码（留空则不修改）" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAdd" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- Detail Drawer -->
    <SwitchDetail :switchId="activeSwitchId" @close="activeSwitchId = null" @switch-updated="load" @open-edit="openEditById" />

    <!-- Assoc Dialog -->
    <el-dialog v-model="showAssocDialog" :title="`关联服务器 — ${assocTargetSwitch?.name}`" width="480px">
      <el-select v-model="selectedServerIds" multiple placeholder="选择关联的服务器" style="width: 100%">
        <el-option v-for="s in allServers" :key="s.id" :label="s.ip" :value="s.id" />
      </el-select>
      <template #footer>
        <el-button @click="showAssocDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAssoc" :loading="savingAssoc">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { switches } from '../api/index.js'
import { servers } from '../api/index.js'
import SwitchDetail from '../components/SwitchDetail.vue'

const emit = defineEmits(['stats'])

// ── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const switches_data = ref([])
const searchQuery = ref('')
const showAddDialog = ref(false)
const showAssocDialog = ref(false)
const editingSwitch = ref(null)
const saving = ref(false)
const savingAssoc = ref(false)
const assocTargetSwitch = ref(null)
const selectedServerIds = ref([])
const allServers = ref([])
const activeSwitchId = ref(null)

const form = ref({ name: '', ip: '', port: 22, username: '', password: '', tags: '', description: '' })

// ── Tags ─────────────────────────────────────────────────────────────────────
const editingTagsId = ref(null)
const editingTagsValue = ref('')
const tagsInputRef = ref(null)

function startEditTags(row) {
  editingTagsId.value = row.id
  editingTagsValue.value = row.tags || ''
  nextTick(() => tagsInputRef.value?.focus())
}

async function saveTags(id) {
  if (editingTagsId.value !== id) return
  const idx = switches_data.value.findIndex(s => s.id === id)
  if (idx === -1) return
  try {
    await switches.update(id, { tags: editingTagsValue.value })
    switches_data.value[idx] = { ...switches_data.value[idx], tags: editingTagsValue.value }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存标签失败')
  } finally {
    editingTagsId.value = null
  }
}

// ── Desc ─────────────────────────────────────────────────────────────────────
const editingDescId = ref(null)
const editingDescValue = ref('')
const descInputRef = ref(null)

function startEditDesc(row) {
  editingDescId.value = row.id
  editingDescValue.value = row.description || ''
  nextTick(() => descInputRef.value?.focus())
}

async function saveDesc(id) {
  if (editingDescId.value !== id) return
  const idx = switches_data.value.findIndex(s => s.id === id)
  if (idx === -1) return
  try {
    await switches.update(id, { description: editingDescValue.value })
    switches_data.value[idx] = { ...switches_data.value[idx], description: editingDescValue.value }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存备注失败')
  } finally {
    editingDescId.value = null
  }
}

// ── CRUD ─────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const data = await switches.list()
    switches_data.value = data.switches
    emit('stats', {
      total: data.switches.length,
      online: data.switches.filter(s => s.is_online).length,
      offline: data.switches.filter(s => !s.is_online).length,
    })
  } catch (e) {
    ElMessage.error('加载交换机列表失败')
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editingSwitch.value = null
  form.value = { name: '', ip: '', port: 22, username: '', password: '', tags: '', description: '' }
  showAddDialog.value = true
}

async function saveAdd() {
  if (!form.value.name || !form.value.ip || !form.value.username) {
    ElMessage.warning('名称、IP、用户名不能为空')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.password) delete payload.password
    if (editingSwitch.value) {
      const updated = await switches.update(editingSwitch.value.id, payload)
      const idx = switches_data.value.findIndex(s => s.id === editingSwitch.value.id)
      if (idx !== -1) switches_data.value[idx] = updated
      ElMessage.success('交换机已更新')
    } else {
      const created = await switches.create(payload)
      switches_data.value.push(created)
      ElMessage.success('交换机已添加')
    }
    showAddDialog.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除交换机 "${row.name}" 吗？`, '确认删除', { type: 'warning' })
    await switches.delete(row.id)
    switches_data.value = switches_data.value.filter(s => s.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

function openDetail(row) {
  activeSwitchId.value = row.id
}


function openEditById(id) {
  const row = switches_data.value.find(s => s.id === id)
  if (!row) return
  editingSwitch.value = row
  form.value = {
    name: row.name,
    ip: row.ip,
    port: row.port,
    username: row.username,
    password: '',
    tags: row.tags || '',
    description: row.description || '',
  }
  showAddDialog.value = true
}

// ── Assoc ─────────────────────────────────────────────────────────────────────
async function openAssocDialog(row) {
  assocTargetSwitch.value = row
  selectedServerIds.value = []
  showAssocDialog.value = true
  try {
    const data = await switches.getServers(row.id)
    selectedServerIds.value = (data || []).map(s => s.id)
    const all = await servers.list()
    allServers.value = all.servers
  } catch (e) {
    ElMessage.error('加载关联信息失败')
  }
}

async function saveAssoc() {
  if (!assocTargetSwitch.value) return
  savingAssoc.value = true
  try {
    await switches.setServers(assocTargetSwitch.value.id, selectedServerIds.value)
    // 更新列表中显示的关联数量
    const idx = switches_data.value.findIndex(s => s.id === assocTargetSwitch.value.id)
    if (idx !== -1) {
      switches_data.value[idx] = { ...switches_data.value[idx], assoc_server_count: selectedServerIds.value.length }
    }
    ElMessage.success('关联已保存')
    showAssocDialog.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存关联失败')
  } finally {
    savingAssoc.value = false
  }
}

// ── Filter ────────────────────────────────────────────────────────────────────
const filteredSwitches = computed(() => {
  if (!searchQuery.value) return switches_data.value
  const q = searchQuery.value.toLowerCase()
  return switches_data.value.filter(s =>
    (s.name || '').toLowerCase().includes(q) ||
    (s.ip || '').toLowerCase().includes(q) ||
    (s.tags || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.switch-card {
  background: var(--bg-card);
  border: 3px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: var(--shadow-md);
}

.tags-cell {
  cursor: pointer;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: 999px;
  font-weight: 700;
  transition: var(--transition);
}
.tags-cell:hover {
  color: var(--orange-dark);
  background: var(--cream-strong);
}
</style>
