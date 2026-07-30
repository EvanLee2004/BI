<script setup lang="ts">
import './styles/components/App.css'
import { onMounted, computed, onErrorCaptured, ref, defineAsyncComponent } from 'vue'
import { onVueErrorCaptured } from './utils/frontendErrorReporter'
import { useCockpitStore } from './stores/cockpit'
import { fetchProductVersion, fetchSession } from './api/client'
import {
  navigateToBuPath,
  shouldRedirectRootToBu,
  buPathFromSession,
  type SessionLike,
} from './utils/buEntryRedirect'
/** Vite base=/app/：import 进 assets，nginx 只长缓存 /app/assets/ */
import logoUrl from './assets/logo.png'
import LoginView from './components/LoginView.vue'
import PeriodPicker from './components/PeriodPicker.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import KpiCards from './components/KpiCards.vue'
import TrendChart from './components/TrendChart.vue'
import PLTable from './components/PLTable.vue'
import ExpenseSection from './components/ExpenseSection.vue'
import ProfitStructure from './components/ProfitStructure.vue'
import RankingsDual from './components/RankingsDual.vue'
import ReceiptsCard from './components/ReceiptsCard.vue'
import DailyQuery from './components/DailyQuery.vue'
import BuNav from './components/BuNav.vue'
import TopBarActions from './components/TopBarActions.vue'
import BuTransitionOverlay from './components/BuTransitionOverlay.vue'
import Toast from './components/base/Toast.vue'
import ErrorState from './components/base/ErrorState.vue'
/* 2.6.5：板块五台账/热力懒加载，压首屏 gz ≤90.8KB */
/* 3.4.1：重点客户在四底，async 分包不进首屏 boot gz */
const ExpenseHeatmap = defineAsyncComponent(() => import('./components/ExpenseHeatmap.vue'))
const LedgerTable = defineAsyncComponent(() => import('./components/LedgerTable.vue'))
const KeyCustomersPanel = defineAsyncComponent(() => import('./components/KeyCustomersPanel.vue'))
const BUPage = defineAsyncComponent(() => import('./components/BUPage.vue'))

const store = useCockpitStore()
const productVer = ref('')
/** 2.2.9：本机日历日，版本号左侧；不依赖后端 */
const todayStr = ref('')
const isBuRoute = computed(() => {
  const m = location.pathname.match(/^\/bu\/(.+)/)
  return m ? decodeURIComponent(m[1]) : ''
})
/** 2.2.4·G：空态提示（后端 empty_message） */
const emptyHint = computed(() => {
  const v = store.vm as { empty?: boolean; empty_message?: string } | null
  if (!v?.empty) return ''
  return v.empty_message || '暂无数据'
})
/** 3.5.0 / 3.6.0：数据完整性 VM 只读；老板看端中性展示 */
const dataIntegrity = computed(() => {
  const d = (store.vm as { data_integrity?: Record<string, unknown> } | null)?.data_integrity
  return d && (d.short_disp || d.headline || d.health_result) ? d : null
})
/** 中性「数据更新至」；不渲染英文 yellow / 橙色全宽条 */
const freshnessLine = computed(() => {
  const built = String(
    (store.vm as { meta?: { built_at?: string }; built_at?: string } | null)?.meta?.built_at
      || (store.vm as { built_at?: string } | null)?.built_at
      || store.snapshotBuiltAt
      || '',
  )
  const day = built.slice(0, 10)
  if (day) return `数据更新至 ${day}`
  return ''
})
const integrityHint = computed(() => {
  const d = dataIntegrity.value
  if (!d) return ''
  // 仅业务语言；过滤 technical yellow 字样
  const raw = String(d.headline || d.short_disp || '')
  if (!raw || /yellow/i.test(raw)) return ''
  return raw
})

/** 2.6.10 V-5：按状态码选错误块标题/出口（纯 BU 优先回自己的业务线） */
const errorPrimaryLabel = computed(() => {
  const st = store.errorStatus
  if (st === 403 || st === 404) {
    // 有 buName / 在 bu 作用域 → 回业务线；否则回整体
    if (store.scope === 'bu' || store.buName) return '回我的业务线'
    return '回整体页'
  }
  if (st === 503) return '刷新'
  return '重试'
})
const errorTitle = computed(() => {
  const st = store.errorStatus
  if (st === 403) return '没有权限'
  if (st === 404) return '页面不存在'
  if (st === 503) return '数据准备中'
  return '暂时打不开'
})

async function onErrorPrimary() {
  const st = store.errorStatus
  if (st === 403 || st === 404) {
    try {
      const sess = (await fetchSession()) as SessionLike
      const dest = buPathFromSession(sess)
      if (dest) {
        navigateToBuPath(dest)
        return
      }
    } catch {
      /* fall through */
    }
    // 有整体权限才回 /；纯 BU 无 dest 时也落到 / 让入口回流逻辑接管
    location.href = '/'
    return
  }
  await store.retryLoad()
}

