<template>
  <el-drawer
    v-model="drawerVisible"
    :title="`${text.serverTitle} ${serverIp}`"
    size="50%"
    direction="rtl"
    class="server-detail-drawer"
  >
    <el-tabs v-model="activeTab" class="server-tabs">
      <el-tab-pane :label="text.detailTab" name="detail">
        <template v-if="detail">
          <el-alert
            v-if="detailError"
            :title="detailError"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />

          <el-descriptions :column="1" border size="small">
            <el-descriptions-item :label="text.ip">{{ detail.ip }}</el-descriptions-item>
            <el-descriptions-item :label="text.os">
              {{ detail.os_type }} / {{ detail.os_version || text.empty }}
            </el-descriptions-item>
            <el-descriptions-item :label="text.cpu">
              {{ detail.cpu ?? text.empty }} {{ text.cpuUnit }}{{ detail.cpu_model ? ` / ${detail.cpu_model}` : '' }}
            </el-descriptions-item>
            <el-descriptions-item :label="text.memory">
              {{ detail.mem ? `${detail.mem} MB` : text.empty }}
            </el-descriptions-item>
            <el-descriptions-item :label="text.tags">{{ detail.tags || text.empty }}</el-descriptions-item>
            <el-descriptions-item :label="text.description">{{ detail.description || text.empty }}</el-descriptions-item>
            <el-descriptions-item :label="text.cachedAt">{{ detail.cached_at || text.empty }}</el-descriptions-item>
          </el-descriptions>

          <el-divider>{{ text.interfaces }}</el-divider>
          <el-table
            v-if="detail.interfaces?.length"
            :data="detail.interfaces"
            size="small"
            max-height="200"
          >
            <el-table-column prop="name" :label="text.interfaceName" width="90" />
            <el-table-column prop="ip" :label="text.ip" min-width="120" />
            <el-table-column prop="mac" label="MAC" width="140" />
            <el-table-column prop="pci_addr" :label="text.pciAddress" width="110" show-overflow-tooltip />
            <el-table-column prop="pci_desc" :label="text.pciDevice" min-width="180" show-overflow-tooltip />
            <el-table-column prop="speed" :label="text.speed" width="80" />
          </el-table>
          <el-empty v-else :description="text.noInterfaces" />

          <div class="detail-note-panel">
            <div class="detail-note-header">
              <span>{{ text.detailNote }}</span>
              <el-button size="small" type="primary" :loading="savingDetailNote" @click="saveDetailNote">
                {{ text.save }}
              </el-button>
            </div>
            <el-input
              v-model="detailNoteDraft"
              type="textarea"
              :autosize="{ minRows: 5, maxRows: 12 }"
              :placeholder="text.detailNotePlaceholder"
            />
          </div>

          <div class="detail-actions">
            <el-button type="primary" size="small" :loading="fetchingDetail" @click="fetchDetail">
              <el-icon><Refresh /></el-icon> {{ text.fetchDetail }}
            </el-button>
            <el-button size="small" @click="checkStatus">{{ text.checkStatus }}</el-button>
            <el-button size="small" @click="openEdit">{{ text.edit }}</el-button>
            <el-button size="small" type="danger" @click="deleteServer">{{ text.delete }}</el-button>
          </div>
        </template>

        <el-empty v-else-if="loadingDetail" :description="text.loading" />
        <el-empty v-else-if="initialLoading" :description="text.loading" />
      </el-tab-pane>

      <el-tab-pane :label="text.filesTab" name="files">
        <div class="file-panel">
          <div class="path-bar">
            <el-button size="small" text :title="text.rootTitle" @click="navigateRoot">
              <el-icon><House /></el-icon>
            </el-button>
            <el-button size="small" text :disabled="currentPath === '/'" :title="text.upTitle" @click="goUp">
              <el-icon><Top /></el-icon>
            </el-button>

            <template v-if="pathEditing">
              <el-input
                ref="pathInputRef"
                v-model="pathDraft"
                size="small"
                class="path-input"
                @keyup.enter="submitPathDraft"
                @blur="submitPathDraft"
              />
            </template>
            <template v-else>
              <div class="path-display" :title="currentPath" @click="startEditPath">
                <span class="breadcrumb-sep">/</span>
                <span
                  v-for="(seg, i) in pathSegments"
                  :key="i"
                  class="breadcrumb-seg"
                  :class="{ last: i === pathSegments.length - 1 }"
                  @click.stop="navigateToSeg(i)"
                >
                  {{ seg }}
                </span>
              </div>
            </template>
          </div>

          <div
            class="file-table-wrap"
            @dragover.prevent="onTableDragOver"
            @dragleave.prevent="onTableDragLeave"
            @drop.prevent="onTableDrop"
          >
            <el-table
              :data="entries"
              v-loading="loading || uploading"
              size="small"
              class="file-table"
              highlight-current-row
              @row-dblclick="onRowDblClick"
              @row-click="onRowClick"
            >
              <el-table-column width="40">
                <template #default="{ row }">
                  <el-icon :color="row.type === 'directory' ? '#409eff' : '#909399'" size="18">
                    <FolderOpened v-if="row.type === 'directory'" />
                    <Document v-else />
                  </el-icon>
                </template>
              </el-table-column>
              <el-table-column prop="name" :label="text.name" min-width="240">
                <template #default="{ row }">
                  <span :class="row.type === 'directory' ? 'dir-name' : 'file-name'">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="text.size" width="90" align="right">
                <template #default="{ row }">
                  <span v-if="row.type === 'file'" class="file-size">{{ formatSize(row.size) }}</span>
                  <span v-else>{{ text.empty }}</span>
                </template>
              </el-table-column>
            </el-table>

            <div v-if="dragOverActive" class="drop-overlay">
              {{ text.dropHint }}
            </div>
          </div>

          <div class="file-floating-bar">
            <div class="file-toolbar">
              <el-button size="small" @click="refresh">
                <el-icon><Refresh /></el-icon> {{ text.refresh }}
              </el-button>
              <el-button size="small" @click="createFolder">{{ text.createFolder }}</el-button>
              <el-button size="small" type="primary" @click="showUploadDialog">
                <el-icon><Upload /></el-icon> {{ text.uploadFile }}
              </el-button>
              <el-button size="small" :disabled="!selectedFile" @click="downloadSelected">
                <el-icon><Download /></el-icon> {{ text.download }}
              </el-button>
            </div>

            <div v-if="uploadProgress.visible" class="upload-progress">
              <div class="upload-progress-main">
                <span class="upload-progress-label">{{ uploadProgress.label }}</span>
                <span v-if="uploadProgress.currentName" class="upload-progress-file">
                  {{ text.currentFilePrefix }} {{ uploadProgress.currentName }}
                </span>
              </div>
              <div class="upload-progress-actions">
                <span class="upload-progress-count">
                  {{ text.uploadedCountPrefix }} {{ uploadProgress.completed }} {{ text.uploadedCountSep }} {{ uploadProgress.total }}
                </span>
                <el-button size="small" text type="danger" @click="cancelCurrentUpload">
                  {{ text.cancelUpload }}
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="text.logsTab" name="logs">
        <div class="log-toolbar">
          <el-button size="small" :loading="loadingLogs" @click="loadLogs">
            <el-icon><Refresh /></el-icon> {{ text.refresh }}
          </el-button>
          <el-button size="small" type="danger" @click="clearLogs">{{ text.clearLogs }}</el-button>
        </div>

        <div class="log-container" v-loading="loadingLogs">
          <div v-if="logs.length === 0" class="log-empty">{{ text.noLogs }}</div>
          <div v-else class="log-list">
            <div v-for="(log, i) in logs" :key="i" class="log-line" :class="logClass(log)">
              <span class="log-time">{{ log.time || text.empty }}</span>
              <span class="log-type">{{ logTypeLabel(log) }}</span>
              <span class="log-status" :class="log.online ? 'online' : 'offline'">
                {{ log.online === true ? text.online : log.online === false ? text.offline : text.empty }}
              </span>
              <span v-if="log.actor" class="log-info">{{ text.user }} {{ log.actor }}</span>
              <span v-if="logChangeSummary(log)" class="log-info">{{ logChangeSummary(log) }}</span>
              <span v-if="log.cpu" class="log-info">CPU {{ log.cpu }}{{ text.cpuUnit }}</span>
              <span v-if="log.mem" class="log-info">{{ text.memory }} {{ log.mem }}MB</span>
              <span v-if="log.os_version" class="log-info">{{ log.os_version }}</span>
              <div v-if="logInterfaces(log).length" class="log-interfaces">
                <div class="log-interfaces-title">{{ text.interfacesDetail }}</div>
                <div v-for="(item, idx) in logInterfaces(log)" :key="idx" class="log-interface-item">
                  <span class="iface-name">{{ item.name || 'unknown' }}</span>
                  <span v-if="item.ip">IP {{ item.ip }}</span>
                  <span v-if="item.mac">MAC {{ item.mac }}</span>
                  <span v-if="item.speed">{{ text.speed }} {{ item.speed }}</span>
                  <span v-if="item.pci_addr">PCI {{ item.pci_addr }}</span>
                  <span v-if="item.pci_desc">{{ item.pci_desc }}</span>
                </div>
              </div>
              <span v-if="log.error" class="log-error">{{ log.error }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="uploadDialogVisible" :title="text.uploadFile" width="440px">
      <el-form>
        <el-form-item :label="text.targetPath">
          <el-input v-model="uploadRemotePath" :placeholder="text.targetPathPlaceholder" />
        </el-form-item>
        <el-form-item :label="text.selectFile">
          <input type="file" style="width: 100%" @change="onFileSelected" />
        </el-form-item>
        <el-form-item v-if="uploadFileName" :label="text.fileName">
          <el-tag>{{ uploadFileName }}</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">{{ text.cancel }}</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">{{ text.upload }}</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Download, FolderOpened, House, Refresh, Top, Upload } from '@element-plus/icons-vue'
