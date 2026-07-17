<script setup lang="ts">
/**
 * 费用明细：走 /api/v1/vm/ledger，任何会话白名单列；单元格 text 转义（铁律10）。
 * 翻页 / 月区间 / 列筛胶囊 / 导出 Excel（服务端 xlsx，任务书51·B5）。
 * 周期月区间：VM.ledger.period_months 直接赋值（任务书51·B6）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'

const store = useCockpitStore()

const columns = ref<string[]>([])
const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const err = ref('')
const monthFrom = ref('')
const monthTo = ref('')
const filterQ = ref('')
const colFilter = ref('')

const info = computed(() => {
  if (loading.value) return '加载中…'
  if (err.value) return err.value
  return `共 ${total.value} 行 · 第 ${page.value} 页`
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

async function load() {
  loading.value = true
  err.value = ''
  try {
    const params = new URLSearchParams()
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
    if (monthFrom.value) params.set('month_from', monthFrom.value)
    if (monthTo.value) params.set('month_to', monthTo.value)
    if (filterQ.value.trim()) params.set('q', filterQ.value.trim())
    if (store.scope === 'bu' && store.buName) params.set('bu', store.buName)
    if (colFilter.value && filterQ.value.trim()) {
      params.set(
        'filters',
        JSON.stringify({ [colFilter.value]: { q: filterQ.value.trim() } }),
      )
    }
    const r = await fetch('/api/v1/vm/ledger?' + params.toString(), { credentials: 'same-origin' })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error((d as { detail?: string }).detail || 'HTTP ' + r.status)
    }
    const d = await r.json()
    columns.value = d.columns || []
    rows.value = d.rows || []
    total.value = d.total || 0
    const forbidden = new Set(d.forbidden || ['定位键', '收单月份', '归属月', '提单人', '提单人部门', '配音费合同号'])
    for (const c of columns.value) {
      if (forbidden.has(c)) throw new Error('接口泄漏隐藏列：' + c)
    }
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e)
    columns.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

function prev() {
  if (page.value > 1) {
    page.value--
    load()
  }
}
function next() {
  if (page.value < totalPages.value) {
    page.value++
    load()
  }
}
function applyFilter() {
  page.value = 1
  load()
}

async function exportXlsx() {
  const params = new URLSearchParams()
  if (monthFrom.value) params.set('month_from', monthFrom.value)
  if (monthTo.value) params.set('month_to', monthTo.value)
  if (filterQ.value.trim()) params.set('q', filterQ.value.trim())
  if (store.scope === 'bu' && store.buName) params.set('bu', store.buName)
  if (colFilter.value && filterQ.value.trim()) {
    params.set('filters', JSON.stringify({ [colFilter.value]: { q: filterQ.value.trim() } }))
  }
  const r = await fetch('/api/v1/vm/ledger/export?' + params.toString(), { credentials: 'same-origin' })
  if (!r.ok) {
    alert('导出失败')
    return
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = '费用明细_白名单.xlsx'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

// 任务书51·B6：周期月区间由 VM 下发，前端只赋值（禁止正则拆中文周期）
watch(
  () => [store.period, store.vm?.ledger] as const,
  ([k]) => {
    const pm = store.vm?.ledger?.period_months
    const range = (k && pm && pm[String(k)]) || { month_from: '', month_to: '' }
    monthFrom.value = range.month_from || ''
    monthTo.value = range.month_to || ''
    page.value = 1
    load()
  },
)

onMounted(() => load())
</script>
<template>
  <SciFiPanel title="费用明细" :tag="info">
    <div class="ledger-tools" style="display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0 8px; align-items: center">
      <label
        >月起
        <input v-model="monthFrom" placeholder="2026-01" style="width: 90px" @change="applyFilter"
      /></label>
      <label
        >月止
        <input v-model="monthTo" placeholder="2026-12" style="width: 90px" @change="applyFilter"
      /></label>
      <select v-model="colFilter" style="max-width: 140px">
        <option value="">全列关键词</option>
        <option v-for="c in columns" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-model="filterQ" placeholder="筛选" style="width: 120px" @keyup.enter="applyFilter" />
      <button type="button" class="mini" @click="applyFilter">筛选</button>
      <button type="button" class="ghost mini" @click="exportXlsx">导出 Excel</button>
      <button type="button" class="ghost mini" :disabled="page <= 1" @click="prev">上一页</button>
      <button type="button" class="ghost mini" :disabled="page >= totalPages" @click="next">下一页</button>
    </div>
    <div class="ledger-scroll">
      <table class="bu-ledger cock-ledger">
        <thead>
          <tr>
            <th v-for="c in columns" :key="c">{{ c }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td
              v-for="c in columns"
              :key="c"
              :class="{ num: /金额|含税/.test(c), 'col-flex': /事项/.test(c) }"
              >{{ row[c] == null ? '' : String(row[c]) }}</td
            >
          </tr>
          <tr v-if="!rows.length && !loading">
            <td :colspan="columns.length || 1" class="muted">无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </SciFiPanel>
</template>
