<script setup lang="ts">
import { ref } from 'vue'
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
  <div class="wrap" style="max-width:360px;padding:48px 24px">
    <h2>看板登录</h2>
    <p class="muted">账号</p>
    <input v-model="account" style="width:100%;margin-bottom:12px" />
    <p class="muted">密码</p>
    <input v-model="password" type="password" style="width:100%;margin-bottom:12px" @keyup.enter="submit" />
    <button class="toggle" type="button" @click="submit">登录</button>
    <p v-if="msg" style="color:var(--neg)">{{ msg }}</p>
  </div>
</template>
