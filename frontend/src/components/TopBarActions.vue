<script setup lang="ts">
/** 顶栏：导出 HTML + 退出（全角色）+ 非管理员自改密码。2.2.7 主路径 .html。 */
import { onMounted, ref } from 'vue'
import { fetchSession } from '../api/client'
import { useCockpitStore } from '../stores/cockpit'

const store = useCockpitStore()
const isAdmin = ref(true) // 默认隐藏改密，等 session
const showPw = ref(false)
const oldPw = ref('')
const newPw = ref('')
const msg = ref('')
const msgCls = ref('')
const exporting = ref(false)

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

/** ③ 导出：后端 Vue 皮 HTML（Playwright 抓页或降级壳），按 X-Filename 下载。 */
async function exportHtml() {
  if (exporting.value) return
  if (location.protocol === 'file:') {
    alert('导出需在看板服务页面使用')
    return
  }
  const blk = store.period || ''
  // 整体页走 /api/export.html：现网 nginx 必反代 /api（export.html 裸路径需 conf 含 export.html 才反代）
  // BU 页 /bu/{name}/export.html 已由 location 的 bu 前缀反代
  const url =
    store.scope === 'bu' && store.buName
      ? `/bu/${encodeURIComponent(store.buName)}/export.html?blk=${encodeURIComponent(blk)}`
      : `/api/export.html?blk=${encodeURIComponent(blk)}`
  exporting.value = true
  try {
    const r = await fetch(url, { credentials: 'same-origin' })
    if (!r.ok) {
      const t = await r.text().catch(() => '')
      throw new Error(t || `HTTP ${r.status}`)
    }
    const fn =
      decodeURIComponent(r.headers.get('X-Filename') || '') || '甲骨易智能经营罗盘.html'
    const b = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(b)
    a.download = fn
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    alert('导出失败：' + (e instanceof Error ? e.message : String(e)))
  } finally {
    exporting.value = false
  }
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
  <button
    type="button"
    class="toggle export-html-btn"
    id="exportBtn"
    :disabled="exporting"
    @click="exportHtml"
  >
    <span>⬇</span> {{ exporting ? '生成中…' : '导出' }}
  </button>
  <button
    v-if="!store.archiveMode"
    type="button"
    class="toggle"
    id="logoutBtn"
    @click="logout"
  >退出</button>
  <button
    v-if="!isAdmin && !store.archiveMode"
    type="button"
    class="toggle"
    id="pwBtn"
    @click="showPw = true"
  >
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
