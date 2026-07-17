<script setup lang="ts">
/**
 * 按时间段查询：日期区间 + 与全局周期联动 + 查询打 /api/daily。
 * 查询结果与默认 RankingsDual 同用 dualRankBarOption（ECharts 双条），顺序/样子一致。
 */
import { computed, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import EchartsHost from './charts/EchartsHost.vue'
import { dualRankBarOption } from '../dual-rank-option'
import type { RankViewBlk } from '../types/vm'

const store = useCockpitStore()

const dailyMeta = computed(() => store.vm?.daily || { year: 0, default_start: '', default_end: '', year_key: '' })
const start = ref('')
const end = ref('')
const handEdit = ref(false)
const loading = ref(false)
const err = ref('')
const sumText = ref('')
const dual = ref<{ sales?: RankViewBlk; customer?: RankViewBlk } | null>(null)

function datesForPeriod(key: string): { s: string; e: string } {
  const v = store.vm?.rankings?.rankings_view?.[key]
  if (v?.start && v?.end) return { s: v.start, e: v.end }
  const y = dailyMeta.value.year || new Date().getFullYear()
  return { s: `${y}-01-01`, e: `${y}-12-31` }
}

function syncFromPeriod() {
  if (handEdit.value) return
  const se = datesForPeriod(store.period)
  start.value = se.s
  end.value = se.e
}

watch(
  () => store.period,
  () => {
    handEdit.value = false
    syncFromPeriod()
  },
  { immediate: true },
)

function onDateEdit() {
  handEdit.value = true
}

async function runQuery() {
  err.value = ''
  loading.value = true
  dual.value = null
  try {
    const u =
      '/api/daily?start=' +
      encodeURIComponent(start.value) +
      '&end=' +
      encodeURIComponent(end.value) +
      '&top=2000'
    const r = await fetch(u, { credentials: 'same-origin' })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error((d as { detail?: string }).detail || 'HTTP ' + r.status)
    }
    const d = await r.json()
    dual.value = d.dual_rankings || null
    const o = d.orders_disp || d.orders_total_disp || ''
    const rc = d.receipts_disp || d.receipts_total_disp || ''
    sumText.value =
      (start.value === end.value ? '只看 ' + start.value : start.value + ' ~ ' + end.value) +
      (o || rc ? ` · 下单 ${o || '—'} / 回款 ${rc || '—'}` : '')
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function restoreYear() {
  handEdit.value = false
  const yk = store.vm?.year_key || ''
  if (yk) store.setPeriod(yk)
  syncFromPeriod()
  dual.value = null
  sumText.value = ''
  err.value = ''
}

const sales = computed((): RankViewBlk | null => dual.value?.sales || null)
const customer = computed((): RankViewBlk | null => dual.value?.customer || null)

function chartH(blk: RankViewBlk | null): number {
  const opt = dualRankBarOption(blk || undefined)
  return typeof opt._chartH === 'number' ? opt._chartH : 480
}
</script>
<template>
  <SciFiPanel id="dailyPanel" title="按时间段查询" panel-class="daily-card">
    <div class="daily-row" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 4px 0 8px">
      <label>起 <input type="date" v-model="start" @change="onDateEdit" id="dailyS" /></label>
      <label>止 <input type="date" v-model="end" @change="onDateEdit" id="dailyE" /></label>
      <button type="button" class="mini" id="dailyGo" :disabled="loading" @click="runQuery">
        {{ loading ? '查询中…' : '查询' }}
      </button>
      <button type="button" class="ghost mini" id="dailyClose" @click="restoreYear">返回默认（年）</button>
      <span id="dailySum" class="muted" style="font-size: 12px">{{ sumText }}</span>
      <span v-if="err" style="color: var(--neg); font-size: 12px">{{ err }}</span>
    </div>
    <div v-if="dual" id="rkCustom" class="grid-2e dual-grid dual-rankings" :data-start="start" :data-end="end" data-daily="1">
      <SciFiPanel
        v-for="blk in [sales, customer]"
        :key="(blk?.dim || '') + 'd'"
        :data-dim="blk?.dim"
      >
        <template #header>
          <span>{{ blk?.title || '' }}</span>
          <span class="dual-legend">
            <span class="dual-leg dual-o">紫=下单</span>
            <span class="dual-leg dual-r">青=回款</span>
          </span>
        </template>
        <div v-if="!blk || blk.empty || !(blk.items && blk.items.length)" class="ev-empty">本期无数据</div>
        <div v-else>
          <div class="rank-chart-host" :style="{ height: chartH(blk) + 'px', minHeight: '420px' }">
            <EchartsHost :option="dualRankBarOption(blk)" />
          </div>
        </div>
      </SciFiPanel>
    </div>
  </SciFiPanel>
</template>
