<script setup lang="ts">
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost, downloadBlob } from '../api'
import { DETAIL_TABLES, STD_MAP, yearOptions, monthOptions, ymString } from '../utils'

const route = useRoute()
const reloadDash = inject<() => void>('reloadDash', () => {})
const refreshExceptions = inject<() => Promise<void>>('refreshExceptions', async () => {})

const tableName = computed(() => {
  const t = (route.query.table as string) || '收入明细'
  return (DETAIL_TABLES as readonly string[]).includes(t) ? t : '收入明细'
})

const year = ref('')
const month = ref('')
const q = ref('')
const columns = ref<string[]>([])
const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const page = ref(1)
const pages = ref(1)
const loading = ref(false)
const adjFields = ref<Record<string, string[]>>({})
const colFilters = ref<Record<string, { q?: string; in?: string[]; min?: string; max?: string; from?: string; to?: string }>>({})

const editVisible = ref(false)
const editKey = ref('')
const editField = ref('')
const editValue = ref('')
const editReason = ref('')
const fieldOptions = ref<string[]>([])
/** 3.7.13 A3：禁连点；等 recompute 成功（jpost 返回）再提示 */
const saving = ref(false)
/** 3.7.13 C1：改完按定位键高亮 */
const highlightKey = ref('')
let highlightTimer: ReturnType<typeof setTimeout> | null = null

const yOpts = yearOptions(true)
const mOpts = monthOptions(true)

function filtersQuery(): string {
  const keys = Object.keys(colFilters.value)
  if (!keys.length) return ''
  try {
    return '&filters=' + encodeURIComponent(JSON.stringify(colFilters.value))
  } catch {
    return ''
  }
}

function baseParams(): string {
  let u = ''
  const m = ymString(year.value, month.value)
  if (m) u += '&month=' + encodeURIComponent(m)
  else if (year.value) u += '&year=' + encodeURIComponent(year.value)
  if (q.value.trim()) u += '&q=' + encodeURIComponent(q.value.trim())
  u += filtersQuery()
  return u
}

async function loadAdjFields() {
  try {
    adjFields.value = await jget('/api/v1/admin/adjust_fields')
  } catch {
    /* ignore */
  }
}

/** 2.2.5：真翻页（每页 50），不再「加载更多」累积 */
async function query(reset = true) {
  if (reset) page.value = 1
  loading.value = true
  try {
    const p = page.value
    const d = await jget<{
      page: number
      pages: number
      total: number
      columns: string[]
      rows: Record<string, unknown>[]
    }>(`/api/v1/admin/detail?table=${encodeURIComponent(tableName.value)}&page=${p}&page_size=50${baseParams()}`)
    page.value = d.page
    pages.value = Math.max(1, Number(d.pages) || 1)
    total.value = d.total
    columns.value = d.columns || []
    rows.value = d.rows || []
  } catch (e) {
    ElMessage.error('查询失败:' + String(e))
  } finally {
    loading.value = false
  }
}

function prevPage() {
  if (loading.value || page.value <= 1) return
  page.value -= 1
  void query(false)
}
function nextPage() {
  if (loading.value || page.value >= pages.value) return
  page.value += 1
  void query(false)
}

function openEdit(row: Record<string, unknown>) {
  const key = String(row['定位键'] ?? '')
  const fields = adjFields.value[tableName.value] || []
  if (!fields.length) {
    ElMessage.error('可调字段未加载，请刷新页面后重试')
    return
  }
  // 3.7.13：项目经理只读，不出现在可调字段（后端 ADJUSTABLE 已剔；前端再滤一层）
  const editable = fields.filter((f) => f !== '项目经理')
  const prefer = ['交付额', '下单预估额', '到账金额', '结算金额', '含税金额', '项目成本']
  fieldOptions.value = [...editable].sort(
    (a, b) => (prefer.indexOf(a) < 0 ? 99 : prefer.indexOf(a)) - (prefer.indexOf(b) < 0 ? 99 : prefer.indexOf(b)),
  )
  editKey.value = key
  editField.value = fieldOptions.value[0] || ''
  editValue.value = ''
  editReason.value = ''
  editVisible.value = true
}

function flashHighlight(key: string) {
  highlightKey.value = key
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => {
    highlightKey.value = ''
    highlightTimer = null
  }, 4000)
}

function rowClassName({ row }: { row: Record<string, unknown> }) {
  if (highlightKey.value && String(row['定位键'] ?? '') === highlightKey.value) {
    return 'adj-highlight-row'
  }
  return ''
}

/**
 * 3.7.13 A3+C1：
 * - saving 禁连点
 * - jpost 成功 = 服务端 with_write_lock 内 recompute 已完成（200）
 * - 再 toast，并按库刷新列表 + 高亮该定位键
 */
async function saveEdit() {
  if (saving.value) return
  if (editValue.value === '') {
    ElMessage.error('请填写新值')
    return
  }
  const key = editKey.value
  saving.value = true
  try {
    await jpost('/api/v1/admin/adjust', {
      目标表: STD_MAP[tableName.value],
      定位键: key,
      字段: editField.value,
      新值: editValue.value,
      原因: editReason.value || '管理端改数',
      类型: '改值',
    })
    editVisible.value = false
    // 仅 recompute 成功（HTTP 200）后提示
    ElMessage.success('✓ 已保存并重算')
    reloadDash()
    await refreshExceptions()
    // 按定位键定位：写入搜索框并重查，保证改行可见
    if (key) {
      q.value = key
    }
    await query(true)
    await nextTick()
    if (key) flashHighlight(key)
  } catch (e) {
    ElMessage.error('保存失败：' + String(e))
  } finally {
    saving.value = false
  }
}

