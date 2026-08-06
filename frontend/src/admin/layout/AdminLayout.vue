<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, provide, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost, AdminApiError } from '../api'
import { syncThemeFromDom } from '../../utils/theme'
import {
  buildLastUpdatePillLabel,
  buildLastUpdatePillTitle,
  pickLastUpdateRaw,
} from '../utils/lastUpdateLabel'

const route = useRoute()
const router = useRouter()

/** 3.7.5：一级组/页切换时 skeleton + 禁止误操作旧页；失败可重试 */
const pageLoading = ref(false)
const pageError = ref('')
const pageRetryPath = ref('')
let removeNavGuards: (() => void) | null = null

const health = ref<Record<string, unknown> | null>(null)
const healthOpen = ref(false)
const healthPopEl = ref<HTMLElement | null>(null)
const healthPillEl = ref<HTMLElement | null>(null)
const versionLabel = ref('v…')
const refreshing = ref(false)
const refreshMsg = ref('')
const exceptions = ref<Record<string, number>>({})
/** 3.7.4：异常接口失败不得静默清零徽标 */
const exceptionsLoadError = ref(false)
const formDirty = ref(0)
const budgetDirty = ref(0)

/** 2.6.6·T1/T2：展开详情；滚动/点外/Esc 收起，避免挡数据
 * 注意：scroll 事件不冒泡，window 监听收不到 .admin-main 内滚 → 用 wheel/touchmove + 挂接可滚容器。
 */
const healthScrollEls: EventTarget[] = []
function closeHealthPop() {
  healthOpen.value = false
  detachHealthScrollTargets()
}
function onHealthUserScroll() {
  if (!healthOpen.value) return
  closeHealthPop()
}
function detachHealthScrollTargets() {
  for (const el of healthScrollEls) {
    el.removeEventListener('scroll', onHealthUserScroll)
  }
  healthScrollEls.length = 0
}
function attachHealthScrollTargets() {
  detachHealthScrollTargets()
  const candidates: (Element | Window | Document | null)[] = [
    window,
    document,
    document.documentElement,
    document.body,
    document.querySelector('.admin-main'),
    document.querySelector('.admin-shell'),
    document.querySelector('.el-main'),
  ]
  for (const el of candidates) {
    if (!el) continue
    el.addEventListener('scroll', onHealthUserScroll, { passive: true })
    healthScrollEls.push(el)
  }
}
function toggleHealthPop() {
  healthOpen.value = !healthOpen.value
  if (healthOpen.value) {
    // 下一帧再挂，确保 DOM 已出
    requestAnimationFrame(() => attachHealthScrollTargets())
  } else {
    detachHealthScrollTargets()
  }
}
/** 3.3.2：页面外滚/触控收起浮层；浮层内部滚动不关（可读完多条告警） */
function onHealthWheelOrTouch(ev?: Event) {
  if (!healthOpen.value) return
  const t = (ev?.target as Node | null) || null
  // 浮层内部 → 不关闭，允许 max-height 内滚读完
  if (t && healthPopEl.value?.contains(t)) return
  closeHealthPop()
}
function onHealthPointerDown(ev: MouseEvent) {
  if (!healthOpen.value) return
  const t = ev.target as Node | null
  if (!t) return
  if (healthPopEl.value?.contains(t)) return
  if (healthPillEl.value?.contains(t)) return
  closeHealthPop()
}
function onHealthKey(ev: KeyboardEvent) {
  if (ev.key === 'Escape' && healthOpen.value) {
    ev.preventDefault()
    closeHealthPop()
  }
}

type BusinessGaps = {
  manual_missing_months?: string[]
  manual_missing_count?: number
  manual_impact?: string
  manual_owner?: string
  unassigned_count?: number
  unassigned_impact?: string
  unassigned_owner?: string
  /** 2.6.8 T1：台账共享不可达，费用沿用本地副本 */
  ledger_fallback?: boolean
  ledger_fallback_as_of?: string
  ledger_fallback_data_end?: string
  ledger_fallback_text?: string
  ledger_fallback_owner?: string
}
const businessGaps = computed(() => (health.value?.business_gaps as BusinessGaps) || null)
const hasBusinessGaps = computed(() => {
  const g = businessGaps.value
  if (!g) return false
  return !!(g.manual_missing_count || g.unassigned_count || g.ledger_fallback)
})

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
  /* 3.7.2：下单未填部门已下线；保留费用未分类 */
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
  else if (g === 'users') await confirmNav('/admin/users')
  else if (g === 'cfg') await confirmNav('/admin/settings')
}