function localTodayYmd(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

onErrorCaptured((err) => onVueErrorCaptured(err))

onMounted(async () => {
  todayStr.value = localTodayYmd()
  // 注意：条件须拆开写，避免打包器把 === 与 || 折叠成 ==(a||b) 语义错误
  const path = location.pathname
  const onLogin = path === '/login'
  const onAdmin = path.startsWith('/admin')
  if (onLogin || onAdmin) return

  // 2.2.9：导出快照优先 boot（零 API）
  if (store.tryBootSnapshot()) {
    const sv = String(store.snapshotVersion || '').trim()
    productVer.value = sv ? (sv.startsWith('v') ? sv : 'v' + sv) : ''
    return
  }

  try {
    const v = await fetchProductVersion()
    const num = String(v.version || '').trim()
    productVer.value = num ? 'v' + num : ''
  } catch {
    productVer.value = ''
  }

  // 2.4.3：根路径 + 纯 BU 会话 → 先跳 /bu/xxx，禁止无脑 loadMain 打 cockpit 403 空壳
  const bu = isBuRoute.value
  if (!bu && (path === '/' || path === '')) {
    try {
      const sess = (await fetchSession()) as SessionLike
      const dest = shouldRedirectRootToBu(path || '/', sess)
      if (dest) {
        navigateToBuPath(dest)
        return
      }
    } catch {
      /* 未登录等：交给 loadMain → 401 跳登录 */
    }
  }

  if (bu) await store.loadBu(bu)
  else await store.loadMain()
})
</script>

<template>
  <BuTransitionOverlay />
  <Toast />
  <!-- 2.6.10 V-5：按 HTTP 401 状态进登录，不靠中文 detail 匹配 -->
  <div v-if="store.authRequired">
    <LoginView />
  </div>
  <div v-else-if="store.loading" class="wrap muted app-loading">加载中…</div>
  <ErrorState
    v-else-if="store.error || (!store.vm && !store.loading)"
    :title="errorTitle"
    :message="store.error || '暂时打不开，请稍后再试'"
    :primary-label="errorPrimaryLabel"
    @primary="onErrorPrimary"
  />
  <div
    v-else-if="store.scope === 'bu'"
    class="view-transition-host"
    :class="{ 'is-transitioning': store.viewTransitioning }"
  >
    <!-- :key 强制 BU→BU 重挂载，避免 KeyCustomersPanel 本地 itemsCache 串线 -->
    <BUPage :key="store.buName || 'bu'" />
  </div>
  <div
    v-else-if="store.vm"
    id="periodSync"
    class="view-transition-host"
    :class="{ 'is-transitioning': store.viewTransitioning }"
  >
    <div
      v-if="store.archiveMode"
      class="archive-banner"
      role="status"
      data-testid="archive-banner"
    >
      历史存档 · {{ store.archiveDay.slice(0, 4) }}-{{ store.archiveDay.slice(4, 6) }}-{{ store.archiveDay.slice(6) }} · 只读
      <span v-if="store.archiveBuiltAt" class="archive-meta">（存于 {{ store.archiveBuiltAt }}）</span>
    </div>
    <div
      v-if="store.snapshotMode"
      class="snapshot-banner"
      role="status"
      data-testid="snapshot-banner"
    >
      静态快照 · 数据截至 {{ (store.snapshotBuiltAt || store.snapshotExportedAt || '').slice(0, 10) || '—' }}
      · 导出于 {{ store.snapshotExportedAt || '—' }}
      · {{ store.snapshotScopeLabel || '整体' }}
      · v{{ store.snapshotVersion || '' }}
    </div>
    <header class="topbar">
      <div class="tb-left">
        <img class="tb-logo" :src="logoUrl" alt="甲骨易" width="28" height="28" />
        <div class="tb-title"><b>甲骨易</b> 经营看板</div>
        <PeriodPicker />
      </div>
      <div class="tb-right">
        <span v-if="todayStr" class="tb-today" title="本机今日日期" data-testid="tb-today">{{ todayStr }}</span>
        <span v-if="productVer" class="tb-ver" :title="productVer">{{ productVer }}</span>
        <ThemeToggle />
        <TopBarActions />
      </div>
    </header>
    <BuNav />
    <div class="wrap">
    <div v-if="emptyHint" class="muted" style="padding:16px 0;color:var(--mut)">
      {{ emptyHint }}
    </div>
    <!-- 3.6.0 G5：老板看端中性新鲜度，禁止橙色 technical yellow 全宽条；详情留给管理端 -->
    <div
      v-if="freshnessLine"
      class="data-freshness-strip"
      data-testid="data-freshness-strip"
      role="status"
    >{{ freshnessLine }}</div>
    <details
      v-if="integrityHint"
      class="data-integrity-details"
      data-testid="data-integrity-strip"
    >
      <summary>业务完整性提示</summary>
      <p class="data-integrity-details__body">{{ integrityHint }}</p>
    </details>
    <section class="sec"><span class="sec-n">一</span><span class="sec-t">基本情况</span></section>
    <KpiCards />
    <section class="sec"><span class="sec-n">二</span><span class="sec-t">经营利润</span></section>
    <div class="grid-2">
      <div class="grid-2-main">
        <TrendChart />
        <ExpenseSection />
      </div>
      <PLTable />
    </div>
    <section class="sec"><span class="sec-n">三</span><span class="sec-t">收入与毛利结构</span></section>
    <ProfitStructure />
    <section class="sec"><span class="sec-n">四</span><span class="sec-t">下单与回款</span></section>
    <DailyQuery />
    <ReceiptsCard />
    <RankingsDual />
    <KeyCustomersPanel />
    <section class="sec"><span class="sec-n">五</span><span class="sec-t">费用明细</span></section>
    <ExpenseHeatmap />
    <LedgerTable />
    </div>
  </div>
</template>

