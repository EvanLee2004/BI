<script setup lang="ts">
import '../styles/components/BUPage.css'
import { computed, onMounted, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import { fetchProductVersion } from '../api/client'
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
import KeyCustomersPanel from './KeyCustomersPanel.vue'
import ReceiptsCard from './ReceiptsCard.vue'
import DailyQuery from './DailyQuery.vue'
import LedgerTable from './LedgerTable.vue'
import BuNav from './BuNav.vue'
import TopBarActions from './TopBarActions.vue'

const store = useCockpitStore()
const productVer = ref('')
/** 2.2.9：本机日历日回落；3.7.4 顶栏优先业务「数据更新至」 */
const todayStr = ref('')
function localTodayYmd(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
const dataUpdatedAt = computed(() => {
  const built = String(
    (store.vm as { meta?: { built_at?: string }; built_at?: string } | null)?.meta?.built_at
      || (store.vm as { built_at?: string } | null)?.built_at
      || store.snapshotBuiltAt
      || '',
  )
  return built.slice(0, 10)
})
const topbarDataDate = computed(() => dataUpdatedAt.value || todayStr.value)
const topbarDataDateTitle = computed(() =>
  dataUpdatedAt.value
    ? `数据更新至 / 最近成功抓取 ${dataUpdatedAt.value}`
    : '数据更新至（尚无业务时间戳时显示本机今日）',
)

onMounted(async () => {
  todayStr.value = localTodayYmd()
  if (store.snapshotMode) {
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
        <img class="tb-logo" :src="logoUrl" alt="甲骨易" width="42" height="42" />
        <div class="tb-title"><b>{{ store.buName }}</b> 经营看板</div>
        <PeriodPicker />
      </div>
      <div class="tb-right">
        <span
          v-if="topbarDataDate"
          class="tb-today"
          :title="topbarDataDateTitle"
          data-testid="tb-today"
        >数据更新至 {{ topbarDataDate }}</span>
        <span v-if="productVer" class="tb-ver" :title="productVer">{{ productVer }}</span>
        <ThemeToggle />
        <TopBarActions />
      </div>
    </header>
    <BuNav :current="store.buName" :label="store.buNavLabel" :names="store.buNames" />
    <div class="wrap">
    <!-- 与整体页同序：二=筛选→双榜→柱图；三=重点客户下单情况追踪 -->
    <section class="sec"><span class="sec-n">一</span><span class="sec-t">基本情况</span></section>
    <KpiCards />
    <section class="sec"><span class="sec-n">二</span><span class="sec-t">下单与回款</span></section>
    <DailyQuery />
    <RankingsDual />
    <ReceiptsCard />
    <section class="sec"><span class="sec-n">三</span><span class="sec-t">重点客户下单情况追踪</span></section>
    <KeyCustomersPanel />
    <section class="sec"><span class="sec-n">四</span><span class="sec-t">经营利润</span></section>
    <div class="grid-2">
      <div class="grid-2-main">
        <TrendChart />
        <ExpenseSection />
      </div>
      <PLTable />
    </div>
    <section class="sec"><span class="sec-n">五</span><span class="sec-t">收入与毛利结构</span></section>
    <ProfitStructure />
    <section class="sec"><span class="sec-n">六</span><span class="sec-t">费用明细</span></section>
    <ExpenseHeatmap />
    <LedgerTable />
    </div>
  </div>
</template>

