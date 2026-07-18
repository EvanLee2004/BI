<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { adminLogin } from '../api'

const route = useRoute()
const account = ref('lushasha')
const password = ref('')
const err = ref('')
const loading = ref(false)

onMounted(() => {
  const q = route.query.msg
  if (typeof q === 'string' && q) err.value = q
})

async function submit() {
  err.value = ''
  loading.value = true
  try {
    const r = await adminLogin(account.value, password.value)
    if (r.ok) {
      const redir = (route.query.redirect as string) || r.redirect || '/admin'
      // 整页跳转保证 cookie 落地后布局重挂
      location.replace(redir.startsWith('/admin') ? redir : '/admin')
      return
    }
    err.value = r.detail || '账号或密码不正确'
  } catch {
    err.value = '网络错误，请重试'
  } finally {
    loading.value = false
  }
}

function toggleTheme() {
  const light = !document.documentElement.classList.contains('theme-light')
  document.documentElement.classList.toggle('theme-light', light)
  try {
    localStorage.setItem('cockpit-theme', light ? 'light' : 'dark')
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <div class="admin-login-page">
    <el-button class="theme-btn" text @click="toggleTheme">◑ 浅色</el-button>
    <el-card class="login-card" shadow="always">
      <h1>管理员端登录</h1>
      <el-alert v-if="err" :title="err" type="error" show-icon :closable="false" style="margin-bottom: 12px" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号">
          <el-input v-model="account" autocomplete="username" autofocus />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" autocomplete="current-password" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">进入</el-button>
      </el-form>
      <p class="hint">管理员账号见「看板账号」表（默认 lushasha）。</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-card {
  width: 320px;
  border-radius: 12px;
}
.login-card h1 {
  font-size: 18px;
  margin: 0 0 16px;
}
.hint {
  color: var(--admin-mut, #64748b);
  font-size: 12px;
  margin-top: 12px;
}
.theme-btn {
  position: fixed;
  top: 14px;
  right: 16px;
}
</style>
