<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import { fetchProductVersion, fetchSession } from '../api/client'
/** Vite base=/app/：import 进 assets，nginx 只长缓存 /app/assets/ */
import logoUrl from '../assets/logo.png'
import PeriodPicker from './PeriodPicker.vue'
import ThemeToggle from './ThemeToggle.vue'
import KpiCards from './KpiCards.vue'
import TrendChart from './TrendChart.vue'
import PLTable from './PLTable.vue'
import ExpenseSection from './ExpenseSection.vue'
import ExpenseHeatmap from './ExpenseHeatmap.vue'
import ProfitStructure from './ProfitStructure.vue'
import RankingsDual from './RankingsDual.vue'
import ReceiptsCard from './ReceiptsCard.vue'
import DailyQuery from './DailyQuery.vue'
import LedgerTable from './LedgerTable.vue'
import BuNav from './BuNav.vue'
import TopBarActions from './TopBarActions.vue'

const store = useCockpitStore()
const productVer = ref('')
/** 2.2.9：本机日历日，版本号左侧 */
const todayStr = ref('')
/**
 * 2.3.4：仅「有整体权限」才显示「← 整体」。
 * - 在线：session.can_main（整体账号 / 管理员）
 * - 快照：仍走 snapshotCanGoOverall（BU 专用包 / 空 cockpit 禁回）
 * 纯 BU 账号不渲染按钮，避免点进「无整体驾驶舱权限」空壳。
 * 默认 false：session 未回前不闪按钮。
 */
const canMain = ref(false)

const showOverallBack = computed(() => {
  if (store.snapshotMode) return store.snapshotCanGoOverall()
  return canMain.value
})

function localTodayYmd(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function goOverall(e?: Event) {
  // 双保险：无权限不导航（防脏 DOM / 手改 HTML）
  if (store.snapshotMode) {
    e?.preventDefault()
    if (!store.snapshotCanGoOverall()) return
    store.loadMain()
    return
  }
  if (!canMain.value) {
    e?.preventDefault()
  }
  // 有 can_main：走 href="/" 全页回整体
}

onMounted(async () => {
  todayStr.value = localTodayYmd()
  if (store.snapshotMode) {
    const sv = String(store.snapshotVersion || '').trim()
    productVer.value = sv ? (sv.startsWith('v') ? sv : 'v' + sv) : ''
    canMain.value = store.snapshotCanGoOverall()
    return
  }
  try {
    const sess = await fetchSession()
    canMain.value = !!(sess as { can_main?: boolean }).can_main
  } catch {
    canMain.value = false
  }
  try {
    const v = await fetchProductVersion()
    const num = String(v.version || '').trim()
    productVer.value = num ? 'v' + num : ''
  } catch {
    productVer.value = ''
  }
})
</script>
<template>
  <div>
    <div
      v-if="store.snapshotMode"
      class="snapshot-banner"
      role="status"
      data-testid="snapshot-banner"
    >
      静态快照 · 数据截至 {{ (store.snapshotBuiltAt || store.snapshotExportedAt || '').slice(0, 10) || '—' }}
      · 导出于 {{ store.snapshotExportedAt || '—' }}
      · {{ store.snapshotScopeLabel || 'BU' }}
      · v{{ store.snapshotVersion || '' }}
    </div>
    <header class="topbar">
      <div class="tb-left">
        <img class="tb-logo" :src="logoUrl" alt="甲骨易" width="28" height="28" />
        <a
          v-if="showOverallBack"
          class="bu-back"
          href="/"
          data-testid="bu-back-overall"
          @click="goOverall"
        >← 整体</a>
        <div class="tb-title"><b>{{ store.buName }}</b> 经营罗盘</div>
        <PeriodPicker />
      </div>
      <div class="tb-right">
        <span v-if="todayStr" class="tb-today" title="本机今日日期" data-testid="tb-today">{{ todayStr }}</span>
        <span v-if="productVer" class="tb-ver" :title="productVer">{{ productVer }}</span>
        <ThemeToggle />
        <TopBarActions />
      </div>
    </header>
    <BuNav :current="store.buName" :label="store.buNavLabel" :names="store.buNames" />
    <div class="wrap">
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
    <section class="sec"><span class="sec-n">五</span><span class="sec-t">费用明细</span></section>
    <ExpenseHeatmap />
    <LedgerTable />
    </div>
  </div>
</template>

<style scoped>
.snapshot-banner {
  background: linear-gradient(90deg, #1e3a5f, #0e7490);
  color: #e0f2fe;
  text-align: center;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
  border-bottom: 1px solid #0284c7;
  position: sticky;
  top: 0;
  z-index: 50;
}
.tb-today {
  font-size: 13px;
  font-weight: 600;
  color: var(--mut, #94a3b8);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  margin-right: 2px;
  white-space: nowrap;
}
</style>
