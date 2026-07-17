<script setup lang="ts">
/**
 * 按时间段查询：日期区间 + 与全局周期联动 + 查询打 /api/daily。
 * 年/季/月切换 → 起止日自动跟随；手改日期不反向改周期。
 */
import { computed, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
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

function pct(v: unknown): string {
  const n = v == null ? 0 : Number(v)
  return (Number.isFinite(n) ? n : 0).toFixed(1)
}

const sales = computed((): RankViewBlk | null => dual.value?.sales || null)
const customer = computed((): RankViewBlk | null => dual.value?.customer || null)
</script>
<template>
  <div class="card daily-card" id="dailyPanel">
    <div class="card-h">按时间段查询</div>
    <div class="daily-row" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 8px 12px">
      <label>起 <input type="date" v-model="start" @change="onDateEdit" id="dailyS" /></label>
      <label>止 <input type="date" v-model="end" @change="onDateEdit" id="dailyE" /></label>
      <button type="button" class="mini" id="dailyGo" :disabled="loading" @click="runQuery">
        {{ loading ? '查询中…' : '查询' }}
      </button>
      <button type="button" class="ghost mini" id="dailyClose" @click="restoreYear">返回默认（年）</button>
      <span id="dailySum" class="muted" style="font-size: 12px">{{ sumText }}</span>
      <span v-if="err" style="color: var(--neg); font-size: 12px">{{ err }}</span>
    </div>
    <div v-if="dual" id="rkCustom" class="grid-2e dual-grid" :data-start="start" :data-end="end" data-daily="1">
      <div v-for="blk in [sales, customer]" :key="(blk?.dim || '') + 'd'" class="card" :data-dim="blk?.dim">
        <div class="card-h">{{ blk?.title }}</div>
        <div v-if="!blk || blk.empty || !(blk.items && blk.items.length)" class="ev-empty">本期无数据</div>
        <div v-else class="ev-list rk-list">
          <div v-for="it in blk.items" :key="it.i + it.name" class="ev-row dual-row">
            <span class="rk-no">{{ it.i }}</span>
            <span class="ev-name" :title="it.name">{{ it.name }}</span>
            <div class="dual-bars">
              <span class="dual-bar dual-o"
                ><i :style="{ width: pct(it.wo) + '%' }"></i><em>{{ it.order_disp }}</em></span
              >
              <span class="dual-bar dual-r"
                ><i :style="{ width: pct(it.wr) + '%' }"></i><em>{{ it.receipt_disp }}</em></span
              >
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