function beginPageLoad(toPath: string) {
  pageLoading.value = true
  pageError.value = ''
  pageRetryPath.value = toPath
}

function endPageLoad() {
  pageLoading.value = false
}

async function retryPageLoad() {
  const p = pageRetryPath.value || route.fullPath
  pageError.value = ''
  beginPageLoad(p)
  try {
    await router.replace(p)
    await nextTick()
    endPageLoad()
  } catch (e) {
    pageError.value = '页面加载失败，请重试'
    pageLoading.value = false
  }
}

function pillClass(result: unknown) {
  if (result === '绿') return 'g'
  if (result === '红') return 'r'
  return 'y'
}

/** 3.7.18：顶栏只显示「上次更新」；管道原因/告警仅在浮层 */
const healthLabel = computed(() => buildLastUpdatePillLabel(health.value || {}))
const healthPillTitle = computed(() => buildLastUpdatePillTitle(health.value || {}))
const healthLastUpdate = computed(() => pickLastUpdateRaw(health.value || {}) || '—')

const fetchBanners = computed(() => ((health.value?.fetch_banners as { text?: string }[]) || []) as { text?: string }[])

const healthRunTime = computed(() => String(health.value?.run_time || '?'))
const healthResult = computed(() => String(health.value?.result || '?'))
const healthRunReasons = computed(() => (health.value?.run_reasons as string[]) || [])
const healthWarnings = computed(() => (health.value?.warnings as string[]) || [])
const healthSources = computed(() => (health.value?.sources as { name: string; rows: number }[]) || [])

async function loadHealth() {
  try {
    health.value = await jget('/api/v1/health')
  } catch {
    /* ignore */
  }
}

async function loadExceptions() {
  try {
    exceptions.value = await jget('/api/v1/admin/exceptions')
    exceptionsLoadError.value = false
  } catch {
    exceptionsLoadError.value = true
    // 不把 exceptions 清成 {}，避免徽标静默消失；保留上次成功计数
  }
}

async function loadVersion() {
  try {
    const v = await jget<{ version?: string; stage?: string }>('/api/v1/version')
    const num = 'v' + String(v.version || '?').split('-')[0]
    const stage = v.stage || ''
    versionLabel.value = num + (stage ? ' · ' + stage : '')
  } catch {
    versionLabel.value = '版本?'
  }
}

type RefreshLast = {
  status?: string
  detail?: string
  seconds?: number
  finished_at?: string
}
type RefreshStatus = {
  running?: boolean
  last?: RefreshLast | null
  zhiyun_auto_fetch?: boolean
}

let refT0 = 0
/** 本次点击会话：POST 前 last.finished_at；未推进则禁止「更新完成（旧秒数）」 */
let baselineFinishedAt: string | null = null
/** 同一 finished_at 只 toast 一次，防连点堆叠 */
let lastToastedFinishedAt: string | null = null

function failBusyMsg() {
  return '暂时无法启动更新（系统忙）。请稍后重试；若连续出现请运维 restart kanban'
}

async function captureBaselineFinishedAt(): Promise<string | null> {
  try {
    const pre = await jget<RefreshStatus>('/api/v1/admin/refresh_status')
    return pre.last?.finished_at ?? null
  } catch {
    return null
  }
}

/** finished_at 相对 baseline 已推进（或 baseline 空且 last 有 finished_at） */
function finishedAtAdvanced(last: RefreshLast | null | undefined, baseline: string | null): boolean {
  if (!last || !last.finished_at) return false
  if (!baseline) return true
  return last.finished_at !== baseline
}

