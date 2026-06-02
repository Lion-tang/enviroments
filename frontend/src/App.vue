<template>
  <!-- Standalone SSH terminal (full-screen, hash routed) -->
  <StandaloneSSH
    v-if="sshRoute"
    :target-id="sshRoute.id"
    :target-type="sshRoute.type"
    :target-label="sshRoute.label"
  />
  <!-- Normal app layout -->
  <div v-else class="app-shell">

    <!-- Sidebar -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-logo">
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'">
          {{ sidebarCollapsed ? '☰' : '✕' }}
        </button>
        <span v-if="!sidebarCollapsed" class="logo-icon">🖥</span>
        <span v-if="!sidebarCollapsed" class="logo-text">Enviroments</span>
      </div>

      <nav class="sidebar-nav">
        <button
          class="nav-item"
          :class="{ active: activeTab === 'servers' }"
          @click="activeTab = 'servers'"
          :title="sidebarCollapsed ? '服务器' : ''"
        >
          <span class="nav-icon">🖧</span>
          <span v-if="!sidebarCollapsed">服务器</span>
        </button>

        <button
          class="nav-item"
          :class="{ active: activeTab === 'switches' }"
          @click="activeTab = 'switches'"
          :title="sidebarCollapsed ? '交换机' : ''"
        >
          <span class="nav-icon">🔌</span>
          <span v-if="!sidebarCollapsed">交换机</span>
        </button>

        <button
          class="nav-item"
          :class="{ active: activeTab === 'favorites' }"
          @click="activeTab = 'favorites'"
          :title="sidebarCollapsed ? '我的收藏' : ''"
        >
          <span class="nav-icon">⭐</span>
          <span v-if="!sidebarCollapsed">我的收藏</span>
        </button>

        <button
          class="nav-item"
          :class="{ active: activeTab === 'topology' }"
          @click="activeTab = 'topology'"
          :title="sidebarCollapsed ? '组网图' : ''"
        >
          <span class="nav-icon">⌘</span>
          <span v-if="!sidebarCollapsed">组网图</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="user-block">
          <span class="user-avatar">👤</span>
          <div v-if="!sidebarCollapsed" class="user-info">
            <span class="user-name">{{ username }}</span>
            <span class="user-role">管理员</span>
          </div>
          <button class="logout-btn" @click="logout" title="退出登录">⚐</button>
        </div>
      </div>
    </aside>

    <!-- Main -->
    <div class="main-area" :style="{ marginLeft: sidebarCollapsed ? '58px' : '220px' }">
      <!-- Top bar -->
      <header class="topbar">
        <div class="topbar-title">
          <h1>{{ tabTitle }}</h1>
          <span class="topbar-sub">{{ tabSubtitle }}</span>
        </div>

        <!-- Stats -->
        <div class="stats-row">
          <div class="stat-chip stat-online">
            <span class="stat-dot"></span>
            <span>{{ activeTab === 'topology' ? '已发现' : '在线' }}</span>
            <strong>{{ activeTab === 'topology' ? topologyFoundCount : (activeTab === 'servers' ? serverOnlineCount : switchOnlineCount) }}</strong>
          </div>
          <div class="stat-chip stat-offline">
            <span class="stat-dot"></span>
            <span>{{ activeTab === 'topology' ? '待确认' : '离线' }}</span>
            <strong>{{ activeTab === 'topology' ? topologyPendingCount : (activeTab === 'servers' ? serverOfflineCount : switchOfflineCount) }}</strong>
          </div>
          <button class="theme-toggle" @click="toggleTheme" :title="isDark ? '切换亮色主题' : '切换暗色主题'">
            {{ isDark ? '☀️' : '🌙' }}
          </button>
        </div>
      </header>

      <!-- Content -->
      <main class="content">
        <div class="fade-in">
          <ServerFavorites
            v-if="activeTab === 'favorites'"
            @stats="onFavoritesStats"
          />
          <ServerList
            v-else-if="activeTab === 'servers'"
            @stats="onServerStats"
          />
          <SwitchList
            v-else-if="activeTab === 'switches'"
            @stats="onSwitchStats"
          />
          <TopologyView
            v-else-if="activeTab === 'topology'"
            @stats="onTopologyStats"
          />
        </div>
      </main>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ServerList from './views/ServerList.vue'
import ServerFavorites from './views/ServerFavorites.vue'
import SwitchList from './views/SwitchList.vue'
import StandaloneSSH from './views/StandaloneSSH.vue'
import TopologyView from './views/TopologyView.vue'

const activeTab = ref('servers')
const username = ref(localStorage.getItem('username') || '')
const sshRoute = ref(null)
const isDark = ref(localStorage.getItem('theme') !== 'light')
const sidebarCollapsed = ref(localStorage.getItem('sidebar') === 'collapsed')
const serverTotal = ref(0)
const serverOnlineCount = ref(0)
const serverOfflineCount = ref(0)
const switchTotal = ref(0)
const switchOnlineCount = ref(0)
const switchOfflineCount = ref(0)
const favoriteTotal = ref(0)
const favoriteOnlineCount = ref(0)
const topologyFoundCount = ref(0)
const topologyPendingCount = ref(0)

const tabTitle = computed(() => {
  if (activeTab.value === 'servers') return '服务器列表'
  if (activeTab.value === 'switches') return '交换机列表'
  if (activeTab.value === 'favorites') return '我的收藏'
  if (activeTab.value === 'topology') return '组网图'
  return 'Enviroments'
})

