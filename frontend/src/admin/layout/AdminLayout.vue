<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'

const route = useRoute()
const router = useRouter()

const health = ref<Record<string, unknown> | null>(null)
const healthOpen = ref(false)
const versionLabel = ref('v…')
const refreshing = ref(false)
const refreshMsg = ref('')
const exceptions = ref<Record<string, number>>({})
const formDirty = ref(0)
const budgetDirty = ref(0)

provide('adminDirty', {
  formDirty,
  budgetDirty,
  setFormDirty: (n: number) => {
    formDirty.value = n
  },
  setBudgetDirty: (n: number) => {
    budgetDirty.value = n
  },
  confirmLeave: async () => {
    const n = (formDirty.value || 0) + (budgetDirty.value || 0)
    if (!n) return true
    try {
      await ElMessageBox.confirm(`有 ${n} 项未保存的修改，确定离开？未保存将丢失。`, '未保存提示', {
        type: 'warning',
        confirmButtonText: '离开',
        cancelButtonText: '留下',
      })
      formDirty.value = 0
      budgetDirty.value = 0
      return true
    } catch {
      return false
    }
  },
})

provide('adminHealth', health)
provide('reloadDash', () => {
  /* ConsoleView iframe 自行监听 storage/event */
  window.dispatchEvent(new CustomEvent('admin-reload-dash'))
})
provide('refreshExceptions', loadExceptions)

const group = computed(() => (route.meta.group as string) || 'see')

const editTables = [
  { t: '收入明细', path: '/admin/edit/detail?table=收入明细' },
  { t: '下单', path: '/admin/edit/detail?table=下单' },
  { t: '回款', path: '/admin/edit/detail?table=回款' },
  { t: '内部译员', path: '/admin/edit/detail?table=内部译员' },
  { t: '费用明细', path: '/admin/edit/detail?table=费用明细' },
]

const reviewTabs = [
  { t: 'overview', label: '总览', path: '/admin/review/overview' },
  { t: 'ledger', label: '数据修正', path: '/admin/review/ledger' },
  { t: 'orderdept', label: '下单未填部门', path: '/admin/review/orderdept', badge: 'order_unfilled_dept' },
  { t: 'unclassified', label: '费用未分类（台账）', path: '/admin/review/unclassified', badge: 'expense_unclassified' },
  { t: 'history', label: '历史快照', path: '/admin/review/history' },
  { t: 'audit', label: '配置变更记录', path: '/admin/review/audit' },
]

async function confirmNav(path: string) {
  const n = (formDirty.value || 0) + (budgetDirty.value || 0)
  if (n) {
    try {
      await ElMessageBox.confirm(`有 ${n} 项未保存的修改，确定离开？`, '未保存提示', { type: 'warning' })
      formDirty.value = 0
      budgetDirty.value = 0
    } catch {
      return
    }
  }
  await router.push(path)
}

async function showGroup(g: string) {
  if (g === 'see') await confirmNav('/admin')
  else if (g === 'edit') await confirmNav('/admin/edit/detail?table=收入明细')
  else if (g === 'review') await confirmNav('/admin/review/overview')
  else if (g === 'cfg') await confirmNav('/admin/settings')
}

function pillClass(result: unknown) {
  if (result === '绿') return 'g'
  if (result === '红') return 'r'
  return 'y'
}

function shortReason(h: Record<string, unknown>) {
  const rr = ((h.run_reasons as string[]) || [])[0] || ''
  if (rr) return rr.length > 36 ? rr.slice(0, 36) + '…' : rr
  const w = ((h.warnings as string[]) || [])[0] || ''
  return w ? (w.length > 36 ? w.slice(0, 36) + '…' : w) : ''
}

const healthLabel = computed(() => {
  const h = health.value || {}
  const result = (h.result as string) || '?'
  let label = '体检 ' + result
  const nWarn = ((h.warnings as string[]) || []).length
  if (result && result !== '绿') {
    const s = shortReason(h)
    if (s) label += ' · ' + s
  } else if (nWarn) label += ' · ' + nWarn + '警'
  return label + ' ▾'
})

const fetchBanners = computed(() => ((health.value?.fetch_banners as { text?: string }[]) || []) as { text?: string }[])

const healthRunTime = computed(() => String(health.value?.run_time || '?'))
const healthResult = computed(() => String(health.value?.result || '?'))
const healthRunReasons = computed(() => (health.value?.run_reasons as string[]) || [])
const healthWarnings = computed(() => (health.value?.warnings as string[]) || [])
const healthSources = computed(() => (health.value?.sources as { name: string; rows: number }[]) || [])

async function loadHealth() {
  try {
    health.value = await jget('/api/health')
  } catch {
    /* ignore */
  }
}

