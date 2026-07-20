<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
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
    adjFields.value = await jget('/api/adjust_fields')
  } catch {
    /* ignore */
  }
}

async function query(reset = true) {
  if (reset) {
    page.value = 1
    rows.value = []
  }
  loading.value = true
  try {
    const p = page.value
    const d = await jget<{
      page: number
      pages: number
      total: number
      columns: string[]
      rows: Record<string, unknown>[]
    }>(`/api/detail?table=${encodeURIComponent(tableName.value)}&page=${p}&page_size=50${baseParams()}`)
    page.value = d.page
    pages.value = d.pages
    total.value = d.total
    columns.value = d.columns || []
    if (reset) rows.value = d.rows || []
    else rows.value = rows.value.concat(d.rows || [])
  } catch (e) {
    ElMessage.error('查询失败:' + String(e))
  } finally {
    loading.value = false
  }
}

function loadMore() {
  if (loading.value || page.value >= pages.value) return
  page.value += 1
  query(false)
}

function openEdit(row: Record<string, unknown>) {
  const key = String(row['定位键'] ?? '')
  const fields = adjFields.value[tableName.value] || []
  if (!fields.length) {
    ElMessage.error('可调字段未加载，请刷新页面后重试')
    return
  }
  const prefer = ['交付额', '下单预估额', '到账金额', '结算金额', '含税金额', '项目成本']
  fieldOptions.value = [...fields].sort(
    (a, b) => (prefer.indexOf(a) < 0 ? 99 : prefer.indexOf(a)) - (prefer.indexOf(b) < 0 ? 99 : prefer.indexOf(b)),
  )
  editKey.value = key
  editField.value = fieldOptions.value[0] || ''
  editValue.value = ''
  editReason.value = ''
  editVisible.value = true
}

async function saveEdit() {
  if (editValue.value === '') {
    ElMessage.error('请填写新值')
    return
  }
  try {
    await jpost('/api/adjust', {
      目标表: STD_MAP[tableName.value],
      定位键: editKey.value,
      字段: editField.value,
      新值: editValue.value,
      原因: editReason.value || '管理端改数',
      类型: '改值',
    })
    editVisible.value = false
    ElMessage.success('✓ 已保存并重算')
    reloadDash()
    await refreshExceptions()
    await query(true)
  } catch (e) {
    ElMessage.error('保存失败：' + String(e))
  }
}

async function removeRow(row: Record<string, unknown>) {
  const key = String(row['定位键'] ?? '')
  try {
    await ElMessageBox.confirm('剔除该行？（软删，可撤销）', '确认')
  } catch {
    return
  }
  try {
    await jpost('/api/adjust', {
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
  }
}

async function exportExcel() {
  try {
    await downloadBlob(
      `/api/detail_export?table=${encodeURIComponent(tableName.value)}${baseParams()}`,
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
      <el-button type="primary" @click="query(true)">查询</el-button>
      <el-button @click="exportExcel">导出 Excel</el-button>
      <span class="muted grow">共{{ total }}行（已载入{{ rows.length }}）</span>
    </div>
    <div class="admin-note">改数=写一条调整记录（重抓不丢）；剔除=软删（可在「数据修正」撤销）。表头漏斗=Excel 式列筛选（当前已载入行）。</div>

    <el-table :data="rows" v-loading="loading" border stripe height="calc(100vh - 280px)" style="width: 100%">
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
        <template #default="{ row }">{{ cellText(row[c]) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">改</el-button>
          <el-button size="small" text @click="removeRow(row)">剔除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 10px; text-align: center">
      <el-button v-if="page < pages" :loading="loading" @click="loadMore">加载更多</el-button>
      <span v-else class="muted">已全部加载</span>
    </div>

    <el-dialog v-model="editVisible" title="改数" width="480px">
      <p>定位键 <code>{{ editKey }}</code></p>
      <el-form label-width="72px">
        <el-form-item label="字段">
          <el-select v-model="editField" style="width: 100%">
            <el-option v-for="f in fieldOptions" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="新值">
          <el-input v-model="editValue" placeholder="数字或文本" />
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="editReason" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
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
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
.grow { flex: 1; }
code { font-size: 12px; word-break: break-all; }
</style>