import { files as filesApi, logs as logsApi, servers as serverApi } from '../api/index.js'

const text = {
  serverTitle: '\u670d\u52a1\u5668',
  detailTab: '\u8be6\u60c5',
  filesTab: '\u6587\u4ef6\u7ba1\u7406',
  logsTab: '\u65e5\u5fd7',
  ip: 'IP',
  os: '\u7cfb\u7edf',
  cpu: 'CPU',
  cpuUnit: '\u6838',
  memory: '\u5185\u5b58',
  tags: '\u6807\u7b7e',
  description: '\u5907\u6ce8',
  cachedAt: '\u91c7\u96c6\u65f6\u95f4',
  interfaces: '\u7f51\u5361',
  interfaceName: '\u7f51\u5361',
  pciAddress: 'PCI \u5730\u5740',
  pciDevice: 'PCI \u8bbe\u5907',
  speed: '\u901f\u7387',
  noInterfaces: '\u6682\u65e0\u7f51\u5361\u4fe1\u606f',
  detailNote: '\u8be6\u60c5\u8bb0\u5f55',
  detailNotePlaceholder: '\u53ef\u4ee5\u5728\u8fd9\u91cc\u8bb0\u5f55\u7ef4\u62a4\u4fe1\u606f\u3001\u6392\u969c\u8fc7\u7a0b\u3001\u8d44\u4ea7\u8bf4\u660e\u7b49',
  save: '\u4fdd\u5b58',
  fetchDetail: '\u91cd\u65b0\u91c7\u96c6',
  checkStatus: '\u68c0\u6d4b\u72b6\u6001',
  edit: '\u7f16\u8f91',
  delete: '\u5220\u9664',
  loading: '\u52a0\u8f7d\u4e2d...',
  rootTitle: '\u56de\u5230\u6839\u76ee\u5f55',
  upTitle: '\u4e0a\u4e00\u7ea7',
  name: '\u540d\u79f0',
  size: '\u5927\u5c0f',
  refresh: '\u5237\u65b0',
  createFolder: '\u65b0\u5efa\u76ee\u5f55',
  uploadFile: '\u4e0a\u4f20\u6587\u4ef6',
  download: '\u4e0b\u8f7d',
  dropHint: '\u62d6\u62fd\u6587\u4ef6\u6216\u76ee\u5f55\u5230\u8fd9\u91cc\u4e0a\u4f20\u5230\u5f53\u524d\u76ee\u5f55',
  clearLogs: '\u6e05\u7a7a\u65e5\u5fd7',
  noLogs: '\u6682\u65e0\u65e5\u5fd7\u8bb0\u5f55',
  online: '\u5728\u7ebf',
  offline: '\u79bb\u7ebf',
  user: '\u7528\u6237',
  interfacesDetail: '\u7f51\u5361\u8be6\u60c5',
  targetPath: '\u76ee\u6807\u8def\u5f84',
  targetPathPlaceholder: '\u4f8b\u5982 /home/user/',
  selectFile: '\u9009\u62e9\u6587\u4ef6',
  fileName: '\u6587\u4ef6\u540d',
  cancel: '\u53d6\u6d88',
  upload: '\u4e0a\u4f20',
  empty: '-',
  loadFailed: '\u52a0\u8f7d\u5931\u8d25',
  fetchFailed: '\u8be6\u60c5\u91c7\u96c6\u5931\u8d25',
  fetchSuccess: '\u91c7\u96c6\u6210\u529f',
  statusFailed: '\u68c0\u6d4b\u5931\u8d25',
  detailNoteSaved: '\u8be6\u60c5\u8bb0\u5f55\u5df2\u4fdd\u5b58',
  detailNoteSaveFailed: '\u4fdd\u5b58\u8be6\u60c5\u8bb0\u5f55\u5931\u8d25',
  deleteConfirm: '\u5220\u9664\u8be5\u670d\u52a1\u5668\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u6062\u590d\u3002',
  deleteConfirmTitle: '\u786e\u8ba4\u5220\u9664',
  deleted: '\u5df2\u5220\u9664',
  readDirFailed: '\u8bfb\u53d6\u76ee\u5f55\u5931\u8d25',
  chooseFileFirst: '\u8bf7\u5148\u9009\u62e9\u6587\u4ef6',
  uploadSuccess: '\u4e0a\u4f20\u6210\u529f',
  uploadFailed: '\u4e0a\u4f20\u5931\u8d25',
  readFileTimeout: '\u6587\u4ef6\u8bfb\u53d6\u8d85\u65f6',
  readFileFailed: '\u6587\u4ef6\u8bfb\u53d6\u5931\u8d25',
  createFolderPrompt: '\u8bf7\u8f93\u5165\u65b0\u76ee\u5f55\u540d\u79f0\u6216\u5b8c\u6574\u8def\u5f84',
  createFolderTitle: '\u65b0\u5efa\u76ee\u5f55',
  create: '\u521b\u5efa',
  folderCreated: '\u76ee\u5f55\u521b\u5efa\u6210\u529f',
  folderCreateFailed: '\u76ee\u5f55\u521b\u5efa\u5931\u8d25',
  clearLogsConfirm: '\u786e\u5b9a\u6e05\u7a7a\u8be5\u670d\u52a1\u5668\u7684\u6240\u6709\u65e5\u5fd7\uff1f',
  clearConfirmTitle: '\u786e\u8ba4',
  logsCleared: '\u5df2\u6e05\u7a7a',
  loadLogsFailed: '\u52a0\u8f7d\u65e5\u5fd7\u5931\u8d25',
  logStatus: '\u72b6\u6001',
  logDetail: '\u8be6\u60c5',
  logCreate: '\u521b\u5efa',
  logDelete: '\u5220\u9664',
  logOccupy: '\u5360\u7528',
  logRelease: '\u91ca\u653e',
  logUpdate: '\u4fee\u6539',
  logDefault: '\u65e5\u5fd7',
  port: '\u7aef\u53e3',
  sshUsername: 'SSH\u8d26\u53f7',
  sshPassword: 'SSH\u5bc6\u7801',
  sshKeyFile: 'SSH\u5bc6\u94a5',
  bmcUsername: 'BMC\u8d26\u53f7',
  bmcPassword: 'BMC\u5bc6\u7801',
  occupiedBy: '\u5360\u7528\u4eba',
  changedFieldsPrefix: '\u4fee\u6539',
  dirUploadScanning: '\u6b63\u5728\u89e3\u6790\u76ee\u5f55...',
  dirUploadUploading: '\u6b63\u5728\u4e0a\u4f20\u76ee\u5f55...',
  dirUploadSuccess: '\u76ee\u5f55\u4e0a\u4f20\u6210\u529f',
  dropNothing: '\u672a\u8bc6\u522b\u5230\u53ef\u4e0a\u4f20\u7684\u6587\u4ef6\u6216\u76ee\u5f55',
  fileUploadPreparing: '\u6b63\u5728\u4e0a\u4f20\u6587\u4ef6...',
  uploadProgressSingle: '\u6587\u4ef6\u4e0a\u4f20\u8fdb\u5ea6',
  uploadProgressDirectory: '\u76ee\u5f55\u4e0a\u4f20\u8fdb\u5ea6',
  uploadedCountPrefix: '\u5df2\u4e0a\u4f20',
  uploadedCountSep: '\u4e2a / \u603b\u5171',
  currentFilePrefix: '\u5f53\u524d\u6587\u4ef6:',
  cancelUpload: '\u53d6\u6d88\u4e0a\u4f20',
  uploadCanceled: '\u5df2\u53d6\u6d88\u4e0a\u4f20',
}

