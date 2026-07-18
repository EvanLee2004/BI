<script setup lang="ts">
/** 看板登录 · 54.2 深空气质壳（纯样式，无新库） */
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
  <div class="login-page">
    <div class="login-card-host">
      <SciFiPanel title="看板登录" panel-class="login-panel">
        <p class="login-sub muted">甲骨易 · 智能经营罗盘</p>
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
        <button class="dsdk-button login-btn" type="button" @click="submit">登录</button>
        <p v-if="msg" class="login-err">{{ msg }}</p>
      </SciFiPanel>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  box-sizing: border-box;
}
.login-card-host {
  width: min(400px, 100%);
}
.login-sub {
  margin: 0 0 16px;
  font-size: 12.5px;
  letter-spacing: 0.04em;
}
.login-lab {
  display: block;
  font-size: 12.5px;
  color: var(--mut, #93a1c0);
  margin: 0 0 6px;
}
.login-input {
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 14px;
}
/* R6：主 CTA 必须 scifi 青，禁止 kit 紫/默认紫压过 */
button.dsdk-button.login-btn,
.login-btn {
  width: 100%;
  margin-top: 4px;
  cursor: pointer;
  border: 1px solid #22d3ee !important;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 16px;
  font-weight: 600;
  text-transform: none;
  background: linear-gradient(90deg, #0891b2, #22d3ee) !important;
  color: #04101c !important;
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.35);
}
button.dsdk-button.login-btn:hover,
.login-btn:hover {
  filter: brightness(1.06);
  background: linear-gradient(90deg, #0e7490, #67e8f9) !important;
  border-color: #67e8f9 !important;
}
.login-err {
  color: var(--neg, #fb7185);
  font-size: 13px;
  margin: 12px 0 0;
}
</style>
