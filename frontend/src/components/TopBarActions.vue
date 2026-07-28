<script setup lang="ts">
/** 顶栏工具：主题外的 导出｜密码｜退出。2.6.7：去掉 ⋯ 折叠；退出二次确认（DataModal）；管理员无密码/无退出。 */
import { onMounted, ref } from 'vue'
import { fetchSession } from '../api/client'
import { useCockpitStore } from '../stores/cockpit'
import { showToast } from '../utils/toast'
import DataModal from './base/DataModal.vue'

const store = useCockpitStore()
const isAdmin = ref(true) // 默认隐藏改密/退出，等 session
const showPw = ref(false)
const showLogoutConfirm = ref(false)
const oldPw = ref('')
const newPw = ref('')
const msg = ref('')
const msgCls = ref('')
const exporting = ref(false)

onMounted(async () => {
  if (store.snapshotMode) {
    isAdmin.value = true
    return
  }
  try {
    const s = await fetchSession()
    isAdmin.value = !!(s as { is_admin?: boolean }).is_admin
  } catch {
    isAdmin.value = true
  }
})

async function doLogout() {
  showLogoutConfirm.value = false
  try {
    await fetch('/api/v1/logout', { method: 'POST', credentials: 'same-origin' })
  } catch {
    /* ignore */
  }
  location.replace('/login')
}

function requestLogout() {
  showLogoutConfirm.value = true
}

/** ③ 导出：2.2.9 自包含静态可交互快照 HTML。 */
async function exportHtml() {
  if (exporting.value) return
  if (location.protocol === 'file:') {
    showToast('这个页面是导出的静态快照，导出功能请回在线看板使用', 'warn')
    return
  }
  const blk = store.period || ''
  let theme = 'neon'
  try {
    const t = localStorage.getItem('cockpit-theme')
    if (t === 'neon' || t === 'dark' || t === 'light') theme = t
    else if (document.documentElement.dataset.theme) {
      const d = document.documentElement.dataset.theme
      if (d === 'neon' || d === 'dark' || d === 'light') theme = d
    }
  } catch {
    /* ignore */
  }
  const q = `blk=${encodeURIComponent(blk)}&theme=${encodeURIComponent(theme)}`
  const url =
    store.scope === 'bu' && store.buName
      ? `/api/v1/export/bu/${encodeURIComponent(store.buName)}/html?${q}`
      : `/api/v1/export.html?${q}`
  exporting.value = true
  try {
    const r = await fetch(url, { credentials: 'same-origin' })
    if (!r.ok) {
      const t = await r.text().catch(() => '')
      console.warn('[export]', r.status, t?.slice?.(0, 200) || '')
      throw new Error('export_failed')
    }
    const fn =
      decodeURIComponent(r.headers.get('X-Filename') || '') || '甲骨易经营看板.html'
    const b = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(b)
    a.download = fn
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    console.warn('[export]', e)
    showToast('导出没成功，请稍后再试一次', 'error')
  } finally {
    exporting.value = false
  }
}

function openPw() {
  showPw.value = true
}

async function savePw() {
  if (!newPw.value || !String(newPw.value).trim()) {
    msg.value = '新密码不能为空'
    msgCls.value = 'err'
    return
  }
  msg.value = '保存中…'
  msgCls.value = ''
  try {
    const r = await fetch('/api/v1/my_passwd', {
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
  } catch {
    msg.value = '网络错误'
    msgCls.value = 'err'
  }
}
</script>
<template>
  <!-- 2.2.9 快照模式：隐藏导出/退出/改密 -->
  <template v-if="!store.snapshotMode">
    <!-- 全视口唯一横排：桌面文案+图标；≤520 仅图标仍横排不折叠 -->
    <div class="tb-actions" data-testid="tb-actions">
      <button
        v-if="!store.archiveMode"
        type="button"
        class="toggle export-html-btn"
        id="exportBtn"
        :disabled="exporting"
        aria-label="导出"
        title="导出"
        @click="exportHtml"
      >
        <span class="tb-ico" aria-hidden="true">⬇</span>
        <span class="tb-lab">{{ exporting ? '生成中…' : '导出' }}</span>
      </button>
      <button
        v-if="!isAdmin && !store.archiveMode"
        type="button"
        class="toggle"
        id="pwBtn"
        aria-label="密码"
        title="密码"
        @click="openPw"
      >
        <span class="tb-ico" aria-hidden="true">🔑</span>
        <span class="tb-lab">密码</span>
      </button>
      <!-- B-5：管理员不显示退出（设置页最下唯一入口） -->
      <button
        v-if="!isAdmin && !store.archiveMode"
        type="button"
        class="toggle"
        id="logoutBtn"
        aria-label="退出"
        title="退出"
        @click="requestLogout"
      >
        <span class="tb-ico" aria-hidden="true">⎋</span>
        <span class="tb-lab">退出</span>
      </button>
    </div>
  </template>

  <DataModal
    :open="showLogoutConfirm"
    title="确认退出"
    @close="showLogoutConfirm = false"
  >
    <p class="tb-logout-q">您确认要退出吗？</p>
    <div class="tb-logout-actions">
      <button type="button" class="ghost mini" data-testid="logout-cancel" @click="showLogoutConfirm = false">
        取消
      </button>
      <button type="button" class="mini" data-testid="logout-confirm" @click="doLogout">
        确认
      </button>
    </div>
  </DataModal>

  <Teleport to="body">
    <div
      v-if="showPw"
      id="pwModal"
      style="
        display: flex;
        position: fixed;
        inset: 0;
        background: var(--mask-heavy);
        z-index: var(--z-password-mask, 9999);
        align-items: center;
        justify-content: center;
      "
      @click.self="showPw = false"
    >
      <div
        style="
          background: var(--card-solid);
          border-radius: 12px;
          padding: 20px;
          width: min(360px, 92vw);
          border: 1px solid var(--line);
        "
      >
        <div style="font-size: 16px; font-weight: 700; margin-bottom: 10px">修改密码</div>
        <div
          style="
            font-size: 12px;
            color: var(--warn-soft-fg);
            margin-bottom: 10px;
            padding: 8px;
            background: var(--warn-soft-bg);
            border-radius: 8px;
          "
        >
          密码管理员可见，请勿使用你在其他地方用的密码
        </div>
        <label style="font-size: 12px; color: var(--mut-label)">旧密码</label>
        <input v-model="oldPw" type="password" style="width: 100%; margin: 4px 0 10px" id="pwOld" />
        <label style="font-size: 12px; color: var(--mut-label)">新密码（非空即可）</label>
        <input v-model="newPw" type="password" style="width: 100%; margin: 4px 0 10px" id="pwNew" />
        <div id="pwMsg" :style="{ color: msgCls === 'err' ? 'var(--err-soft-fg)' : 'var(--ok-soft-fg)', fontSize: '12px' }">
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
