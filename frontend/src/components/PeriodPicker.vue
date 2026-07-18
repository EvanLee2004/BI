<script setup lang="ts">
/**
 * 54.11 R-02：两段式周期选择（年/季/月/自定义区间）。
 * 仅映射 store.vm.period_keys，不改后端枚举。
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

const customKey = computed(() => {
  const y =
    yearOf(current.value) ||
    yearOf(years.value[0] || '') ||
    String(new Date().getFullYear())
  return resolveCustomPeriodKey(keys.value, y, customFrom.value, customTo.value)
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

// 默认展示全年
const displayLabel = computed(() => current.value || store.vm?.year_key || '选择周期')
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

      <div v-else class="pp-body pp-custom" role="tabpanel">
        <div class="pp-custom-row">
          <label>
            起
            <select v-model.number="customFrom" class="pp-select">
              <option v-for="m in monthOptions" :key="'f' + m" :value="m">{{ m }}月</option>
            </select>
          </label>
          <span class="pp-dash">—</span>
          <label>
            止
            <select v-model.number="customTo" class="pp-select">
              <option v-for="m in monthOptions" :key="'t' + m" :value="m">{{ m }}月</option>
            </select>
          </label>
          <button
            type="button"
            class="pp-opt on pp-apply"
            :disabled="!customKey"
            @click="applyCustom"
          >
            应用
          </button>
        </div>
        <p v-if="!customKey" class="pp-empty">该起止组合不在可选周期中</p>
        <p v-else class="pp-preview">将选中：{{ customKey }}</p>
        <div class="pp-custom-list">
          <button
            v-for="k in customs"
            :key="k"
            type="button"
            class="pp-opt pp-opt-sm"
            :class="{ on: k === current }"
            @click="pick(k)"
          >
            {{ k.replace(/^\d{4}年/, '') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pp {
  position: relative;
  z-index: 40;
}
.pp-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid var(--line, rgba(34, 211, 238, 0.35));
  background: var(--panel, rgba(8, 16, 32, 0.92));
  color: inherit;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  max-width: min(220px, 70vw);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pp-caret {
  opacity: 0.7;
  font-size: 11px;
}
.pp-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: min(320px, calc(100vw - 24px));
  max-height: min(420px, 70vh);
  overflow: auto;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid var(--line, rgba(34, 211, 238, 0.35));
  /* R-03 将再统一 token；此处先保证可读 */
  background: rgba(8, 14, 28, 0.97);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  z-index: 50;
}
:global(html[data-theme='light']) .pp-panel,
:global(body.theme-light) .pp-panel {
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.pp-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.pp-tab {
  flex: 1 1 auto;
  min-height: 36px;
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  opacity: 0.85;
}
.pp-tab.on {
  border-color: var(--blue, #22d3ee);
  background: rgba(34, 211, 238, 0.12);
  opacity: 1;
  font-weight: 600;
}
.pp-body {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.pp-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.pp-opt {
  min-height: 36px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--line, rgba(34, 211, 238, 0.28));
  background: transparent;
  color: inherit;
  font-size: 13px;
  cursor: pointer;
}
.pp-opt.on {
  border-color: var(--blue, #22d3ee);
  background: rgba(34, 211, 238, 0.15);
  font-weight: 600;
}
.pp-opt:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pp-opt-sm {
  font-size: 12px;
  min-height: 32px;
}
.pp-empty {
  margin: 0;
  font-size: 12px;
  opacity: 0.7;
  width: 100%;
}
.pp-custom {
  flex-direction: column;
  align-items: stretch;
}
.pp-custom-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.pp-custom-row label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.pp-select {
  min-height: 32px;
  border-radius: 6px;
  border: 1px solid var(--line, rgba(34, 211, 238, 0.28));
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  font: inherit;
  padding: 2px 6px;
}
.pp-dash {
  opacity: 0.6;
}
.pp-preview {
  margin: 0;
  font-size: 12px;
  opacity: 0.85;
}
.pp-custom-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 160px;
  overflow: auto;
}
@media (max-width: 400px) {
  .pp-panel {
    right: auto;
    left: 0;
    width: min(300px, calc(100vw - 16px));
  }
  .pp-grid-4 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