const props = defineProps({ serverId: { type: Number, default: null } })
const emit = defineEmits(['close', 'server-updated', 'open-edit'])

const drawerVisible = computed({
  get: () => !!props.serverId,
  set: () => emit('close'),
})

const activeTab = ref('detail')
const detail = ref(null)
const loadingDetail = ref(false)
const initialLoading = ref(true)
const fetchingDetail = ref(false)
const detailError = ref('')
const detailNoteDraft = ref('')
const savingDetailNote = ref(false)
const serverIp = ref('')

const entries = ref([])
const loading = ref(false)
const currentPath = ref('/')
const pathEditing = ref(false)
const pathDraft = ref('/')
const pathInputRef = ref(null)
const selectedFile = ref(null)
const uploadDialogVisible = ref(false)
const uploadRemotePath = ref('')
const uploadFile = ref(null)
const uploadFileName = ref('')
const uploading = ref(false)
const dragOverActive = ref(false)
const uploadProgress = ref({
  visible: false,
  label: '',
  completed: 0,
  total: 0,
  currentName: '',
})
const currentUploadController = ref(null)
const uploadCanceled = ref(false)

const logs = ref([])
const loadingLogs = ref(false)
const logOffset = ref(0)
const logTotal = ref(0)

const detailCache = new Map()

