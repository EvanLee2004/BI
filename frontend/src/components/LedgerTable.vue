<script setup lang="ts">
/**
 * 费用明细：走 /api/v1/vm/ledger，任何会话白名单列；单元格 text 转义（铁律10）。
 * 任务书58·R-50：日历起止（收单日期日级）+ 查询/本月/返回本年；默认本年全年。
 * 只筛明细表本身，不联动上方热力/费用折线；show_all / 关键词 / 分页 / 导出同源。
 */
import { computed, ref, watch } from 'vue'
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
/** 收单日期起止 YYYY-MM-DD（任务书58） */
const dateFrom = ref('')
const dateTo = ref('')
const filterQ = ref('')
const colFilter = ref('')
/** R-45：默认期间费用口径；开=台账全量 */
const showAll = ref(false)
const caliberNote = ref('仅期间费用大类（与上方图表口径一致；已剔成本/非利润表）')

const info = computed(() => {
  if (loading.value) return '加载中…'
  if (err.value) return err.value
  return `共 ${total.value} 行 · 第 ${page.value} 页`
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function yearNum(): number {
  // 任务书51·B6：不用正则拆周期字符串；字面扫描连续 4 位数字作年
  const yk = String(store.vm?.year_key || store.period || '')
  for (let i = 0; i <= yk.length - 4; i++) {
    const chunk = yk.slice(i, i + 4)
    let ok = true
    for (let j = 0; j < 4; j++) {
      const c = chunk.charCodeAt(j)
      if (c < 48 || c > 57) {
        ok = false
        break
      }
    }
    if (ok) return Number(chunk)
  }
  const y = store.vm?.daily?.year
  if (y) return Number(y)
  return new Date().getFullYear()
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function todayYmd(): string {
  const d = new Date()
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function yearRange(): { s: string; e: string } {
  const y = yearNum()
  return { s: `${y}-01-01`, e: `${y}-12-31` }
}

function monthRange(): { s: string; e: string } {
  const d = new Date()
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  return { s: `${y}-${pad2(m)}-01`, e: todayYmd() }
}

function applyYearDefault() {
  const se = yearRange()
  dateFrom.value = se.s
  dateTo.value = se.e
}

function buildParams(forExport = false): URLSearchParams {
  const params = new URLSearchParams()
  if (!forExport) {
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
  }
  if (dateFrom.value) params.set('date_from', dateFrom.value)
  if (dateTo.value) params.set('date_to', dateTo.value)
  if (filterQ.value.trim()) params.set('q', filterQ.value.trim())
  if (store.scope === 'bu' && store.buName) params.set('bu', store.buName)
  if (colFilter.value && filterQ.value.trim()) {
    params.set(
      'filters',
      JSON.stringify({ [colFilter.value]: { q: filterQ.value.trim() } }),
    )
  }
  params.set('show_all', showAll.value ? '1' : '0')
  return params
}

async function load() {
  loading.value = true
  err.value = ''
  try {
    const r = await fetch('/api/v1/vm/ledger?' + buildParams().toString(), {
      credentials: 'same-origin',
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error((d as { detail?: string }).detail || 'HTTP ' + r.status)
    }
    const d = await r.json()
    columns.value = d.columns || []
    rows.value = d.rows || []
    total.value = d.total || 0
    if (d.caliber_note) caliberNote.value = String(d.caliber_note)
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

function setThisMonth() {
  const se = monthRange()
  dateFrom.value = se.s
  dateTo.value = se.e
  applyFilter()
}

function restoreYear() {
  applyYearDefault()
  applyFilter()
}

async function exportXlsx() {
  const r = await fetch('/api/v1/vm/ledger/export?' + buildParams(true).toString(), {
    credentials: 'same-origin',
  })
  if (!r.ok) {
    alert('导出失败')
    return
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = showAll.value ? '费用明细_台账全量.xlsx' : '费用明细_期间费用.xlsx'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

// 进入看端 / 年 key 就绪：默认本年全年（不随全局周期月联动热力无关区间）
watch(
  () => [store.vm?.year_key, store.scope, store.buName] as const,
  () => {
    if (!dateFrom.value || !dateTo.value) applyYearDefault()
    page.value = 1
    load()
  },
  { immediate: true },
)

/** 54.5：日期列展示去掉无意义的 00:00:00（纯展示串，不改后端/不碰金额） */
function cellText(v: unknown): string {
  if (v == null) return ''
  const s = String(v)
  return s.replace(/(\d{4}-\d{2}-\d{2})[ T]00:00:00(?:\.0+)?$/, '$1')
}

</script>
<template>
  <SciFiPanel title="费用明细" :tag="info">
    <p class="ledger-caliber-note" data-testid="ledger-caliber-note">{{ caliberNote }}</p>
    <div
      class="ledger-tools"
      data-testid="ledger-date-tools"
      style="display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0 8px; align-items: center"
    >
      <label class="ledger-show-all" data-testid="ledger-show-all">
        <input type="checkbox" v-model="showAll" @change="applyFilter" />
        显示全部台账记录
      </label>
      <label
        >起
        <input
          id="ledgerDateFrom"
          type="date"
          v-model="dateFrom"
          data-testid="ledger-date-from"
      /></label>
      <label
        >止
        <input
          id="ledgerDateTo"
          type="date"
          v-model="dateTo"
          data-testid="ledger-date-to"
      /></label>
      <button type="button" class="mini" data-testid="ledger-query" @click="applyFilter">查询</button>
      <button type="button" class="ghost mini" data-testid="ledger-this-month" @click="setThisMonth">
        本月
      </button>
      <button type="button" class="ghost mini" data-testid="ledger-restore-year" @click="restoreYear">
        返回本年
      </button>
      <select v-model="colFilter" style="max-width: 140px">
        <option value="">全列关键词</option>
        <option v-for="c in columns" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-model="filterQ" placeholder="筛选" style="width: 120px" @keyup.enter="applyFilter" />
      <button type="button" class="mini" @click="applyFilter">筛选</button>
      <button type="button" class="ghost mini" data-testid="ledger-export" @click="exportXlsx">
        导出 Excel
      </button>
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
              >{{ cellText(row[c]) }}</td
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
<style scoped>
.ledger-caliber-note{margin:0 0 8px;font-size:12px;color:var(--mut,#94a3b8);line-height:1.45}
</style>
