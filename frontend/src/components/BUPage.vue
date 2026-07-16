<script setup lang="ts">
import { useCockpitStore } from '../stores/cockpit'
import PeriodPicker from './PeriodPicker.vue'
import ThemeToggle from './ThemeToggle.vue'
import KpiCards from './KpiCards.vue'
import TrendChart from './TrendChart.vue'
import PLTable from './PLTable.vue'
import ExpenseSection from './ExpenseSection.vue'
import ExpenseTrend from './ExpenseTrend.vue'
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
    <KpiCards />
    <div class="grid-2">
      <div class="grid-2-main">
        <TrendChart />
        <ExpenseSection />
      </div>
      <PLTable />
    </div>
    <ExpenseTrend />
    <DailyQuery />
    <ReceiptsCard />
    <RankingsDual />
    <LedgerTable />
  </div>
</template>