async function removeRow(row: Record<string, unknown>) {
  if (saving.value) return
  const key = String(row['定位键'] ?? '')
  try {
    await ElMessageBox.confirm('剔除该行？（软删，可撤销）', '确认')
  } catch {
    return
  }
  saving.value = true
  try {
    await jpost('/api/v1/admin/adjust', {
      目标表: STD_MAP[tableName.value],
      定位键: key,
      字段: '',
      新值: '',
      原因: '剔除',
      类型: '剔除',
    })
    ElMessage.success('✓ 已剔除')
    reloadDash()
    await refreshExceptions()
    await query(true)
  } catch (e) {
    ElMessage.error('失败：' + String(e))
  } finally {
    saving.value = false
  }
}

async function exportExcel() {
  try {
    await downloadBlob(
      `/api/v1/admin/detail/export?table=${encodeURIComponent(tableName.value)}${baseParams()}`,
      `${tableName.value}_${new Date().toISOString().slice(0, 10)}.xlsx`,
    )
    ElMessage.success('✓ 已导出 Excel（当前筛选，最多 5000 行）')
  } catch (e) {
    ElMessage.error('导出失败：' + String(e))
  }
}

function cellText(v: unknown): string {
  if (v == null) return ''
  return String(v)
}

/** 任务书61·E1：Excel 式列筛选——用已载入行构造 filters，filter-method 前端过滤当前页 */
function colFilterOptions(col: string): { text: string; value: string }[] {
  const seen = new Set<string>()
  const out: { text: string; value: string }[] = []
  for (const r of rows.value) {
    const t = cellText(r[col]).trim()
    if (!t || seen.has(t)) continue
    seen.add(t)
    out.push({ text: t.length > 40 ? t.slice(0, 40) + '…' : t, value: t })
    if (out.length >= 80) break
  }
  return out
}

function colFilterMethod(value: string, row: Record<string, unknown>, col: string): boolean {
  return cellText(row[col]).trim() === String(value)
}

watch(
  () => route.query.table,
  () => {
    colFilters.value = {}
    highlightKey.value = ''
    query(true)
  },
)

onMounted(async () => {
  await loadAdjFields()
  await query(true)
})
</script>

<template>
  <div>
    <div class="toolbar">
      <span>当前表：<b>{{ tableName }}</b></span>
      <el-select v-model="year" placeholder="年" clearable style="width: 110px">
        <el-option v-for="o in yOpts" :key="o.value || 'all'" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="month" placeholder="月" clearable style="width: 100px">
        <el-option v-for="o in mOpts" :key="o.value || 'allm'" :label="o.label" :value="o.value" />
      </el-select>
      <el-input v-model="q" placeholder="订单号/定位键/客户…" style="width: 200px" clearable @keyup.enter="query(true)" />
      <el-button type="primary" :disabled="loading || saving" @click="query(true)">查询</el-button>
      <el-button :disabled="saving" @click="exportExcel">导出 Excel</el-button>
      <span class="muted grow">共 {{ total }} 条 · 第 {{ page }}/{{ pages }} 页</span>
      <el-button size="small" :disabled="page <= 1 || loading || saving" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading || saving" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">
      改数=写一条调整记录（重抓不丢）；剔除=软删（可在「数据修正」撤销）。表头漏斗=Excel 式列筛选（当前页）。
      <template v-if="tableName === '收入明细'">
        「项目经理」只读展示。算账看交付日/归属月；原值_*=智云底稿（规范化前留底，不参与改数）。
      </template>
    </div>

    <el-table
      :data="rows"
      v-loading="loading"
      border
      stripe
      height="calc(100vh - 280px)"
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column
        v-for="c in columns"
        :key="c"
        :prop="c"
        :label="c"
        min-width="120"
        show-overflow-tooltip
        :filters="colFilterOptions(c)"
        :filter-method="(val: string, row: Record<string, unknown>) => colFilterMethod(val, row, c)"
        filter-placement="bottom-end"
      >
        <template #default="{ row }">
          <span class="cell-clip" :title="cellText(row[c])">{{ cellText(row[c]) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :disabled="saving" @click="openEdit(row)">改</el-button>
          <el-button size="small" text :disabled="saving" @click="removeRow(row)">剔除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="editVisible" title="改数" width="480px" :close-on-click-modal="!saving">
      <p>定位键 <code>{{ editKey }}</code></p>
      <el-form label-width="72px">
        <el-form-item label="字段">
          <el-select v-model="editField" style="width: 100%" :disabled="saving">
            <el-option v-for="f in fieldOptions" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="新值">
          <el-input v-model="editValue" placeholder="数字或文本" :disabled="saving" />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="editReason" placeholder="可选" :disabled="saving" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
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
.muted { color: var(--admin-mut); font-size: 13px; }
.grow { flex: 1; }
code { font-size: 12px; word-break: break-all; }
:deep(.adj-highlight-row) {
  --el-table-tr-bg-color: color-mix(in srgb, var(--el-color-primary) 18%, transparent);
}
:deep(.adj-highlight-row > td) {
  background-color: color-mix(in srgb, var(--el-color-primary) 18%, transparent) !important;
}
</style>
