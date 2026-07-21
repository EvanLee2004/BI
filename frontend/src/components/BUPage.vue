<script setup lang="ts">
import { onMounted, ref } from 'vue'
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
import ReceiptsCard from './ReceiptsCard.vue'
import DailyQuery from './DailyQuery.vue'
import LedgerTable from './LedgerTable.vue'
import BuNav from './BuNav.vue'
import TopBarActions from './TopBarActions.vue'

const store = useCockpitStore()
const productVer = ref('')
onMounted(async () => {
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
    <header class="topbar">
      <div class="tb-left">
        <img class="tb-logo" :src="logoUrl" alt="甲骨易" width="28" height="28" />
        <a class="bu-back" href="/">← 整体</a>
        <div class="tb-title"><b>{{ store.buName }}</b> 经营罗盘</div>
        <PeriodPicker />
      </div>
      <div class="tb-right">
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
