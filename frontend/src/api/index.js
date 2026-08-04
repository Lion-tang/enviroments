import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

// ── Auth interceptor ──────────────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('user_id')
      window.location.href = '/#/login'
    }
    return Promise.reject(error)
  }
)

// ── Auth API (bypass interceptor for login/register) ─────────────────────────
export const auth = {
  login: (data) => axios.post('/api/v1/auth/login', data).then(r => r.data),
  register: (data) => axios.post('/api/v1/auth/register', data).then(r => r.data),
  me: () => api.get('/auth/me').then(r => r.data),
}

export const servers = {
  list: () => api.get('/servers', { params: { compact: true } }).then(r => r.data),

  get: (id) => api.get(`/servers/${id}`).then(r => r.data),

  create: (data) => api.post('/servers', data).then(r => r.data),

  update: (id, data) => api.put(`/servers/${id}`, data).then(r => r.data),

  delete: (id) => api.delete(`/servers/${id}`),

  checkStatus: (id) => api.get(`/servers/${id}/status`).then(r => r.data),

  checkStatusBatch: (serverIds = null) =>
    api.post('/servers/status/batch', { server_ids: serverIds }).then(r => r.data),

  fetchDetail: (id, refresh = false) =>
    api.get(`/servers/${id}/detail`, { params: { refresh } }).then(r => r.data),

  favorite: (id) => api.post(`/servers/${id}/favorite`).then(r => r.data),

  unfavorite: (id) => api.delete(`/servers/${id}/favorite`).then(r => r.data),

  occupy: (id) => api.post(`/servers/${id}/occupy`).then(r => r.data),

  release: (id) => api.post(`/servers/${id}/release`).then(r => r.data),

  openBmc: (id) => api.get(`/servers/${id}/open-bmc`).then(r => r.data),
}

export const files = {
  list: (serverId, path) => api.get(`/servers/${serverId}/files`, { params: { path } }).then(r => r.data),

  downloadUrl: (serverId, path) => `/api/v1/servers/${serverId}/files/download?path=${encodeURIComponent(path)}`,

  download: (serverId, path) =>
    api.get(`/servers/${serverId}/files/download`, {
      params: { path },
      responseType: 'blob',
      timeout: 0,
    }).then(r => r.data),

  upload: (serverId, path, content, config = {}) => {
    if (content instanceof Blob) {
      const form = new FormData()
      form.append('path', path)
      form.append('file', content, content.name || 'upload.bin')
      return api.post(
        `/servers/${serverId}/files/upload`,
        form,
        { timeout: 0, ...config },
      ).then(r => r.data)
    }
    return api.post(
      `/servers/${serverId}/files`,
      { path, content },
      { timeout: 0, ...config },
    ).then(r => r.data)
  },

  mkdir: (serverId, path, config = {}) =>
    api.post(`/servers/${serverId}/files/mkdir`, { path }, config).then(r => r.data),
}

export const logs = {
  list: (serverId, limit = 100, offset = 0) =>
    api.get(`/servers/${serverId}/logs`, { params: { limit, offset } }).then(r => r.data),

  clear: (serverId) => api.delete(`/servers/${serverId}/logs/clear`),
}

export const switches = {
  list: () => api.get('/switches').then(r => r.data),

  get: (id) => api.get(`/switches/${id}`).then(r => r.data),

  create: (data) => api.post('/switches', data).then(r => r.data),

  update: (id, data) => api.put(`/switches/${id}`, data).then(r => r.data),

  delete: (id) => api.delete(`/switches/${id}`),

  getServers: (id) => api.get(`/switches/${id}/servers`).then(r => r.data),

  getDetail: (id) => api.get(`/switches/${id}/detail`).then(r => r.data),

  fetchDetail: (id, refresh = false) =>
    api.get(`/switches/${id}/detail`, { params: { refresh } }).then(r => r.data),

  checkStatus: (id) => api.get(`/switches/${id}/status`).then(r => r.data),

  setServers: (switchId, serverIds) =>
    api.post(`/switches/${switchId}/servers`, { server_ids: serverIds }),

  getServers: (switchId) =>
    api.get(`/switches/${switchId}/servers`).then(r => r.data),
}

export const serverSwitchAssoc = {
  get: (serverId) => api.get(`/switches/server/${serverId}/switches`).then(r => r.data),

  set: (serverId, switchIds) => api.post(`/switches/server/${serverId}/switches`, { switch_ids: switchIds }),
}

export const switchLogs = {
  list: (switchId, limit = 200, offset = 0) =>
    api.get(`/switches/${switchId}/logs`, { params: { limit, offset } }).then(r => r.data),

  clear: (switchId) => api.delete(`/switches/${switchId}/logs/clear`),
}

export const topology = {
  get: () => api.get('/topology').then(r => r.data),

  discover: (serverIds = null) =>
    api.post('/topology/discover', { server_ids: serverIds }, { timeout: 300000 }).then(r => r.data),
}
