<script setup lang="ts">
/**
 * 费用明细：走 /api/v1/vm/ledger，任何会话白名单列；单元格 text 转义（铁律10）。
 * 任务书58·R-50：日历起止 + 查询/本月/返回本年。
 * 任务书61·E3 / 产品改：Excel 式每列表头筛选——可选值多选（对齐数据调整漏斗），非盲输。
 * 任务书61·J-3：默认口径不显人工分摊三类台账行（后端 merge_ledger_caliber_filters）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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
/** R-45：默认期间费用口径；开=台账全量 */
const showAll = ref(false)
const caliberNote = ref('仅期间费用大类（与上方图表口径一致；已剔成本/非利润表）')

/** 每列已选取值（Excel 多选）；空数组/缺键=该列不筛 */
const colIns = ref<Record<string, string[]>>({})
/** 漏斗草稿（打开时拷贝，确定才写入 colIns） */
const draftIns = ref<string[]>([])
const openCol = ref<string | null>(null)
/** 当前漏斗可选值（来自 /api/v1/vm/ledger/values） */
const optionList = ref<string[]>([])
const optionsLoading = ref(false)
const optionsErr = ref('')
/** 在可选值列表内缩窄显示 */
const optionSearch = ref('')

const info = computed(() => {
  if (loading.value) return '加载中…'
  if (err.value) return err.value
  return `共 ${total.value} 行 · 第 ${page.value} 页`
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const activeColFilters = computed(() => {
  const o: Record<string, { in: string[] }> = {}
  for (const [k, v] of Object.entries(colIns.value)) {
    const clean = (v || []).map((x) => String(x)).filter((x) => x !== '')
    if (clean.length) o[k] = { in: clean }
  }
  return o
})

const visibleOptions = computed(() => {
  const q = optionSearch.value.trim().toLowerCase()
  if (!q) return optionList.value
  return optionList.value.filter((v) => v.toLowerCase().includes(q))
})

function yearNum(): number {
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
  const cf = activeColFilters.value
  if (Object.keys(cf).length) {
    params.set('filters', JSON.stringify(cf))
  }
  params.set('show_all', showAll.value ? '1' : '0')
  return params
}

/** 拉可选值时：带其它列筛，但不带本列（后端也会剔本列 in） */
function buildValuesParams(column: string): URLSearchParams {
  const params = new URLSearchParams()
  params.set('column', column)
  if (dateFrom.value) params.set('date_from', dateFrom.value)
  if (dateTo.value) params.set('date_to', dateTo.value)
  if (filterQ.value.trim()) params.set('q', filterQ.value.trim())
  if (store.scope === 'bu' && store.buName) params.set('bu', store.buName)
  params.set('show_all', showAll.value ? '1' : '0')
  const others: Record<string, { in: string[] }> = {}
  for (const [k, v] of Object.entries(colIns.value)) {
    if (k === column) continue
    const clean = (v || []).map((x) => String(x)).filter((x) => x !== '')
    if (clean.length) others[k] = { in: clean }
  }
  if (Object.keys(others).length) {
    params.set('filters', JSON.stringify(others))
  }
  params.set('limit', '200')
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

async function loadColumnOptions(column: string) {
  optionsLoading.value = true
  optionsErr.value = ''
  optionList.value = []
  try {
    const r = await fetch('/api/v1/vm/ledger/values?' + buildValuesParams(column).toString(), {
      credentials: 'same-origin',
    })
    if (!r.ok) {
      const d = await r.json().catch(() => ({}))
      throw new Error((d as { detail?: string }).detail || 'HTTP ' + r.status)
    }
    const d = await r.json()
    const vals = Array.isArray(d.values) ? d.values.map((x: unknown) => String(x ?? '')) : []
    // 空串也展示为「(空)」可选
    optionList.value = vals
  } catch (e) {
    optionsErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    optionsLoading.value = false
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
  openCol.value = null
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

async function toggleColFilter(c: string) {
  if (openCol.value === c) {
    openCol.value = null
    return
  }
  openCol.value = c
  optionSearch.value = ''
  draftIns.value = [...(colIns.value[c] || [])]
  await loadColumnOptions(c)
}

function isDraftChecked(v: string): boolean {
  return draftIns.value.includes(v)
}

function toggleDraft(v: string) {
  const i = draftIns.value.indexOf(v)
  if (i >= 0) {
    draftIns.value = draftIns.value.filter((x) => x !== v)
  } else {
    draftIns.value = [...draftIns.value, v]
  }
}

function selectAllVisible() {
  const set = new Set(draftIns.value)
  for (const v of visibleOptions.value) set.add(v)
  draftIns.value = [...set]
}

function clearDraft() {
  draftIns.value = []
}

function applyColFilter() {
  const c = openCol.value
  if (!c) return
  const next = { ...colIns.value }
  if (draftIns.value.length) next[c] = [...draftIns.value]
  else delete next[c]
  colIns.value = next
  applyFilter()
}

function clearColFilter(c: string) {
  const next = { ...colIns.value }
  delete next[c]
  colIns.value = next
  draftIns.value = []
  applyFilter()
}

function optionLabel(v: string): string {
  if (v === '') return '(空)'
  return v.length > 48 ? v.slice(0, 48) + '…' : v
}

function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement | null
  if (!t) return
  if (t.closest('.ld-col-filter') || t.closest('.ld-th-btn')) return
  openCol.value = null
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

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

watch(
  () => [store.vm?.year_key, store.scope, store.buName] as const,
  () => {
    if (!dateFrom.value || !dateTo.value) applyYearDefault()
    page.value = 1
    load()
  },
  { immediate: true },
)

/** 54.5：日期列展示去掉无意义的 00:00:00 */
function cellText(v: unknown): string {
  if (v == null) return ''
  const s = String(v)
  return s.replace(/(\d{4}-\d{2}-\d{2})[ T]00:00:00(?:\.0+)?$/, '$1')
}

function hasColIn(c: string): boolean {
  return !!(colIns.value[c] && colIns.value[c].length)
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
      <input v-model="filterQ" placeholder="全列关键词" style="width: 120px" @keyup.enter="applyFilter" />
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
            <th v-for="c in columns" :key="c" class="ld-th">
              <button
                type="button"
                class="ld-th-btn"
                :class="{ on: hasColIn(c) || openCol === c }"
                data-testid="ledger-col-filter-btn"
                @click.stop="toggleColFilter(c)"
              >
                {{ c }}
                <span class="ld-funnel" aria-hidden="true">▾</span>
              </button>
              <div
                v-if="openCol === c"
                class="ld-col-filter"
                data-testid="ledger-col-filter-pop"
                @click.stop
              >
                <input
                  v-model="optionSearch"
                  type="text"
                  class="ld-opt-search"
                  data-testid="ledger-col-option-search"
                  placeholder="搜索可选值…"
                />
                <div v-if="optionsLoading" class="ld-opt-hint">加载可选值…</div>
                <div v-else-if="optionsErr" class="ld-opt-err">{{ optionsErr }}</div>
                <div v-else class="ld-opt-list" data-testid="ledger-col-option-list">
                  <label v-for="v in visibleOptions" :key="v === '' ? '__empty__' : v" class="ld-opt-row">
                    <input
                      type="checkbox"
                      :checked="isDraftChecked(v)"
                      data-testid="ledger-col-option-cb"
                      @change="toggleDraft(v)"
                    />
                    <span :title="v">{{ optionLabel(v) }}</span>
                  </label>
                  <div v-if="!visibleOptions.length" class="ld-opt-hint">无匹配可选值</div>
                </div>
                <div class="ld-col-actions">
                  <button type="button" class="ghost mini" data-testid="ledger-col-select-all" @click="selectAllVisible">
                    全选
                  </button>
                  <button type="button" class="ghost mini" data-testid="ledger-col-clear-draft" @click="clearDraft">
                    清空勾选
                  </button>
                  <button type="button" class="mini" data-testid="ledger-col-apply" @click="applyColFilter">确定</button>
                  <button type="button" class="ghost mini" data-testid="ledger-col-clear" @click="clearColFilter(c)">
                    清除筛选
                  </button>
                </div>
              </div>
            </th>
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
.ld-th{position:relative;vertical-align:top}
.ld-th-btn{
  display:inline-flex;align-items:center;gap:4px;max-width:100%;
  background:transparent;border:0;color:inherit;font:inherit;font-weight:600;
  cursor:pointer;padding:2px 0;text-align:left;
}
.ld-th-btn.on{color:#22d3ee}
.ld-funnel{opacity:.65;font-size:10px}
.ld-col-filter{
  position:absolute;z-index:var(--z-popover, 40);left:0;top:100%;
  min-width:200px;max-width:280px;padding:8px;border-radius:8px;
  background:var(--overlay-panel, rgba(8,14,28,.97));
  border:1px solid rgba(125,211,252,.25);
  box-shadow:0 8px 24px rgba(0,0,0,.35);
}
.ld-opt-search{
  width:100%;box-sizing:border-box;padding:4px 6px;border-radius:4px;margin-bottom:6px;
  border:1px solid rgba(125,211,252,.2);background:rgba(0,0,0,.25);color:var(--ink,#e8eef8);
}
.ld-opt-list{
  max-height:220px;overflow:auto;margin-bottom:6px;
  border:1px solid rgba(125,211,252,.12);border-radius:6px;padding:4px;
}
.ld-opt-row{
  display:flex;align-items:flex-start;gap:6px;padding:3px 4px;font-size:12px;font-weight:400;
  cursor:pointer;line-height:1.35;
}
.ld-opt-row:hover{background:rgba(125,211,252,.08)}
.ld-opt-row span{word-break:break-all}
.ld-opt-hint,.ld-opt-err{font-size:12px;padding:6px 2px;color:var(--mut,#94a3b8)}
.ld-opt-err{color:#f87171}
.ld-col-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
</style>