function getPathStorageKey(serverId) {
  const userId = localStorage.getItem('user_id') || 'anonymous'
  return `server-file-path:${userId}:${serverId}`
}

function getRememberedPath(serverId) {
  if (!serverId) return '/'
  return localStorage.getItem(getPathStorageKey(serverId)) || '/'
}

function rememberPath(serverId, path) {
  if (!serverId || !path) return
  localStorage.setItem(getPathStorageKey(serverId), path)
}

watch(
  () => props.serverId,
  async (id) => {
    if (!id) return
    entries.value = []
    currentPath.value = getRememberedPath(id)
    pathDraft.value = currentPath.value
    selectedFile.value = null
    activeTab.value = 'detail'
    detailError.value = ''

    const cached = detailCache.get(id)
    if (cached) {
      detail.value = cached.detail
      detailNoteDraft.value = cached.detail.detail_note || ''
      serverIp.value = cached.detail.ip
      initialLoading.value = false
    } else {
      detail.value = null
      initialLoading.value = true
    }

    try {
      const basic = await serverApi.get(id)
      detail.value = mergeServerDetail(detail.value, basic)
      detailNoteDraft.value = detail.value.detail_note || ''
      serverIp.value = detail.value.ip
    } catch {
      if (!cached) ElMessage.error(text.loadFailed)
      initialLoading.value = false
      return
    }

    try {
      const fetched = await serverApi.fetchDetail(id)
      detail.value = mergeServerDetail(detail.value, fetched)
      detailNoteDraft.value = detail.value.detail_note || ''
      serverIp.value = detail.value.ip
      detailCache.set(id, { detail: detail.value, timestamp: Date.now() })
    } catch (e) {
      detailError.value = e.response?.data?.detail || text.fetchFailed
      if (!cached) ElMessage.warning(detailError.value)
    } finally {
      initialLoading.value = false
    }
  },
  { immediate: true },
)

