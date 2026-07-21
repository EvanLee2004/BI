<script setup lang="ts">
/**
 * 按时间段查询（B-01）：日期区间 + 与全局周期联动 + 查询打 /api/daily。
 * 查询结果写入 store（dailyDual），由下方 RankingsDual「原位」切换为区间双卡展示——
 * 本面板只保留查询控件与摘要，不再自渲染排名卡：回款情况总图不消失、版面不跳动。
 */
import { computed, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import type { RankViewBlk } from '../types/vm'

const store = useCockpitStore()

const dailyMeta = computed(() => store.vm?.daily || { year: 0, default_start: '', default_end: '', year_key: '' })
const start = ref('')
const end = ref('')
const handEdit = ref(false)
const loading = ref(false)
const err = ref('')
const sumText = ref('')

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
    const dual = (d.dual_rankings || null) as { sales?: RankViewBlk; customer?: RankViewBlk } | null
    store.setDaily(start.value, end.value, dual)
    const o = d.orders_disp || d.orders_total_disp || ''
    const rc = d.receipts_disp || d.receipts_total_disp || ''
    sumText.value =
      (start.value === end.value ? '仅 ' + start.value : start.value + ' ~ ' + end.value) +
      (o || rc ? ` · 下单 ${o || '—'} / 回款 ${rc || '—'}` : '')
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e)
    store.clearDaily()
  } finally {
    loading.value = false
  }
}

function restoreYear() {
  handEdit.value = false
  const yk = store.vm?.year_key || ''
  if (yk) store.setPeriod(yk)
  syncFromPeriod()
  store.clearDaily()
  sumText.value = ''
  err.value = ''
}

/** 任务书58·R-51：本月 = 当月 1 日～今天，并触发查询（只影响本板块） */
function setThisMonth() {
  const d = new Date()
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  const pad = (n: number) => (n < 10 ? `0${n}` : String(n))
  handEdit.value = true
  start.value = `${y}-${pad(m)}-01`
  end.value = `${y}-${pad(m)}-${pad(d.getDate())}`
  runQuery()
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
      <button type="button" class="ghost mini" id="dailyThisMonth" data-testid="daily-this-month" @click="setThisMonth">
        本月
      </button>
      <button type="button" class="ghost mini" id="dailyClose" @click="restoreYear">返回默认（年）</button>
      <span id="dailySum" class="muted" style="font-size: 12px">{{ sumText }}</span>
      <span v-if="err" style="color: var(--neg); font-size: 12px">{{ err }}</span>
    </div>
  </SciFiPanel>
</template>
