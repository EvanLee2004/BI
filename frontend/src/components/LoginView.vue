<script setup lang="ts">
import { ref } from 'vue'
import SciFiPanel from './SciFiPanel.vue'

const account = ref('')
const password = ref('')
const msg = ref('')
async function submit() {
  msg.value = ''
  try {
    const r = await fetch('/api/v1/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account: account.value, password: password.value }),
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
  <div class="wrap login-wrap" style="max-width: 400px; padding: 64px 24px">
    <SciFiPanel title="看板登录" state="normal">
      <p class="muted" style="margin: 0 0 6px">账号</p>
      <input v-model="account" class="scifi-input" style="width: 100%; margin-bottom: 12px" />
      <p class="muted" style="margin: 0 0 6px">密码</p>
      <input
        v-model="password"
        type="password"
        class="scifi-input"
        style="width: 100%; margin-bottom: 12px"
        @keyup.enter="submit"
      />
      <button class="dsdk-button" type="button" @click="submit">登录</button>
      <p v-if="msg" style="color: var(--neg)">{{ msg }}</p>
    </SciFiPanel>
  </div>
</template>
