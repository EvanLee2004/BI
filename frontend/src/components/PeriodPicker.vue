<script setup lang="ts">
/**
 * 两段式周期选择（年/季/月/自定义区间）。
 * 2.3.4：自定义区间 = 起止月筛选（无 1-2月/2-3月… 快捷组合墙）；仅映射 store.vm.period_keys。
 */
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import {
  classifyPeriodKey,
  groupPeriodKeys,
  resolveCustomPeriodKey,
  type PeriodGrain,
} from '../utils/periodKeys'

const store = useCockpitStore()
const open = ref(false)
const grain = ref<PeriodGrain>('year')
const customFrom = ref(1)
const customTo = ref(1)
const rootEl = ref<HTMLElement | null>(null)

const keys = computed(() => (store.vm?.period_keys as string[]) || [])
const current = computed(() => store.period || store.vm?.year_key || '')

function yearOf(k: string): string {
  const m = k.match(/^(\d{4})年/)
  return m ? m[1] : ''
}

function monthNum(k: string): number | null {
  const m = k.match(/^\d{4}年(\d{1,2})月$/)
  return m ? parseInt(m[1], 10) : null
}

function parseCustom(k: string): { y: string; a: number; b: number } | null {
  const m = k.match(/^(\d{4})年(\d{1,2})-(\d{1,2})月$/)
  if (!m) return null
  return { y: m[1], a: parseInt(m[2], 10), b: parseInt(m[3], 10) }
}

const grouped = computed(() => groupPeriodKeys(keys.value))
const years = computed(() => grouped.value.year)
const quarters = computed(() => grouped.value.quarter)
const months = computed(() => grouped.value.month)
const customs = computed(() => grouped.value.custom)

/** 可选月份：来自单月 key + 区间 key 的端点（后端只生成有数据的月）。 */
const monthOptions = computed(() => {
  const set = new Set<number>()
  for (const k of months.value) {
    const n = monthNum(k)
    if (n) set.add(n)
  }
  for (const k of customs.value) {
    const c = parseCustom(k)
    if (c) {
      set.add(c.a)
      set.add(c.b)
    }
  }
  return [...set].sort((a, b) => a - b)
})

const customYear = computed(
  () =>
    yearOf(current.value) ||
    yearOf(years.value[0] || '') ||
    String(new Date().getFullYear()),
)

const customKey = computed(() =>
  resolveCustomPeriodKey(keys.value, customYear.value, customFrom.value, customTo.value),
)

/** 预览文案：起止对调时仍显示规范区间。 */
const customPreview = computed(() => {
  if (!customKey.value) return ''
  const a = Math.min(customFrom.value, customTo.value)
  const b = Math.max(customFrom.value, customTo.value)
  if (a === b) return `${customYear.value}年${a}月`
  return `${customYear.value}年${a}-${b}月`
})

function syncGrainFromCurrent() {
  const k = current.value
  if (!k) {
    grain.value = 'year'
    return
  }
  grain.value = classifyPeriodKey(k)
  const c = parseCustom(k)
  if (c) {
    customFrom.value = c.a
    customTo.value = c.b
  } else {
    const m = monthNum(k)
    if (m) {
      customFrom.value = m
      customTo.value = m
    }
  }
}

function pick(k: string) {
  if (!k || !keys.value.includes(k)) return
  store.setPeriod(k)
  open.value = false
}

function applyCustom() {
  if (customKey.value) pick(customKey.value)
}

function toggle() {
  open.value = !open.value
  if (open.value) syncGrainFromCurrent()
}

function onDoc(e: MouseEvent) {
  if (!open.value || !rootEl.value) return
  if (!rootEl.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('mousedown', onDoc))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDoc))
watch(current, () => {
  if (!open.value) syncGrainFromCurrent()
})

const displayLabel = computed(() => current.value || store.vm?.year_key || '选择周期')
import './period-picker.css'
</script>

<template>
  <div ref="rootEl" class="pp" data-testid="period-picker">
    <button type="button" class="pp-trigger toggle" :aria-expanded="open" @click="toggle">
      {{ displayLabel }}
      <span class="pp-caret" aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="pp-panel" role="dialog" aria-label="选择时间周期">
      <div class="pp-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          class="pp-tab"
          :class="{ on: grain === 'year' }"
          :aria-selected="grain === 'year'"
          @click="grain = 'year'"
        >
          年
        </button>
        <button
          type="button"
          role="tab"
          class="pp-tab"
          :class="{ on: grain === 'quarter' }"
          :aria-selected="grain === 'quarter'"
          @click="grain = 'quarter'"
        >
          季
        </button>
        <button
          type="button"
          role="tab"
          class="pp-tab"
          :class="{ on: grain === 'month' }"
          :aria-selected="grain === 'month'"
          @click="grain = 'month'"
        >
          月
        </button>
        <button
          type="button"
          role="tab"
          class="pp-tab"
          :class="{ on: grain === 'custom' }"
          :aria-selected="grain === 'custom'"
          @click="grain = 'custom'"
        >
          自定义区间
        </button>
      </div>

      <div v-if="grain === 'year'" class="pp-body" role="tabpanel">
        <button
          v-for="k in years"
          :key="k"
          type="button"
          class="pp-opt"
          :class="{ on: k === current }"
          @click="pick(k)"
        >
          {{ k }}
        </button>
        <p v-if="!years.length" class="pp-empty">无全年选项</p>
      </div>

      <div v-else-if="grain === 'quarter'" class="pp-body pp-grid-4" role="tabpanel">
        <button
          v-for="k in quarters"
          :key="k"
          type="button"
          class="pp-opt"
          :class="{ on: k === current }"
          @click="pick(k)"
        >
          {{ k.replace(/^\d{4}年/, '') }}
        </button>
        <p v-if="!quarters.length" class="pp-empty">无季度选项</p>
      </div>

      <div v-else-if="grain === 'month'" class="pp-body pp-grid-4" role="tabpanel">
        <button
          v-for="k in months"
          :key="k"
          type="button"
          class="pp-opt"
          :class="{ on: k === current }"
          @click="pick(k)"
        >
          {{ monthNum(k) }}月
        </button>
        <p v-if="!months.length" class="pp-empty">无单月选项</p>
      </div>

      <div v-else class="pp-body pp-custom" role="tabpanel" data-testid="period-custom-filter">
        <p class="pp-hint">按起止月份筛选（仅月粒度；起止相同=单月）</p>
        <div class="pp-custom-row">
          <label>
            起
            <select v-model.number="customFrom" class="pp-select" data-testid="period-from">
              <option v-for="m in monthOptions" :key="'f' + m" :value="m">{{ m }}月</option>
            </select>
          </label>
          <span class="pp-dash">—</span>
          <label>
            止
            <select v-model.number="customTo" class="pp-select" data-testid="period-to">
              <option v-for="m in monthOptions" :key="'t' + m" :value="m">{{ m }}月</option>
            </select>
          </label>
          <button
            type="button"
            class="pp-opt on pp-apply"
            data-testid="period-apply"
            :disabled="!customKey"
            @click="applyCustom"
          >
            应用
          </button>
        </div>
        <p v-if="!customKey" class="pp-empty">该起止组合不在可选周期中</p>
        <p v-else class="pp-preview">将选中：{{ customPreview }}</p>
      </div>
    </div>
  </div>
</template>