async function loadExceptions() {
  try {
    exceptions.value = await jget('/api/exceptions')
  } catch {
    /* ignore */
  }
}

async function loadVersion() {
  try {
    const v = await jget<{ version?: string; stage?: string }>('/api/version')
    const num = 'v' + String(v.version || '?').split('-')[0]
    const stage = v.stage || ''
    versionLabel.value = num + (stage ? ' · ' + stage : '')
  } catch {
    versionLabel.value = '版本?'
  }
}

let refT0 = 0
async function doRefresh() {
  refreshing.value = true
  refreshMsg.value = '更新数据中…'
  refT0 = Date.now()
  try {
    await jpost('/api/refresh', {})
  } catch {
    /* 409 已在更新 → 轮询 */
  }
  pollRefresh()
}

async function pollRefresh() {
  try {
    const s = await jget<{ running?: boolean; last?: { status?: string; detail?: string; seconds?: number }; zhiyun_auto_fetch?: boolean }>(
      '/api/refresh_status',
    )
    if (s.running) {
      const el = Math.round((Date.now() - refT0) / 1000)
      refreshMsg.value = '更新数据中… ' + el + 's' + (s.zhiyun_auto_fetch ? '（含智云在线抓数，约1~2分钟）' : '')
      setTimeout(pollRefresh, 2000)
      return
    }
    refreshing.value = false
    const L = s.last
    if (L && L.status === 'error') {
      refreshMsg.value = '更新失败：' + (L.detail || '')
      ElMessage.error(refreshMsg.value)
    } else {
      await loadHealth()
      await loadExceptions()
      const h = health.value || {}
      const probs = [...((h.run_reasons as string[]) || []), ...((h.warnings as string[]) || [])]
      const secs = L?.seconds ? `（${L.seconds}s）` : ''
      if (h.result === '绿' && !probs.length) {
        refreshMsg.value = '更新成功' + secs
        ElMessage.success('✓ ' + refreshMsg.value)
      } else {
        refreshMsg.value = '更新完成，但有问题' + secs
        ElMessage.warning(refreshMsg.value)
      }
      window.dispatchEvent(new CustomEvent('admin-reload-dash'))
    }
  } catch (e) {
    refreshing.value = false
    refreshMsg.value = '查询更新状态失败:' + String(e)
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
  window.dispatchEvent(
    new CustomEvent('admin-theme', { detail: { theme: light ? 'light' : 'dark' } }),
  )
}

const isLight = ref(false)
function syncThemeFlag() {
  isLight.value = document.documentElement.classList.contains('theme-light')
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if ((formDirty.value || 0) + (budgetDirty.value || 0) > 0) {
    e.preventDefault()
    e.returnValue = ''
  }
}

let healthTimer: number | undefined
onMounted(async () => {
  syncThemeFlag()
  await loadHealth()
  await loadExceptions()
  await loadVersion()
  healthTimer = window.setInterval(loadHealth, 30000)
  window.addEventListener('beforeunload', onBeforeUnload)
  try {
    const s = await jget<{ running?: boolean }>('/api/refresh_status')
    if (s.running) {
      refreshing.value = true
      refT0 = Date.now()
      pollRefresh()
    }
  } catch {
    /* ignore */
  }
})
onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
  window.removeEventListener('beforeunload', onBeforeUnload)
})

function badgeN(key?: string) {
  if (!key) return 0
  return exceptions.value[key] || 0
}

const curTable = computed(() => {
  if (!route.path.includes('/edit/detail')) return ''
  return (route.query.table as string) || '收入明细'
})
</script>

