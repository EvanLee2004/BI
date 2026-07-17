<script setup lang="ts">
/**
 * 费用明细：走 /api/v1/vm/ledger，任何会话白名单列；单元格 text 转义（铁律10）。
 * 翻页 / 月区间 / 列筛胶囊 / 导出 Excel。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'

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

// 单元格用 Vue 文本插值（等同 textContent），事项等自由文本自动转义——禁止原始 HTML 绑定。

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
    // 列筛：选中列关键词
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
    // 守卫：禁止列绝不出现
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
  params.set('table', '费用明细')
  if (monthFrom.value) params.set('month_from', monthFrom.value)
  if (monthTo.value) params.set('month_to', monthTo.value)
  if (filterQ.value.trim()) params.set('q', filterQ.value.trim())
  if (store.scope === 'bu' && store.buName) params.set('bu', store.buName)
  // 看端导出：管理端 audience 会全列——改走 ledger 同源时，用 detail_export 但强制非管理员会话路径
  // 管理员会话 detail_export 会全列；任务书要求导出=白名单。用 blob 从当前页 JSON 组 CSV 兜底。
  // 优先：若当前是管理员，本地用白名单列导出。
  const cols = columns.value
  const all: Record<string, unknown>[] = []
  // 拉最多 5000 行
  const p2 = new URLSearchParams(params)
  p2.set('page', '1')
  p2.set('page_size', '5000')
  if (store.scope === 'bu' && store.buName) p2.set('bu', store.buName)
  if (monthFrom.value) p2.set('month_from', monthFrom.value)
  if (monthTo.value) p2.set('month_to', monthTo.value)
  if (filterQ.value.trim()) p2.set('q', filterQ.value.trim())
  const r = await fetch('/api/v1/vm/ledger?' + p2.toString(), { credentials: 'same-origin' })
  if (!r.ok) {
    alert('导出失败')
    return
  }
  const d = await r.json()
  const ccols: string[] = d.columns || cols
  const rrows: Record<string, unknown>[] = d.rows || []
  const lines = [ccols.join(',')]
  for (const row of rrows) {
    lines.push(
      ccols
        .map((c) => {
          const v = String(row[c] ?? '')
          if (/[",\n]/.test(v)) return '"' + v.replace(/"/g, '""') + '"'
          return v
        })
        .join(','),
    )
  }
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = '费用明细_白名单.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// 周期 → 月区间粗跟随（年/季/月标签解析）
watch(
  () => store.period,
  (k) => {
    // 简单跟随：X年 → 空；X年N月 → 该月；X年Q1 → 01-03
    monthFrom.value = ''
    monthTo.value = ''
    const m = String(k || '').match(/(\d{4})年(?:Q(\d)|(\d{1,2})(?:-(\d{1,2}))?月)?/)
    if (!m) return
    const y = m[1]
    if (m[2]) {
      const q = +m[2]
      const a = (q - 1) * 3 + 1
      const b = q * 3
      monthFrom.value = `${y}-${String(a).padStart(2, '0')}`
      monthTo.value = `${y}-${String(b).padStart(2, '0')}`
    } else if (m[3] && m[4]) {
      monthFrom.value = `${y}-${String(+m[3]).padStart(2, '0')}`
      monthTo.value = `${y}-${String(+m[4]).padStart(2, '0')}`
    } else if (m[3]) {
      const mm = String(+m[3]).padStart(2, '0')
      monthFrom.value = `${y}-${mm}`
      monthTo.value = `${y}-${mm}`
    }
    page.value = 1
    load()
  },
)

onMounted(() => load())
</script>
<template>
  <div class="card">
    <div class="card-h">
      费用明细
      <span class="tag">{{ info }}</span>
    </div>
    <div class="ledger-tools" style="display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 12px; align-items: center">
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
  </div>
</template>
