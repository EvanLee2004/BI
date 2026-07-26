<script setup lang="ts">
import '../styles/components/LoginView.css'
/** 2.5.0：全员唯一登录页（看端霓虹壳）；支持 ?next= 安全回跳（后端白名单） */
import { onMounted, ref } from 'vue'
import SciFiPanel from './SciFiPanel.vue'

const account = ref('')
const password = ref('')
const msg = ref('')

function readQuery(): { next: string; msg: string } {
  try {
    const q = new URLSearchParams(location.search)
    return {
      next: (q.get('next') || q.get('redirect') || '').trim(),
      msg: (q.get('msg') || '').trim(),
    }
  } catch {
    return { next: '', msg: '' }
  }
}

onMounted(() => {
  const q = readQuery()
  if (q.msg) msg.value = q.msg
})

async function submit() {
  msg.value = ''
  const q = readQuery()
  try {
    const body: { account: string; password: string; next?: string } = {
      account: account.value,
      password: password.value,
    }
    if (q.next) body.next = q.next
    const r = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const d = await r.json()
    if (!r.ok) {
      msg.value = d.detail || '登录失败'
      return
    }
    window.location.href = d.redirect || '/'
  } catch (e) {
    msg.value = String(e)
  }
}
</script>
<template>
  <div class="login-page">
    <div class="login-card-host">
      <SciFiPanel title="登录" panel-class="login-panel">
        <p class="login-sub muted">甲骨易 · 经营看板</p>
        <label class="login-lab">账号</label>
        <input
          v-model="account"
          class="scifi-input login-input"
          autocomplete="username"
          autofocus
        />
        <label class="login-lab">密码</label>
        <input
          v-model="password"
          type="password"
          class="scifi-input login-input"
          autocomplete="current-password"
          @keyup.enter="submit"
        />
        <button class="dsdk-button login-btn" type="button" @click="submit">进入</button>
        <p v-if="msg" class="login-err">{{ msg }}</p>
      </SciFiPanel>
    </div>
  </div>
</template>