<template>
  <div class="admin-shell">
    <header class="admin-bar">
      <b>管理员控制台</b>
      <span class="ver-pill" title="版本" @click="showGroup('cfg')">{{ versionLabel }}</span>
      <span class="admin-pill" :class="pillClass(health?.result)" @click="healthOpen = !healthOpen">{{ healthLabel }}</span>
      <el-button type="primary" :loading="refreshing" @click="doRefresh">{{ refreshing ? '更新中…' : '更新数据' }}</el-button>
      <span class="muted">{{ refreshMsg }}</span>
      <span style="margin-left: auto" />
      <el-button text @click="toggleTheme">{{ isLight ? '◐ 深色' : '◑ 浅色' }}</el-button>
      <a class="logout" href="/admin/logout">退出</a>
    </header>

    <div v-if="healthOpen && health" class="health-pop">
      <h4>体检明细 · 运行 {{ healthRunTime }}</h4>
      <div class="grp">
        <div class="k">① 管道运行：{{ healthResult }}</div>
        <ul v-if="healthRunReasons.length">
          <li v-for="(r, i) in healthRunReasons" :key="i">{{ r }}</li>
        </ul>
        <div v-else class="ok">✓ 运行正常（fetch/调整无异常）</div>
      </div>
      <div class="grp">
        <div class="k">② 数据体检：{{ healthWarnings.length ? healthWarnings.length + ' 警' : '无' }}</div>
        <ul v-if="healthWarnings.length">
          <li v-for="(w, i) in healthWarnings" :key="i">{{ w }}</li>
        </ul>
        <div v-else class="ok">✓ 无数据质量告警</div>
      </div>
      <div class="grp">
        <div class="k">数据源覆盖</div>
        <div>
          <span v-for="(s, i) in healthSources" :key="i">
            {{ s.name }}：{{ s.rows }}行　
          </span>
        </div>
      </div>
    </div>

    <div v-if="fetchBanners.length" class="admin-fetch-banner" role="status">
      <div v-for="(b, i) in fetchBanners" :key="i" class="fb-line">{{ b.text }}</div>
    </div>

    <nav class="admin-groups">
      <div class="gtab" :class="{ on: group === 'see' }" @click="showGroup('see')">看</div>
      <div class="gtab" :class="{ on: group === 'edit' }" @click="showGroup('edit')">数据调整</div>
      <div class="gtab" :class="{ on: group === 'review' }" @click="showGroup('review')">异常处理</div>
      <div class="gtab" :class="{ on: group === 'cfg' }" @click="showGroup('cfg')">设置</div>
    </nav>

    <div v-if="group === 'edit'" class="admin-subnav">
      <el-button
        v-for="it in editTables"
        :key="it.t"
        size="small"
        :type="curTable === it.t ? 'primary' : 'default'"
        round
        @click="confirmNav(it.path)"
      >{{ it.t }}</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" :type="route.path.includes('/manual') ? 'primary' : 'default'" round @click="confirmNav('/admin/edit/manual')">人工填写</el-button>
      <el-button size="small" :type="route.path.includes('/budget') ? 'primary' : 'default'" round @click="confirmNav('/admin/edit/budget')">业绩目标</el-button>
    </div>

    <div v-if="group === 'review'" class="admin-subnav">
      <el-button
        v-for="it in reviewTabs"
        :key="it.t"
        size="small"
        :type="route.path.includes(it.t) || (it.t === 'overview' && route.path.endsWith('/overview')) ? 'primary' : 'default'"
        round
        @click="confirmNav(it.path)"
      >
        {{ it.label }}
        <el-badge v-if="it.badge" :value="badgeN(it.badge)" :hidden="!badgeN(it.badge)" :type="badgeN(it.badge) ? 'danger' : 'success'" class="nav-badge" />
      </el-button>
    </div>

    <main class="admin-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.admin-shell { min-height: 100vh; }
.admin-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  background: rgba(21, 30, 48, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--admin-line, #2a364d);
  position: sticky;
  top: 0;
  z-index: 40;
}
html.theme-light .admin-bar { background: rgba(255, 255, 255, 0.92); }
.admin-bar b { font-size: 15px; }
.ver-pill {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 8px;
  border: 1px solid var(--admin-line, #2a364d);
  color: var(--admin-mut, #8b9bb4);
  cursor: pointer;
}
.muted { color: var(--admin-mut, #8b9bb4); font-size: 13px; }
.logout { color: var(--admin-mut, #8b9bb4); text-decoration: none; font-size: 13px; padding: 6px 10px; }
.logout:hover { color: var(--admin-fg, #e8eef9); }
.admin-groups {
  display: flex;
  gap: 4px;
  padding: 10px 16px 0;
}
.gtab {
  padding: 9px 18px;
  border-radius: 10px 10px 0 0;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  color: var(--admin-mut, #8b9bb4);
  border: 1px solid transparent;
  border-bottom: none;
}
.gtab.on {
  background: var(--admin-panel, #151e30);
  color: var(--admin-fg, #e8eef9);
  border-color: var(--admin-line, #2a364d);
}
.admin-subnav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 10px 16px;
  background: rgba(15, 22, 36, 0.65);
  border-bottom: 1px solid var(--admin-line, #2a364d);
}
.admin-main { padding: 16px 20px 28px; }
.health-pop {
  position: absolute;
  top: 52px;
  left: 14px;
  z-index: 50;
  max-width: 560px;
  background: var(--admin-panel, #151e30);
  border: 1px solid var(--admin-line, #2a364d);
  border-radius: 12px;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.6;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
}
.health-pop h4 { margin: 0 0 4px; font-size: 13px; }
.health-pop .grp { margin-top: 10px; }
.health-pop .k { color: var(--admin-mut); font-weight: 600; }
.health-pop .ok { color: #16a34a; }
.nav-badge { margin-left: 6px; }
</style>
