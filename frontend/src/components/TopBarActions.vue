<script setup lang="ts">
/** 顶栏：退出（全角色）+ 非管理员自改密码。 */
import { onMounted, ref } from 'vue'
import { fetchSession } from '../api/client'

const isAdmin = ref(true) // 默认隐藏改密，等 session
const showPw = ref(false)
const oldPw = ref('')
const newPw = ref('')
const msg = ref('')
const msgCls = ref('')

onMounted(async () => {
  try {
    const s = await fetchSession()
    isAdmin.value = !!(s as { is_admin?: boolean }).is_admin
  } catch {
    isAdmin.value = true
  }
})

async function logout() {
  try {
    await fetch('/api/v1/logout', { method: 'POST', credentials: 'same-origin' })
  } catch {
    /* ignore */
  }
  location.replace('/login')
}

async function savePw() {
  if (newPw.value.length < 4) {
    msg.value = '新密码至少 4 位'
    msgCls.value = 'err'
    return
  }
  msg.value = '保存中…'
  msgCls.value = ''
  try {
    const r = await fetch('/api/my_passwd', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old: oldPw.value, new: newPw.value }),
    })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) {
      msg.value = (d as { detail?: string }).detail || '失败'
      msgCls.value = 'err'
      return
    }
    msg.value = (d as { note?: string }).note || '已修改'
    msgCls.value = 'ok'
    setTimeout(() => {
      showPw.value = false
      location.replace('/login')
    }, 800)
  } catch (e) {
    msg.value = '网络错误'
    msgCls.value = 'err'
  }
}
</script>
<template>
  <button type="button" class="toggle" id="logoutBtn" @click="logout">退出</button>
  <button v-if="!isAdmin" type="button" class="toggle" id="pwBtn" @click="showPw = true">
    <span>🔑</span> 密码
  </button>
  <Teleport to="body">
    <div
      v-if="showPw"
      id="pwModal"
      style="
        display: flex;
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.55);
        z-index: 9999;
        align-items: center;
        justify-content: center;
      "
      @click.self="showPw = false"
    >
      <div
        style="
          background: var(--card, #1e293b);
          border-radius: 12px;
          padding: 20px;
          width: min(360px, 92vw);
          border: 1px solid var(--line, #334155);
        "
      >
        <div style="font-size: 16px; font-weight: 700; margin-bottom: 10px">修改密码</div>
        <div
          style="
            font-size: 12px;
            color: #fde68a;
            margin-bottom: 10px;
            padding: 8px;
            background: #422006;
            border-radius: 8px;
          "
        >
          密码管理员可见，请勿使用你在其他地方用的密码
        </div>
        <label style="font-size: 12px; color: #94a3b8">旧密码</label>
        <input v-model="oldPw" type="password" style="width: 100%; margin: 4px 0 10px" id="pwOld" />
        <label style="font-size: 12px; color: #94a3b8">新密码（至少 4 位）</label>
        <input v-model="newPw" type="password" style="width: 100%; margin: 4px 0 10px" id="pwNew" />
        <div id="pwMsg" :style="{ color: msgCls === 'err' ? '#f87171' : '#86efac', fontSize: '12px' }">
          {{ msg }}
        </div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
          <button type="button" class="ghost mini" id="pwCancel" @click="showPw = false">取消</button>
          <button type="button" class="mini" id="pwOk" @click="savePw">保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