async function doRefresh() {
  // 连点：已在更新会话中则忽略
  if (refreshing.value) return

  baselineFinishedAt = await captureBaselineFinishedAt()
  refreshing.value = true
  refreshMsg.value = '更新数据中…'
  refT0 = Date.now()

  try {
    await jpost('/api/v1/admin/refresh', {})
    // 200 started → 轮询
    pollRefresh()
  } catch (e) {
    if (e instanceof AdminApiError && e.status === 409) {
      try {
        const s = await jget<RefreshStatus>('/api/v1/admin/refresh_status')
        if (s.running) {
          refreshMsg.value = '更新进行中，已跟进进度'
          ElMessage.info(refreshMsg.value)
          pollRefresh()
          return
        }
        // 409 且 running false：锁忙但无刷新会话 → 明确失败，禁止假完成
        refreshing.value = false
        refreshMsg.value = failBusyMsg()
        ElMessage.error(refreshMsg.value)
        return
      } catch {
        refreshing.value = false
        refreshMsg.value = failBusyMsg()
        ElMessage.error(refreshMsg.value)
        return
      }
    }
    // 其它 4xx/5xx/网络：真实错误，绝不 toast 完成
    refreshing.value = false
    const msg = e instanceof AdminApiError ? e.message : e instanceof Error ? e.message : String(e)
    refreshMsg.value = '更新启动失败：' + msg
    ElMessage.error(refreshMsg.value)
  }
}

async function pollRefresh() {
  try {
    const s = await jget<RefreshStatus>('/api/v1/admin/refresh_status')
    if (s.running) {
      const el = Math.round((Date.now() - refT0) / 1000)
      refreshMsg.value =
        '更新数据中… ' + el + 's' + (s.zhiyun_auto_fetch ? '（含智云在线抓数，约1~2分钟）' : '')
      setTimeout(pollRefresh, 2000)
      return
    }
    refreshing.value = false
    const L = s.last

    // 未观察到新一次 finish → 禁止用旧 last.seconds 弹「更新完成」
    if (!finishedAtAdvanced(L, baselineFinishedAt)) {
      refreshMsg.value = '未能确认新一次更新已执行'
      ElMessage.warning(refreshMsg.value)
      return
    }

    // 同一 finished_at 只 toast 一次
    const fin = L?.finished_at || null
    if (fin && fin === lastToastedFinishedAt) {
      return
    }
    lastToastedFinishedAt = fin

    if (L && L.status === 'error') {
      refreshMsg.value = '更新失败：' + (L.detail || '')
      ElMessage.error(refreshMsg.value)
      return
    }

    await loadHealth()
    await loadExceptions()
    const h = health.value || {}
    const probs = [...((h.run_reasons as string[]) || []), ...((h.warnings as string[]) || [])]
    const secs = L?.seconds != null && L.seconds !== undefined ? `（${L.seconds}s）` : ''
    if (h.result === '绿' && !probs.length) {
      refreshMsg.value = '更新成功' + secs
      ElMessage.success('✓ ' + refreshMsg.value)
    } else {
      refreshMsg.value = '更新完成' + secs
      ElMessage.warning(refreshMsg.value)
    }
    window.dispatchEvent(new CustomEvent('admin-reload-dash'))
  } catch (e) {
    refreshing.value = false
    refreshMsg.value = '查询更新状态失败:' + String(e)
  }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if ((formDirty.value || 0) + (budgetDirty.value || 0) > 0) {
    e.preventDefault()
    e.returnValue = ''
  }
}