function mergeServerDetail(current, incoming) {
  return {
    ...current,
    ...incoming,
    interfaces: incoming?.interfaces ?? current?.interfaces ?? [],
    cached_at: incoming?.cached_at ?? current?.cached_at ?? null,
  }
}

async function fetchDetail() {
  fetchingDetail.value = true
  detailError.value = ''
  try {
    const fetched = await serverApi.fetchDetail(props.serverId, true)
    detail.value = mergeServerDetail(detail.value, fetched)
    detailNoteDraft.value = detail.value.detail_note || ''
    detailCache.set(props.serverId, { detail: detail.value, timestamp: Date.now() })
    ElMessage.success(text.fetchSuccess)
    if (activeTab.value === 'logs') await loadLogs()
  } catch (e) {
    detailError.value = e.response?.data?.detail || text.fetchFailed
    ElMessage.error(detailError.value)
  } finally {
    fetchingDetail.value = false
  }
}

async function checkStatus() {
  try {
    const result = await serverApi.checkStatus(props.serverId)
    if (!detail.value) {
      detail.value = mergeServerDetail(detail.value, await serverApi.get(props.serverId))
    }
    detail.value.is_online = result.online
    detailCache.set(props.serverId, { detail: detail.value, timestamp: Date.now() })
    emit('server-updated')
    ElMessage.success(`${detail.value.ip}: ${result.online ? text.online : text.offline}`)
    if (activeTab.value === 'logs') await loadLogs()
  } catch {
    ElMessage.error(text.statusFailed)
  }
}

async function saveDetailNote() {
  if (!props.serverId || !detail.value) return
  savingDetailNote.value = true
  try {
    const updated = await serverApi.update(props.serverId, { detail_note: detailNoteDraft.value })
    detail.value = { ...detail.value, detail_note: updated.detail_note }
    detailCache.set(props.serverId, { detail: detail.value, timestamp: Date.now() })
    ElMessage.success(text.detailNoteSaved)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || text.detailNoteSaveFailed)
  } finally {
    savingDetailNote.value = false
  }
}

function openEdit() {
  emit('close')
  emit('open-edit', props.serverId)
}

async function deleteServer() {
  try {
    await ElMessageBox.confirm(text.deleteConfirm, text.deleteConfirmTitle, {
      type: 'warning',
      confirmButtonText: text.delete,
      cancelButtonText: text.cancel,
    })
    await serverApi.delete(props.serverId)
    ElMessage.success(text.deleted)
    emit('close')
    emit('server-updated')
  } catch {}
}

async function loadDir(path) {
  if (!props.serverId) return
  loading.value = true
  entries.value = []
  try {
    const data = await filesApi.list(props.serverId, path)
    entries.value = data.entries
    currentPath.value = data.path
    pathDraft.value = data.path
    rememberPath(props.serverId, data.path)
    selectedFile.value = null
  } catch (e) {
    ElMessage.error(`${text.readDirFailed}: ${e.response?.data?.detail || e.message}`)
  } finally {
    loading.value = false
  }
}

const pathSegments = computed(() => {
  if (!currentPath.value || currentPath.value === '/') return []
  return currentPath.value.split('/').filter(Boolean)
})

async function refresh() {
  await loadDir(currentPath.value)
}

function navigateRoot() {
  loadDir('/')
}

function goUp() {
  if (currentPath.value === '/') return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  loadDir(parts.length ? `/${parts.join('/')}` : '/')
}

function navigateToSeg(idx) {
  if (currentPath.value === '/') return
  const parts = currentPath.value.split('/').filter(Boolean)
  loadDir(`/${parts.slice(0, idx + 1).join('/')}`)
}

function startEditPath() {
  pathDraft.value = currentPath.value || '/'
  pathEditing.value = true
  queueMicrotask(() => pathInputRef.value?.focus?.())
}