const tabSubtitle = computed(() => {
  if (activeTab.value === 'servers') return `共 ${serverTotal.value} 台`
  if (activeTab.value === 'switches') return `共 ${switchTotal.value} 台`
  if (activeTab.value === 'favorites') return `共 ${favoriteTotal.value} 台收藏`
  if (activeTab.value === 'topology') return `发现 ${topologyFoundCount.value} 条链路`
  return ''
})

function onServerStats(stats) {
  serverTotal.value = stats.total || 0
  serverOnlineCount.value = stats.online || 0
  serverOfflineCount.value = stats.offline || 0
}

function onSwitchStats(stats) {
  switchTotal.value = stats.total || 0
  switchOnlineCount.value = stats.online || 0
  switchOfflineCount.value = stats.offline || 0
}

function onFavoritesStats(stats) {
  favoriteTotal.value = stats.total || 0
  favoriteOnlineCount.value = stats.online || 0
}

function onTopologyStats(stats) {
  topologyFoundCount.value = stats.found || 0
  topologyPendingCount.value = stats.pending || 0
}

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('user_id')
  window.location.reload()
}

function toggleTheme() {
  isDark.value = !isDark.value
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

watch(sidebarCollapsed, (val) => {
  localStorage.setItem('sidebar', val ? 'collapsed' : 'expanded')
})

function parseHash() {
  const hash = window.location.hash
  const match = hash.match(/^#\/ssh\/([a-z]+)\/(\d+)(?:\/(.+))?$/)
  if (match) {
    return {
      type: match[1],
      id: Number(match[2]),
      label: decodeURIComponent(match[3] || `${match[1]} #${match[2]}`),
    }
  }
  return null
}

sshRoute.value = parseHash()
window.addEventListener('hashchange', () => { sshRoute.value = parseHash() })
</script>

<style>
/* ─── Shell Layout ─────────────────────────────────────────────────────────── */

.app-shell {
  display: flex;
  min-height: 100vh;
  background:
    radial-gradient(circle at 18% 8%, rgba(255, 107, 157, 0.12), transparent 26%),
    radial-gradient(circle at 86% 18%, rgba(255, 209, 102, 0.22), transparent 28%),
    var(--bg-base);
}

/* ─── Sidebar ──────────────────────────────────────────────────────────────── */

.sidebar {
  width: 220px;
  min-height: 100vh;
  background: rgba(255, 249, 245, 0.94);
  border-right: 3px solid var(--border);
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 10;
  transition: width 0.25s ease;
  overflow: hidden;
  backdrop-filter: blur(14px);
}

.sidebar.collapsed {
  width: 58px;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 14px;
  border-bottom: 2px solid var(--border);
  min-height: 64px;
  overflow: hidden;
}

.collapse-btn {
  font-size: 16px;
  background: #fff;
  border: 2px solid var(--border);
  color: var(--accent);
  cursor: pointer;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  transition: var(--transition);
  flex-shrink: 0;
  line-height: 1;
  font-weight: 800;
}
.collapse-btn:hover { color: #fff; background: var(--accent); transform: rotate(-6deg); }

.logo-icon { font-size: 22px; }

.logo-text {
  font-size: 17px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: 0;
  font-family: 'Nunito', 'Noto Sans SC', sans-serif;
}

/* Nav */
.sidebar-nav {
  flex: 1;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 999px;
  border: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  transition: var(--transition);
  width: 100%;
  text-align: left;
  position: relative;
}

.nav-item:hover {
  background: #fff;
  border-color: var(--border);
  color: var(--accent);
}

.nav-item.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 800;
  box-shadow: 4px 4px 0 rgba(255, 140, 66, 0.2);
}

.nav-item.active::before {
  content: none;
}

.nav-icon { font-size: 16px; }

.nav-badge {
  margin-left: auto;
  background: var(--accent);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 20px;
}

/* Footer */
.sidebar-footer {
  border-top: 2px solid var(--border);
  padding: 14px;
}

.user-block {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 2px solid var(--border);
  border-radius: 20px;
  padding: 10px;
}

.user-avatar { font-size: 22px; }

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 800;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 11px;
  color: var(--text-muted);
}

.logout-btn {
  background: var(--cream-strong);
  border: 2px solid var(--border);
  color: var(--accent);
  cursor: pointer;
  font-size: 14px;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  transition: var(--transition);
}

.logout-btn:hover { color: #fff; background: var(--offline); border-color: var(--offline); }

/* ─── Main Area ────────────────────────────────────────────────────────────── */

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  overflow: hidden;
  min-width: 0;
}

/* Top bar */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  border-bottom: 3px solid var(--border);
  background: rgba(255, 249, 245, 0.92);
  position: sticky;
  top: 0;
  z-index: 5;
  backdrop-filter: blur(14px);
}

.topbar-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.topbar-title h1 {
  font-size: 24px;
  font-weight: 800;
  color: var(--text-primary);
}

.topbar-sub {
  font-size: 13px;
  color: var(--text-muted);
}

.stats-row {
  display: flex;
  gap: 10px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-card);
  border: 2px solid var(--border);
  font-weight: 700;
}

.stat-chip strong { color: var(--text-primary); font-weight: 600; }

.stat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.stat-online .stat-dot { background: var(--online); box-shadow: 0 0 6px var(--online); }
.stat-offline .stat-dot { background: var(--offline); }

.theme-toggle {
  background: var(--bg-card);
  border: 2px solid var(--border);
  border-radius: 999px;
  width: 40px;
  height: 34px;
  padding: 0;
  font-size: 16px;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  align-items: center;
}
.theme-toggle:hover { background: var(--bg-hover); transform: rotate(6deg); }

/* Content */
.content {
  padding: 24px 28px;
  overflow-x: hidden;
}
</style>
