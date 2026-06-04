<template>
  <div class="login-page">
    <div class="login-shell">
      <section class="guide-panel">
        <div class="guide-kicker">第一次使用</div>
        <h1 class="guide-title">一个面向小团队的小型服务器管理应用</h1>
        <p class="guide-sub">
          Enviroments 适合管理少量服务器和交换机，把资产记录、在线检测、Web SSH、文件访问和链路拓扑放在一个页面里。第一次进来可以先建账号，再逐步录入资产。
        </p>

        <div class="guide-flow">
          <div v-for="item in guideItems" :key="item.step" class="guide-item">
            <span class="guide-step">{{ item.step }}</span>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.desc }}</p>
            </div>
          </div>
        </div>

        <div class="guide-note">
          <strong>推荐顺序</strong>
          <span>先添加服务器，再添加交换机，最后建立关联并生成拓扑图。</span>
        </div>
      </section>

      <div class="login-card">
        <div class="login-logo">🖥</div>
        <h1 class="login-title">Enviroments</h1>
        <p class="login-sub">小型服务器管理应用</p>

        <el-tabs v-model="activeTab" class="auth-tabs">
          <el-tab-pane label="登录" name="login">
            <el-form :model="loginForm" label-width="0" @submit.prevent="doLogin" class="auth-form">
              <el-form-item>
                <el-input v-model="loginForm.username" placeholder="用户名" autocomplete="username" size="large" />
              </el-form-item>
              <el-form-item>
                <el-input v-model="loginForm.password" type="password" placeholder="密码" show-password autocomplete="current-password" size="large" @keyup.enter="doLogin" />
              </el-form-item>
              <el-button type="primary" class="auth-submit" :loading="loading" @click="doLogin">登录</el-button>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="注册" name="register">
            <el-form :model="regForm" label-width="0" @submit.prevent="doRegister" class="auth-form">
              <el-form-item>
                <el-input v-model="regForm.username" placeholder="用户名（2-50字符）" autocomplete="username" size="large" />
              </el-form-item>
              <el-form-item>
                <el-input v-model="regForm.password" type="password" placeholder="密码（至少6位）" show-password autocomplete="new-password" size="large" @keyup.enter="doRegister" />
              </el-form-item>
              <el-button type="primary" class="auth-submit" :loading="loading" @click="doRegister">注册</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>

        <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="true" @close="errorMsg=''" style="margin-top:16px" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const activeTab = ref('login')
const loading = ref(false)
const errorMsg = ref('')

const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ username: '', password: '' })
const guideItems = [
  {
    step: '01',
    title: '注册账号',
    desc: '创建自己的登录账号，后续服务器收藏和操作记录都会和账号关联。',
  },
  {
    step: '02',
    title: '添加服务器',
    desc: '录入 IP、SSH 账号、标签、备注和 BMC 信息，系统会采集在线状态和硬件信息。',
  },
  {
    step: '03',
    title: '添加交换机',
    desc: '录入交换机管理地址和登录信息，用于查看设备详情和查询 MAC 地址表。',
  },
  {
    step: '04',
    title: '关联并生成拓扑',
    desc: '把服务器关联到可能连接的交换机，点击重新生成拓扑图查看两端接口。',
  },
]

async function doLogin() {
  if (!loginForm.username || !loginForm.password) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await axios.post('/api/v1/auth/login', {
      username: loginForm.username,
      password: loginForm.password,
    })
    localStorage.setItem('token', res.data.access_token)
    localStorage.setItem('username', res.data.username)
    localStorage.setItem('user_id', res.data.user_id)
    ElMessage.success(`欢迎，${res.data.username}`)
    window.location.reload()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  if (!regForm.username || !regForm.password) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await axios.post('/api/v1/auth/register', {
      username: regForm.username,
      password: regForm.password,
    })
    localStorage.setItem('token', res.data.access_token)
    localStorage.setItem('username', res.data.username)
    localStorage.setItem('user_id', res.data.user_id)
    ElMessage.success(`注册成功，欢迎 ${res.data.username}`)
    window.location.reload()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at 16% 18%, rgba(255, 107, 157, 0.16), transparent 28%),
    radial-gradient(circle at 84% 14%, rgba(255, 209, 102, 0.24), transparent 30%),
    linear-gradient(180deg, #fff9f5 0%, #fff3eb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: auto;
  padding: 36px;
  box-sizing: border-box;
}