function submitPathDraft() {
  const target = (pathDraft.value || '/').trim() || '/'
  pathEditing.value = false
  loadDir(target)
}

function onRowClick(row) {
  if (row.type === 'directory') {
    loadDir(row.path)
    return
  }
  selectedFile.value = row.type === 'file' ? row : null
}

function onRowDblClick(row) {
  if (row.type === 'directory') return
  downloadFile(row.path)
}

async function downloadFile(path) {
  try {
    const blob = await filesApi.download(props.serverId, path)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = path.split('/').pop()
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    ElMessage.error(`${text.download}: ${e.response?.data?.detail || e.message}`)
  }
}

function downloadSelected() {
  if (selectedFile.value) downloadFile(selectedFile.value.path)
}

watch(activeTab, (tab) => {
  if (tab === 'files' && entries.value.length === 0) loadDir(currentPath.value || '/')
  if (tab === 'logs') {
    logOffset.value = 0
    logs.value = []
    loadLogs()
  }
})

function showUploadDialog() {
  uploadRemotePath.value = currentPath.value === '/' ? '/' : `${currentPath.value}/`
  uploadFile.value = null
  uploadFileName.value = ''
  uploadDialogVisible.value = true
}

function onFileSelected(event) {
  const file = event.target.files[0]
  if (!file) return
  prepareUploadFile(file)
}

function prepareUploadFile(file, remotePath = null) {
  uploadFileName.value = file.name
  uploadFile.value = file
  const baseName = file.name.replace(/\\/g, '/').split('/').pop()
  uploadRemotePath.value = remotePath || `${currentPath.value === '/' ? '' : currentPath.value}/${baseName}`
}

function beginUploadProgress(label, total) {
  currentUploadController.value = new AbortController()
  uploadCanceled.value = false
  uploadProgress.value = {
    visible: true,
    label,
    completed: 0,
    total,
    currentName: '',
  }
}

function updateUploadProgress(completed, currentName = uploadProgress.value.currentName) {
  uploadProgress.value = {
    ...uploadProgress.value,
    completed,
    currentName,
  }
}

function finishUploadProgress() {
  currentUploadController.value = null
  uploadCanceled.value = false
  uploadProgress.value = {
    visible: false,
    label: '',
    completed: 0,
    total: 0,
    currentName: '',
  }
}

function cancelCurrentUpload() {
  uploadCanceled.value = true
  currentUploadController.value?.abort()
}

function getUploadRequestConfig() {
  return currentUploadController.value ? { signal: currentUploadController.value.signal } : {}
}

function isCanceledError(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError' || uploadCanceled.value
}

function ensureUploadNotCanceled() {
  if (uploadCanceled.value) {
    throw new Error(text.uploadCanceled)
  }
}

async function doUpload() {
  if (!uploadFile.value) {
    ElMessage.warning(text.chooseFileFirst)
    return
  }
  uploading.value = true
  beginUploadProgress(text.uploadProgressSingle, 1)
  updateUploadProgress(0, uploadFileName.value || uploadRemotePath.value.split('/').pop() || '')
  ElMessage.info(text.fileUploadPreparing)
  try {
    await filesApi.upload(props.serverId, uploadRemotePath.value, uploadFile.value, getUploadRequestConfig())
    updateUploadProgress(1, uploadFileName.value || uploadRemotePath.value.split('/').pop() || '')
    uploadDialogVisible.value = false
    await refresh()
    ElMessage.success(text.uploadSuccess)
  } catch (e) {
    if (isCanceledError(e)) {
      ElMessage.info(text.uploadCanceled)
    } else {
      ElMessage.error(`${text.uploadFailed}: ${e.response?.data?.detail || e.message}`)
    }
  } finally {
    uploading.value = false
    window.setTimeout(finishUploadProgress, 800)
  }
}

function joinRemotePath(base, name) {
  const cleanBase = base === '/' ? '' : (base || '').replace(/\/+$/, '')
  const cleanName = (name || '').replace(/^\/+/, '')
  return `${cleanBase}/${cleanName}` || '/'
}

function getEntryFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject))
}

function readDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const allEntries = []
    const readBatch = () => {
      reader.readEntries((entries) => {
        if (!entries.length) {
          resolve(allEntries)
          return
        }
        allEntries.push(...entries)
        readBatch()
      }, reject)
    }
    readBatch()
  })
}

async function flattenDroppedEntry(entry, parentPath = '') {
  if (entry.isFile) {
    const file = await getEntryFile(entry)
    return [{
      kind: 'file',
      relativePath: parentPath ? `${parentPath}/${file.name}` : file.name,
      file,
    }]
  }

  if (!entry.isDirectory) return []

  const dirPath = parentPath ? `${parentPath}/${entry.name}` : entry.name
  const flattened = [{ kind: 'dir', relativePath: dirPath }]
  const reader = entry.createReader()
  const children = await readDirectoryEntries(reader)
  for (const child of children) {
    flattened.push(...await flattenDroppedEntry(child, dirPath))
  }
  return flattened
}

