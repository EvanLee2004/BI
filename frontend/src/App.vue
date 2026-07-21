<script setup lang="ts">
import { onMounted, computed, onErrorCaptured, ref } from 'vue'
import { onVueErrorCaptured } from './utils/frontendErrorReporter'
import { useCockpitStore } from './stores/cockpit'
import { fetchProductVersion } from './api/client'
/** Vite base=/app/：import 进 assets，nginx 只长缓存 /app/assets/ */
import logoUrl from './assets/logo.png'
import LoginView from './components/LoginView.vue'
import PeriodPicker from './components/PeriodPicker.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import KpiCards from './components/KpiCards.vue'
import TrendChart from './components/TrendChart.vue'
import PLTable from './components/PLTable.vue'
import ExpenseSection from './components/ExpenseSection.vue'
import ExpenseHeatmap from './components/ExpenseHeatmap.vue'
import ProfitStructure from './components/ProfitStructure.vue'
import RankingsDual from './components/RankingsDual.vue'
import ReceiptsCard from './components/ReceiptsCard.vue'
import DailyQuery from './components/DailyQuery.vue'
import LedgerTable from './components/LedgerTable.vue'
import BuNav from './components/BuNav.vue'
import BUPage from './components/BUPage.vue'
import TopBarActions from './components/TopBarActions.vue'

const store = useCockpitStore()
const productVer = ref('')
const isBuRoute = computed(() => {
  const m = location.pathname.match(/^\/bu\/(.+)/)
  return m ? decodeURIComponent(m[1]) : ''
})
/** 2.2.4·G：无数据空态提示（后端 empty_message） */
const emptyHint = computed(() => {
  const v = store.vm as { empty?: boolean; empty_message?: string } | null
  if (!v?.empty) return ''
  return v.empty_message || '暂无数据'
})

onErrorCaptured((err) => onVueErrorCaptured(err))

onMounted(async () => {
  // 注意：条件须拆开写，避免打包器把 === 与 || 折叠成 ==(a||b) 语义错误
  const path = location.pathname
  const onLogin = path === '/login'
  const onAdmin = path.startsWith('/admin')
  if (onLogin || onAdmin) return
  try {
    const v = await fetchProductVersion()
    const num = String(v.version || '').trim()
    productVer.value = num ? 'v' + num : ''
  } catch {
    productVer.value = ''
  }
  const bu = isBuRoute.value
  if (bu) await store.loadBu(bu)
  else await store.loadMain()
})
</script>

<template>
  <div v-if="store.error && store.error.includes('未登录')">
    <LoginView />
  </div>
  <div v-else-if="store.loading" class="wrap muted" style="padding:40px">加载中…</div>
  <div v-else-if="store.error" class="wrap" style="padding:40px;color:var(--neg)">{{ store.error }}</div>
  <BUPage v-else-if="store.scope === 'bu'" />
  <div v-else-if="store.vm" id="periodSync">
    <header class="topbar">
      <div class="tb-left">
        <img class="tb-logo" :src="logoUrl" alt="甲骨易" width="28" height="28" />
        <div class="tb-title"><b>甲骨易</b> 智能经营罗盘</div>
        <PeriodPicker />
      </div>
      <div class="tb-right">
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