.login-page::before {
  content: '';
  position: absolute;
  top: 10%;
  left: 8%;
  width: 128px;
  height: 128px;
  background: rgba(255, 209, 102, 0.28);
  border-radius: 50%;
}

.login-page::after {
  content: '';
  position: absolute;
  right: 12%;
  bottom: 16%;
  width: 160px;
  height: 160px;
  background: rgba(255, 107, 157, 0.16);
  border-radius: 50%;
}

.login-shell {
  width: min(1080px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 24px;
  align-items: stretch;
  position: relative;
  z-index: 1;
}

.guide-panel {
  background: rgba(255, 255, 255, 0.74);
  border: 3px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 34px;
  min-height: 520px;
  display: flex;
  flex-direction: column;
}

.guide-kicker {
  color: var(--orange-dark);
  font-size: 13px;
  font-weight: 900;
  margin-bottom: 12px;
}

.guide-title {
  color: var(--text-primary);
  font-size: 32px;
  line-height: 1.25;
  margin: 0 0 12px;
  font-weight: 900;
  letter-spacing: 0;
}

.guide-sub {
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.8;
  margin: 0 0 22px;
  max-width: 620px;
}

.guide-flow {
  display: grid;
  gap: 12px;
}

.guide-item {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 12px;
  align-items: start;
  padding: 14px;
  background: var(--bg-card);
  border: 2px solid var(--border);
  border-radius: 18px;
}

.guide-step {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: var(--cream-strong);
  color: var(--orange-dark);
  display: grid;
  place-items: center;
  font-weight: 900;
  border: 2px solid var(--border);
}

.guide-item strong {
  color: var(--text-primary);
  font-size: 15px;
}

.guide-item p {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  margin: 4px 0 0;
}

.guide-note {
  margin-top: auto;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 13px 15px;
  border-radius: 16px;
  background: var(--cream-strong);
  border: 2px solid var(--border);
  color: var(--text-secondary);
  font-size: 13px;
}

.guide-note strong {
  color: var(--text-primary);
  white-space: nowrap;
}

.login-card {
  background: var(--bg-card);
  border: 3px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 42px 36px 36px;
  width: 380px;
  box-shadow: var(--shadow-lg);
  position: relative;
  animation: fadeIn 0.4s ease;
}

.login-logo {
  text-align: center;
  font-size: 34px;
  width: 72px;
  height: 72px;
  margin: 0 auto 12px;
  display: grid;
  place-items: center;
  background: var(--cream-strong);
  border: 3px solid var(--border);
  border-radius: 24px;
  box-shadow: 5px 5px 0 rgba(255, 140, 66, 0.16);
}

.login-title {
  text-align: center;
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 4px;
  letter-spacing: 0;
  font-family: 'Nunito', 'Noto Sans SC', sans-serif;
}

.login-sub {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 28px;
}

.auth-tabs { margin-top: 8px; }

.auth-form :deep(.el-form-item) { margin-bottom: 14px; }

.auth-form :deep(.el-input__wrapper) {
  padding: 12px 16px !important;
}

.auth-submit {
  width: 100%;
  height: 42px;
  font-size: 15px;
  margin-top: 4px;
}

@media (max-width: 900px) {
  .login-page {
    align-items: flex-start;
    padding: 20px;
  }

  .login-shell {
    grid-template-columns: 1fr;
  }

  .login-card {
    width: auto;
  }

  .guide-panel {
    min-height: auto;
    padding: 24px;
  }

  .guide-title {
    font-size: 24px;
  }
}
</style>
