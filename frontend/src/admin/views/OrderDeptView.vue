<script setup lang="ts">
/**
 * 下单未填部门 · 2.2.6：表头筛选驱动本页批量归类；确认框明示「仅当前页」+笔数+金额。
 * 服务端分页每页 50；顶栏无销售筛选（防两套筛选脱节）。
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance } from 'element-plus'
import { jget, jpost } from '../api'

const reloadDash = inject<() => void>('reloadDash', () => {})
const refreshExceptions = inject<() => Promise<void>>('refreshExceptions', async () => {})

const rows = ref<Record<string, unknown>[]>([])
const depts = ref<string[]>([])
const batchDept = ref('')
const loading = ref(false)
const bulkLoading = ref(false)
const rowDept = ref<Record<string, string>>({})
const page = ref(1)
const pageSize = 50
const total = ref(0)
const pages = ref(1)
const tableRef = ref<TableInstance>()
/** el-table 列筛选生效值：columnKey → 选中值列表 */
const activeFilters = ref<Record<string, string[]>>({})

/** 本页 × 表头当前筛选（与表格可见行同一数据源） */
const filteredRows = computed(() => {
  let list = rows.value
  for (const [prop, vals] of Object.entries(activeFilters.value)) {
    if (!vals || vals.length === 0) continue
    list = list.filter((r) => vals.includes(String(r[prop] ?? '')))
  }
  return list
})

const filterSummary = computed(() => {
  const parts: string[] = []
  for (const [prop, vals] of Object.entries(activeFilters.value)) {
    if (!vals || vals.length === 0) continue
    parts.push(`${prop}=${vals.join('、')}`)
  }
  return parts.length ? parts.join('；') : '本页全部待归类'
})

function sumOrderAmt(list: Record<string, unknown>[]): number {
  let s = 0
  for (const r of list) {
    const raw = r['下单预估额']
    if (raw == null || raw === '') continue
    const n = typeof raw === 'number' ? raw : Number(String(raw).replace(/,/g, ''))
    if (!Number.isNaN(n)) s += n
  }
  return s
}

