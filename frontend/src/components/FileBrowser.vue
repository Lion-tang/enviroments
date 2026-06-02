<template>
  <el-drawer v-model="visible" title="📁 文件管理器" size="520px" direction="rtl">
    <!-- Current Path -->
    <div class="path-bar">
      <span class="path-label">路径：</span>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item v-for="(seg, i) in pathSegments" :key="i">
          <a @click.prevent="navigateToSeg(i)">{{ seg || '根' }}</a>
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <!-- Actions -->
    <div class="toolbar">
      <el-button size="small" @click="refresh" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
      <el-button size="small" :disabled="currentPath !== '/'" @click="goUp">
        <el-icon><ArrowUp /></el-icon> 上一级
      </el-button>
      <el-button size="small" type="primary" @click="showUploadDialog">
        <el-icon><Upload /></el-icon> 上传
      </el-button>
    </div>

    <!-- File/Folder List -->
    <el-table
      :data="entries"
      v-loading="loading"
      size="small"
      class="file-table"
      @row-dblclick="rowDblClick"
    >
      <el-table-column width="40">
        <template #default="{ row }">
          <el-icon v-if="row.type === 'directory'" color="#409eff" size="18">
            <Folder />
          </el-icon>
          <el-icon v-else color="#909399" size="18">
            <Document />
          </el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">
          <span v-if="row.type === 'file'">{{ formatSize(row.size) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <template v-if="row.type === 'directory'">
            <el-button size="small" @click="navigateInto(row.path)">进入</el-button>
          </template>
          <template v-else>
            <el-button size="small" type="success" @click="downloadFile(row.path)">
              下载
            </el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- Upload Dialog -->
    <el-dialog v-model="uploadDialogVisible" title="上传文件" width="440px">
      <el-form>
        <el-form-item label="目标路径">
          <el-input v-model="uploadPath" placeholder="例: /home/user/file.txt" />
        </el-form-item>
        <el-form-item label="选择文件">
          <el-input type="file" @change="onFileSelected" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doUpload" :loading="uploading">上传</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Folder, Document, Refresh, ArrowUp, Upload } from '@element-plus/icons-vue'
import { files } from '../api/index.js'

const props = defineProps({ serverId: Number })
const emit = defineEmits(['open'])

const visible = computed({
  get: () => !!props.serverId,
  set: (v) => { if (!v) emit('open', null) },
})

const loading = ref(false)
const entries = ref([])
const currentPath = ref('/')
const uploadDialogVisible = ref(false)
const uploadPath = ref('')
const uploadFileData = ref(null)
const uploading = ref(false)

const pathSegments = computed(() => {
  if (currentPath.value === '/') return ['/']
  return currentPath.value.split('/').filter(Boolean)
})

async function loadDir(path) {
  if (!props.serverId) return
  loading.value = true
  try {
    const data = await files.list(props.serverId, path)
    entries.value = data.entries
    currentPath.value = data.path
  } catch (e) {
    ElMessage.error('读取目录失败: ' + (e.response?.data?.detail || e.message))
    entries.value = []
  } finally {
    loading.value = false
  }
}

function refresh() {
  loadDir(currentPath.value)
}

function navigateInto(path) {
  loadDir(path)
}

function navigateToSeg(idx) {
  if (idx === 0) {
    loadDir('/')
  } else {
    const parts = currentPath.value.split('/').filter(Boolean)
    const target = '/' + parts.slice(0, idx).join('/')
    loadDir(target)
  }
}

function goUp() {
  if (currentPath.value === '/') return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  loadDir(parts.length ? '/' + parts.join('/') : '/')
}

function rowDblClick(row) {
  if (row.type === 'directory') {
    navigateInto(row.path)
  } else {
    downloadFile(row.path)
  }
}

function downloadFile(path) {
  const url = files.downloadUrl(props.serverId, path)
  const a = document.createElement('a')
  a.href = url
  a.download = path.split('/').pop()
  a.click()
}

function showUploadDialog() {
  uploadPath.value = currentPath.value === '/'
    ? '/'
    : currentPath.value + '/'
  uploadFileData.value = null
  uploadDialogVisible.value = true
}

function onFileSelected(e) {
  const file = e.target.files[0]
  if (!file) return
  const baseName = file.name.replace(/\\/g, '/').split('/').pop()
  uploadPath.value = uploadPath.value.replace(/\/$/, '') + '/' + baseName
  const reader = new FileReader()
  reader.onload = (ev) => {
    const base64 = ev.target.result.split(',')[1]
    uploadFileData.value = { name: baseName, base64 }
  }
  reader.readAsDataURL(file)
}

async function doUpload() {
  if (!uploadFileData.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    await files.upload(props.serverId, uploadPath.value, uploadFileData.value.base64)
    ElMessage.success('上传成功')
    uploadDialogVisible.value = false
    refresh()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

function formatSize(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// Watch serverId to load initial directory
import { watch } from 'vue'
watch(() => props.serverId, (id) => {
  if (id) loadDir('/')
}, { immediate: true })
</script>

<style scoped>
.path-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--cream-strong);
  border: 2px solid var(--border);
  border-radius: 18px;
  font-size: 13px;
}
.path-label { color: var(--text-secondary); font-weight: 800; }
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.file-table { cursor: default; }
</style>
