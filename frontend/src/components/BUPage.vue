<script setup lang="ts">
import { useCockpitStore } from '../stores/cockpit'
import PeriodPicker from './PeriodPicker.vue'
import ThemeToggle from './ThemeToggle.vue'
import KpiCards from './KpiCards.vue'
import TrendChart from './TrendChart.vue'
import PLTable from './PLTable.vue'
import ExpenseSection from './ExpenseSection.vue'
import ExpenseTrend from './ExpenseTrend.vue'
import ProfitStructure from './ProfitStructure.vue'
import RankingsDual from './RankingsDual.vue'
import ReceiptsCard from './ReceiptsCard.vue'
import DailyQuery from './DailyQuery.vue'
import LedgerTable from './LedgerTable.vue'

const store = useCockpitStore()
</script>
<template>
  <div class="wrap">
    <header class="topbar">
      <a class="bu-back" href="/">← 整体</a>
      <div class="tb-title"><b>{{ store.buName }}</b> 经营罗盘</div>
      <div class="tb-right">
        <PeriodPicker />
        <ThemeToggle />
      </div>
    </header>
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
    <ExpenseTrend />
    <section class="sec"><span class="sec-n">三</span><span class="sec-t">收入与毛利结构</span></section>
    <ProfitStructure />
    <section class="sec"><span class="sec-n">四</span><span class="sec-t">下单与回款</span></section>
    <DailyQuery />
    <ReceiptsCard />
    <RankingsDual />
    <section class="sec"><span class="sec-n">五</span><span class="sec-t">费用明细</span></section>
    <LedgerTable />
  </div>
</template>