function fmtYuan(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function dateFilterOptions() {
  return [...new Set(rows.value.map((r) => String(r['下单日期'] || '')).filter(Boolean))]
    .slice(0, 40)
    .map((t) => ({ text: t, value: t }))
}
function salesFilterOptions() {
  return [...new Set(rows.value.map((r) => String(r['销售'] || '')).filter(Boolean))]
    .map((t) => ({ text: t, value: t }))
}

function onFilterChange(filters: Record<string, string[]>) {
  // Element Plus：key 为 column-key / prop
  const next: Record<string, string[]> = {}
  for (const [k, v] of Object.entries(filters || {})) {
    if (Array.isArray(v) && v.length) next[k] = v.map(String)
  }
  activeFilters.value = next
}

function clearColFilters() {
  activeFilters.value = {}
  try {
    tableRef.value?.clearFilter()
  } catch {
    /* ignore */
  }
}

async function load(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  clearColFilters()
  try {
    if (!depts.value.length) {
      try {
        depts.value = await jget('/api/order_depts')
      } catch {
        depts.value = []
      }
    }
    const d = await jget<{ pages: number; total: number; rows: Record<string, unknown>[] }>(
      `/api/detail?table=${encodeURIComponent('下单')}&unfilled_dept=1&page=${page.value}&page_size=${pageSize}`,
    )
    pages.value = Math.max(1, Number(d.pages) || 1)
    total.value = Number(d.total) || 0
    rows.value = d.rows || []
  } catch (e) {
    ElMessage.error('查询失败:' + String(e))
    rows.value = []
  } finally {
    loading.value = false
  }
  void refreshExceptions()
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  void load(false)
}
function nextPage() {
  if (page.value >= pages.value) return
  page.value++
  void load(false)
}

async function saveOne(row: Record<string, unknown>) {
  const key = String(row['定位键'] ?? '')
  const dept = rowDept.value[key]
  if (!dept) {
    ElMessage.warning('先选部门')
    return
  }
  try {
    await jpost('/api/adjust', {
      目标表: 'std_下单',
      定位键: key,
      字段: '部门',
      新值: dept,
      原因: '异常处理·归类部门',
      类型: '改值',
    })
    ElMessage.success('✓ 已归类')
    rows.value = rows.value.filter((r) => r['定位键'] !== key)
    total.value = Math.max(0, total.value - 1)
    reloadDash()
    await refreshExceptions()
  } catch (e) {
    ElMessage.error('保存失败：' + String(e))
  }
}

async function batchSave() {
  if (!batchDept.value) {
    ElMessage.warning('先选批量归入的部门')
    return
  }
  const list = filteredRows.value
  if (!list.length) {
    ElMessage.warning('本页当前筛选下没有可归类的行')
    return
  }
  const n = list.length
  const amt = fmtYuan(sumOrderAmt(list))
  const cond = filterSummary.value
  const dept = batchDept.value
  try {
    await ElMessageBox.confirm(
      `【仅当前页】将把下表当前筛选结果归入「${dept}」\n\n` +
        `筛选条件：${cond}\n` +
        `笔数：${n} 笔\n` +
        `金额合计：¥${amt}\n\n` +
        `不会处理其它页的待归类订单。`,
      '批量归入（仅当前页）',
      {
        confirmButtonText: '确认归入',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
  } catch {
    return
  }
  const keys = list.map((r) => String(r['定位键'] ?? '')).filter(Boolean)
  bulkLoading.value = true
  try {
    const res = await jpost<{ count?: number }>('/api/adjust/batch', {
      目标表: 'std_下单',
      字段: '部门',
      新值: dept,
      原因: '异常处理·批量归类·本页表筛',
      类型: '改值',
      定位键列表: keys,
    })
    ElMessage.success(`✓ 已归入「${dept}」${res.count ?? keys.length} 笔（仅当前页）`)
    reloadDash()
    await load(false)
  } catch (e) {
    ElMessage.error('批量失败：' + String(e))
  } finally {
    bulkLoading.value = false
  }
}

onMounted(() => load(true))
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load(true)">刷新清单</el-button>
      <el-select v-model="batchDept" clearable placeholder="批量归入部门" style="width: 160px" filterable>
        <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
      </el-select>
      <el-button size="small" type="primary" :loading="bulkLoading" @click="batchSave">
        对本页表筛结果批量归入
      </el-button>
      <span class="muted">
        待归类共 {{ total }} 笔 · 第 {{ page }}/{{ pages }} 页 · 本页 {{ rows.length }} 笔 · 表筛后
        {{ filteredRows.length }} 笔
      </span>
      <el-button size="small" :disabled="page <= 1 || loading" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">
      智云下单源头没填「部门」→ 排名灰显「（未填）」。请用<strong>表头筛选</strong>缩小本页范围，再点批量归入；
      确认框会写明<strong>仅当前页</strong>的笔数与金额，不会处理其它页。
    </div>

    <el-table
      ref="tableRef"
      :data="rows"
      v-loading="loading || bulkLoading"
      border
      stripe
      height="calc(100vh - 300px)"
      @filter-change="onFilterChange"
    >
      <el-table-column
        prop="下单日期"
        column-key="下单日期"
        label="下单日期"
        width="120"
        :filters="dateFilterOptions()"
        :filter-method="(v: string, row: Record<string, unknown>) => String(row['下单日期'] || '') === v"
      >
        <template #default="{ row }">{{ row['下单日期'] }}</template>
      </el-table-column>
      <el-table-column prop="订单号" label="订单号" min-width="120">
        <template #default="{ row }">{{ row['订单号'] }}</template>
      </el-table-column>
      <el-table-column
        prop="销售"
        column-key="销售"
        label="销售"
        width="100"
        :filters="salesFilterOptions()"
        :filter-method="(v: string, row: Record<string, unknown>) => String(row['销售'] || '') === v"
      >
        <template #default="{ row }">{{ row['销售'] }}</template>
      </el-table-column>
      <el-table-column prop="下单预估额" label="金额" width="120">
        <template #default="{ row }">{{ row['下单预估额'] }}</template>
      </el-table-column>
      <el-table-column label="归到哪个部门" width="160">
        <template #default="{ row }">
          <el-select
            v-model="rowDept[String(row['定位键'])]"
            placeholder="选部门…"
            size="small"
            style="width: 130px"
            filterable
          >
            <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="" width="90">
        <template #default="{ row }">
          <el-button size="small" @click="saveOne(row)">保存</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.muted {
  color: var(--admin-mut, #94a3b8);
  font-size: 13px;
}
</style>