async function uploadDroppedFile(file) {
  const remotePath = `${currentPath.value === '/' ? '' : currentPath.value}/${file.name}`
  uploading.value = true
  beginUploadProgress(text.uploadProgressSingle, 1)
  updateUploadProgress(0, file.name)
  ElMessage.info(text.fileUploadPreparing)
  try {
    ensureUploadNotCanceled()
    await filesApi.upload(props.serverId, remotePath, file, getUploadRequestConfig())
    updateUploadProgress(1, file.name)
    await refresh()
    ElMessage.success(text.uploadSuccess)
  } catch (e) {
    if (isCanceledError(e)) {
      ElMessage.info(text.uploadCanceled)
    } else {
      ElMessage.error(`${text.uploadFailed}: ${e.response?.data?.detail || e.message}`)
    }
  } finally {
    uploading.value = false
    window.setTimeout(finishUploadProgress, 800)
  }
}

async function uploadDroppedDirectory(items) {
  ElMessage.info(text.dirUploadScanning)
  const flattened = []
  for (const item of items) {
    const entry = item.webkitGetAsEntry?.()
    if (entry) flattened.push(...await flattenDroppedEntry(entry))
  }

  if (!flattened.length) {
    ElMessage.warning(text.dropNothing)
    return
  }

  uploading.value = true
  beginUploadProgress(text.uploadProgressDirectory, flattened.filter((item) => item.kind === 'file').length)
  ElMessage.info(text.dirUploadUploading)
  try {
    const dirs = flattened.filter((item) => item.kind === 'dir').sort((a, b) => a.relativePath.length - b.relativePath.length)
    const files = flattened.filter((item) => item.kind === 'file')
    let completed = 0

    for (const dir of dirs) {
      ensureUploadNotCanceled()
      await filesApi.mkdir(props.serverId, joinRemotePath(currentPath.value, dir.relativePath), getUploadRequestConfig())
    }
    for (const item of files) {
      ensureUploadNotCanceled()
      updateUploadProgress(completed, item.relativePath)
      ensureUploadNotCanceled()
      await filesApi.upload(
        props.serverId,
        joinRemotePath(currentPath.value, item.relativePath),
        item.file,
        getUploadRequestConfig(),
      )
      completed += 1
      updateUploadProgress(completed, item.relativePath)
    }

    await refresh()
    ElMessage.success(`${text.dirUploadSuccess} (${files.length})`)
  } catch (e) {
    if (isCanceledError(e)) {
      ElMessage.info(text.uploadCanceled)
    } else {
      ElMessage.error(e.response?.data?.detail || e.message || text.uploadFailed)
    }
  } finally {
    uploading.value = false
    window.setTimeout(finishUploadProgress, 800)
  }
}

function onTableDragOver() {
  dragOverActive.value = true
}

function onTableDragLeave() {
  dragOverActive.value = false
}

async function onTableDrop(event) {
  dragOverActive.value = false
  const items = Array.from(event.dataTransfer?.items || [])
  const hasDirectory = items.some((item) => item.webkitGetAsEntry?.()?.isDirectory)
  if (hasDirectory) {
    await uploadDroppedDirectory(items)
    return
  }

  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  await uploadDroppedFile(file)
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt(text.createFolderPrompt, text.createFolderTitle, {
      confirmButtonText: text.create,
      cancelButtonText: text.cancel,
      inputValue: currentPath.value === '/' ? '/' : `${currentPath.value}/`,
    })
    const target = (value || '').trim()
    if (!target) return
    await filesApi.mkdir(props.serverId, target)
    await refresh()
    ElMessage.success(text.folderCreated)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || e.message || text.folderCreateFailed)
    }
  }
}