let healthTimer: number | undefined
onMounted(async () => {
  // 2.2.7：管理壳固定深色（去掉顶栏浅色开关）；展示 iframe 内 ThemeToggle 仍可用
  syncThemeFromDom()
  // 3.7.5：切组/切页 loading；失败可重试
  const unBefore = router.beforeEach((to, from) => {
    if (!to.path.startsWith('/admin')) return true
    if (to.fullPath === from.fullPath) return true
    beginPageLoad(to.fullPath)
    return true
  })
  const unAfter = router.afterEach((to) => {
    if (!to.path.startsWith('/admin')) return
    // 下一帧结束 loading，确保异步组件有时间挂起
    nextTick(() => {
      endPageLoad()
    })
  })
  const unErr = router.onError(() => {
    pageError.value = '页面加载失败，请重试'
    pageLoading.value = false
  })
  removeNavGuards = () => {
    unBefore()
    unAfter()
    unErr()
  }
  await loadHealth()
  await loadExceptions()
  await loadVersion()
  healthTimer = window.setInterval(loadHealth, 30000)
  window.addEventListener('beforeunload', onBeforeUnload)
  // scroll 不冒泡：用 wheel/touchmove 捕获「用户在滚」；另在 open 时挂 .admin-main
  window.addEventListener('wheel', onHealthWheelOrTouch, { passive: true, capture: true })
  window.addEventListener('touchmove', onHealthWheelOrTouch, { passive: true, capture: true })
  document.addEventListener('pointerdown', onHealthPointerDown, true)
  window.addEventListener('keydown', onHealthKey)
  try {
    const s = await jget<RefreshStatus>('/api/v1/admin/refresh_status')
    if (s.running) {
      // 恢复中途刷新：baseline=当前 last，等新 finished_at 推进后再诚实完成
      baselineFinishedAt = s.last?.finished_at ?? null
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
  removeNavGuards?.()
  removeNavGuards = null
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('wheel', onHealthWheelOrTouch, true)
  window.removeEventListener('touchmove', onHealthWheelOrTouch, true)
  document.removeEventListener('pointerdown', onHealthPointerDown, true)
  window.removeEventListener('keydown', onHealthKey)
  detachHealthScrollTargets()
})

function badgeN(key?: string) {
  if (!key) return 0
  return exceptions.value[key] || 0
}

/** 异常分组徽标：加载失败显示 !，真实 0 才隐藏 success 绿点 */
const reviewBadgeText = computed(() => {
  if (exceptionsLoadError.value) return '!'
  const keys = ['expense_unclassified', 'adjust_expired', 'adjust_missing']
  const n = keys.reduce((s, k) => s + (exceptions.value[k] || 0), 0)
  return n > 0 ? String(n) : ''
})

const curTable = computed(() => {
  if (!route.path.includes('/edit/detail')) return ''
  return (route.query.table as string) || '收入明细'
})
import './admin-layout.css'
</script>

<template>
  <div class="admin-shell">
    <!-- 2.6.7 B-7：红色系统告警横幅已下线；告警仍写 数据/日志/告警.log，体检黄条保留 -->
    <header class="admin-bar">
      <b>管理员控制台</b>
      <span class="ver-pill" title="版本" @click="showGroup('cfg')">{{ versionLabel }}</span>
      <span
        ref="healthPillEl"
        class="admin-pill"
        data-testid="admin-health-pill"
        :class="pillClass(health?.result)"
        :title="healthPillTitle"
        role="button"
        :aria-expanded="healthOpen"
        @click="toggleHealthPop"
      >{{ healthLabel }}</span>
      <el-button type="primary" :loading="refreshing" @click="doRefresh">{{ refreshing ? '更新中…' : '更新数据' }}</el-button>
      <span class="muted">{{ refreshMsg }}</span>
      <span style="margin-left: auto" />
    </header>

    <div
      v-if="healthOpen && health"
      ref="healthPopEl"
      class="health-pop"
      data-testid="admin-health-pop"
      role="dialog"
      aria-label="体检明细"
    >
      <h4>体检明细 · 上次更新 {{ healthLastUpdate }}</h4>
      <p v-if="healthRunTime && healthRunTime !== '?'" class="muted" style="margin: 0 0 6px; font-size: 12px">
        管道运行时间：{{ healthRunTime }}
      </p>
      <p class="health-pop-hint muted">页外滚动 / 点外部 / Esc 可收起；浮层内可滚读</p>
      <div class="grp" data-testid="health-gaps">
        <div class="k">⓪ 业务缺口（可展开）</div>
        <template v-if="businessGaps && hasBusinessGaps">
          <div v-if="businessGaps.ledger_fallback" class="gap-block" data-testid="health-gap-ledger-fallback">
            <b>费用台账沿用本地副本</b>
            <div class="gap-impact">{{ businessGaps.ledger_fallback_text || '收单台账共享不可达，费用按本地旧副本计算' }}</div>
            <div v-if="businessGaps.ledger_fallback_data_end" class="gap-impact">
              费用数据止于：{{ businessGaps.ledger_fallback_data_end }}
            </div>
            <div v-if="businessGaps.ledger_fallback_owner" class="gap-owner">建议：{{ businessGaps.ledger_fallback_owner }}</div>
          </div>
          <div v-if="businessGaps.manual_missing_count" class="gap-block" data-testid="health-gap-manual">
            <b>手填缺 {{ businessGaps.manual_missing_count }} 个月</b>
            <div>缺月：{{ (businessGaps.manual_missing_months || []).join('、') || '—' }}</div>
            <div v-if="businessGaps.manual_impact" class="gap-impact">{{ businessGaps.manual_impact }}</div>
            <div v-if="businessGaps.manual_owner" class="gap-owner">建议：{{ businessGaps.manual_owner }}</div>
          </div>
          <div v-if="businessGaps.unassigned_count" class="gap-block" data-testid="health-gap-unassigned">
            <b>未归属 BU 销售 {{ businessGaps.unassigned_count }} 人</b>
            <div v-if="businessGaps.unassigned_impact" class="gap-impact">{{ businessGaps.unassigned_impact }}</div>
            <div v-if="businessGaps.unassigned_owner" class="gap-owner">建议：{{ businessGaps.unassigned_owner }}</div>
          </div>
        </template>
        <div v-else class="ok">✓ 当前无结构化业务缺口（台账降级 / 手填缺月 / 未归属）</div>
      </div>
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
        <div v-else class="ok">✓ 暂无质量告警</div>
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

    <nav class="admin-groups" aria-label="管理端分组">
      <button
        type="button"
        class="gtab"
        :class="{ on: group === 'see' }"
        data-testid="nav-group-see"
        @click="showGroup('see')"
      >展示</button>
      <button
        type="button"
        class="gtab"
        :class="{ on: group === 'edit' }"
        data-testid="nav-group-edit"
        @click="showGroup('edit')"
      >数据调整</button>
      <button
        type="button"
        class="gtab"
        :class="{ on: group === 'review' }"
        data-testid="nav-group-review"
        @click="showGroup('review')"
      >
        异常处理
        <span
          v-if="reviewBadgeText"
          class="gtab-badge"
          data-testid="nav-exceptions-badge"
          :title="exceptionsLoadError ? '异常汇总加载失败' : '待处理异常'"
        >{{ reviewBadgeText }}</span>
      </button>
      <button
        type="button"
        class="gtab"
        data-testid="nav-user-stats"
        :class="{ on: group === 'users' }"
        @click="showGroup('users')"
      >用户统计</button>
      <button
        type="button"
        class="gtab"
        :class="{ on: group === 'cfg' }"
        data-testid="nav-group-cfg"
        @click="showGroup('cfg')"
      >设置</button>
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
      <el-button
        size="small"
        data-testid="nav-manual"
        :type="route.name === 'admin-manual' || route.path.includes('/edit/manual') ? 'primary' : 'default'"
        round
        @click="confirmNav('/admin/edit/manual')"
      >人工填写</el-button>
      <el-button
        size="small"
        data-testid="nav-budget"
        :type="route.name === 'admin-budget' || route.path.includes('/edit/budget') ? 'primary' : 'default'"
        round
        @click="confirmNav('/admin/edit/budget')"
      >业绩目标</el-button>
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
        <el-badge
          v-if="it.badge && exceptionsLoadError"
          value="!"
          type="warning"
          class="nav-badge"
          data-testid="subnav-exceptions-fail"
        />
        <el-badge
          v-else-if="it.badge"
          :value="badgeN(it.badge)"
          :hidden="!badgeN(it.badge)"
          :type="badgeN(it.badge) ? 'danger' : 'success'"
          class="nav-badge"
        />
      </el-button>
    </div>

    <main
      class="admin-main"
      :class="{ 'is-page-loading': pageLoading }"
      :aria-busy="pageLoading ? 'true' : 'false'"
      data-testid="admin-main"
    >
      <div
        v-if="pageLoading"
        class="admin-page-skeleton"
        data-testid="admin-page-loading"
        role="status"
        aria-live="polite"
      >
        <div class="sk-block sk-title" />
        <div class="sk-block sk-line" />
        <div class="sk-block sk-line short" />
        <div class="sk-block sk-card" />
        <span class="sk-label">加载中…</span>
      </div>
      <div
        v-else-if="pageError"
        class="admin-page-error"
        data-testid="admin-page-error"
        role="alert"
      >
        <p>{{ pageError }}</p>
        <button type="button" class="retry-btn" data-testid="admin-page-retry" @click="retryPageLoad">
          重试
        </button>
      </div>
      <div
        v-show="!pageLoading && !pageError"
        class="admin-page-body"
        data-testid="admin-page-body"
      >
        <RouterView v-slot="{ Component, route: r }">
          <component :is="Component" :key="r.fullPath" />
        </RouterView>
      </div>
    </main>
  </div>
</template>