function formatSize(bytes) {
  if (bytes == null) return text.empty
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function loadLogs() {
  if (!props.serverId) return
  loadingLogs.value = true
  logOffset.value = 0
  logs.value = []
  try {
    const data = await logsApi.list(props.serverId, 200, 0)
    logs.value = data.logs
    logTotal.value = data.total
  } catch {
    ElMessage.error(text.loadLogsFailed)
  } finally {
    loadingLogs.value = false
  }
}

async function clearLogs() {
  try {
    await ElMessageBox.confirm(text.clearLogsConfirm, text.clearConfirmTitle, { type: 'warning' })
    await logsApi.clear(props.serverId)
    logs.value = []
    logTotal.value = 0
    ElMessage.success(text.logsCleared)
  } catch {}
}

function logClass(log) {
  if (log.error) return 'log-error-row'
  if (log.online === false) return 'log-offline-row'
  return ''
}

function logTypeLabel(log) {
  if (log.type === 'status_check') return text.logStatus
  if (log.type === 'detail_fetch') return text.logDetail
  if (log.type === 'server_create') return text.logCreate
  if (log.type === 'server_delete') return text.logDelete
  if (log.action === 'occupy') return text.logOccupy
  if (log.action === 'release') return text.logRelease
  if (log.type === 'server_update') return text.logUpdate
  return log.type || text.logDefault
}

const logFieldLabels = {
  ip: text.ip,
  port: text.port,
  os_type: text.os,
  ssh_username: text.sshUsername,
  ssh_password: text.sshPassword,
  ssh_key_file: text.sshKeyFile,
  description: text.description,
  detail_note: text.detailNote,
  tags: text.tags,
  bmc_ip: 'BMC IP',
  bmc_username: text.bmcUsername,
  bmc_password: text.bmcPassword,
  occupied_by: text.occupiedBy,
}

function logChangeSummary(log) {
  if (!log.changes) return ''
  const fields = Object.keys(log.changes)
  if (!fields.length) return ''
  return `${text.changedFieldsPrefix} ${fields.map((field) => logFieldLabels[field] || field).join('\u3001')}`
}

function logInterfaces(log) {
  return Array.isArray(log.interfaces) ? log.interfaces : []
}
</script>

<style scoped>
:global(.server-detail-drawer.el-drawer) {
  min-width: 720px;
}

@media (max-width: 900px) {
  :global(.server-detail-drawer.el-drawer) {
    width: 92% !important;
    min-width: 0;
  }
}

.path-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-bottom: 10px;
  padding: 6px 10px;
  background: var(--bg-hover);
  border-radius: 6px;
  font-size: 13px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.path-display {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  overflow: hidden;
  cursor: text;
}

.path-input {
  min-width: 180px;
  flex: 1;
}

.breadcrumb-sep {
  color: var(--text-muted);
  margin: 0 2px;
  user-select: none;
}

.breadcrumb-seg {
  color: var(--accent);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.breadcrumb-seg:hover {
  background: var(--cream-strong);
  text-decoration: underline;
}

.breadcrumb-seg.last {
  color: var(--text-primary);
  cursor: default;
  font-weight: 500;
}

.breadcrumb-seg.last:hover {
  background: none;
  text-decoration: none;
}

.file-table {
  cursor: pointer;
}

.file-panel {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  height: calc(100vh - 220px);
}

.file-table-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-bottom: 12px;
}

.file-floating-bar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 12px;
  padding-bottom: max(10px, env(safe-area-inset-bottom));
  border: 2px solid var(--border);
  border-radius: 18px;
  background: var(--bg-card);
  backdrop-filter: blur(10px);
  box-shadow: var(--shadow-md);
}

.dir-name {
  color: var(--orange-dark);
  font-weight: 800;
}

.file-name {
  color: var(--text-primary);
}

.file-table {
  height: 100%;
}

.file-size {
  color: var(--text-muted);
  font-size: 12px;
}

.file-toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-progress {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 18px;
  background: var(--cream-strong);
  color: var(--text-primary);
  font-size: 13px;
}

.upload-progress-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.upload-progress-label {
  font-weight: 800;
}

.upload-progress-file {
  color: var(--text-muted);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 520px;
}

.upload-progress-count {
  color: var(--orange-dark);
  font-variant-numeric: tabular-nums;
  margin-left: 12px;
  white-space: nowrap;
}

.upload-progress-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
}

.drop-overlay {
  margin-top: 10px;
  padding: 18px 16px;
  border: 2px dashed var(--accent);
  border-radius: 18px;
  background: var(--cream-strong);
  color: var(--orange-dark);
  text-align: center;
  font-size: 13px;
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.detail-note-panel {
  margin-top: 16px;
  padding: 12px;
  border: 2px solid var(--border);
  border-radius: 18px;
  background: #fffaf6;
}

.detail-note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--text-primary);
  font-weight: 800;
}

.log-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.log-container {
  border: 2px solid var(--border);
  border-radius: 18px;
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
}

.log-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
}

.log-list {
  font-family: 'Consolas', monospace;
  font-size: 12px;
}

.log-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
}

.log-line:last-child {
  border-bottom: none;
}

.log-offline-row {
  background: rgba(248, 81, 73, 0.08);
}

.log-error-row {
  background: rgba(248, 81, 73, 0.05);
}

.log-time {
  color: var(--text-muted);
  white-space: nowrap;
}

.log-type {
  color: var(--accent);
  font-weight: 500;
}

.log-status {
  font-size: 12px;
}

.log-status.online {
  color: var(--online);
}

.log-status.offline {
  color: var(--offline);
}

.log-info {
  color: var(--text-secondary);
}

.log-error {
  color: var(--offline);
}

.log-interfaces {
  width: 100%;
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--bg-hover);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  line-height: 1.7;
}

.log-interfaces-title {
  margin-bottom: 4px;
  color: var(--text-primary);
  font-weight: 600;
}

.log-interface-item {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
}

.iface-name {
  min-width: 90px;
  color: var(--accent);
  font-weight: 600;
}
</style>
