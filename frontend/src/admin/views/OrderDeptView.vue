<script setup lang="ts">
/**
 * 下单未填部门 · 54.7 R-00a：禁止一次拉满/渲满万级行（旧逻辑 page_size=200×50 页 concat 卡死）。
 * 服务端分页，每页 50 行；真分页控件；2s 内可交互。
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'

const reloadDash = inject<() => void>('reloadDash', () => {})
const refreshExceptions = inject<() => Promise<void>>('refreshExceptions', async () => {})

const rows = ref<Record<string, unknown>[]>([])
const depts = ref<string[]>([])
const salesFilter = ref('')
const batchDept = ref('')
const loading = ref(false)
const rowDept = ref<Record<string, string>>({})
const page = ref(1)
const pageSize = 50
const total = ref(0)
const pages = ref(1)

const salesList = computed(() => {
  const s = new Set(
    rows.value
      .map((r) => String(r['销售'] || '').trim())
      .filter(Boolean),
  )
  return [...s].sort()
})

/** 当前页内销售筛选（不二次请求；全库筛在后续迭代可加 query 参数） */
const shown = computed(() => {
  if (!salesFilter.value) return rows.value
  return rows.value.filter((r) => String(r['销售'] || '').trim() === salesFilter.value)
})

async function load(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
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
  // 不阻塞首屏：计数刷新放后
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
    ElMessage.warning('先选批量部门')
    return
  }
  const list = shown.value
  if (!list.length) {
    ElMessage.warning('没有可归类的行')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将把本页筛选结果 ${list.length} 笔${salesFilter.value ? '（销售=' + salesFilter.value + '）' : ''} 归到「${batchDept.value}」？`,
      '批量归类（仅当前页）',
    )
  } catch {
    return
  }
  let ok = 0
  let fail = 0
  for (const r of list) {
    try {
      await jpost('/api/adjust', {
        目标表: 'std_下单',
        定位键: r['定位键'],
        字段: '部门',
        新值: batchDept.value,
        原因: '异常处理·批量归类' + (salesFilter.value ? '·' + salesFilter.value : ''),
        类型: '改值',
      })
      ok++
    } catch {
      fail++
    }
  }
  ElMessage.success(`✓ 批量完成：成功 ${ok}${fail ? '，失败 ' + fail : ''}`)
  reloadDash()
  await load(false)
}

onMounted(() => load(true))
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load(true)">刷新清单</el-button>
      <el-select v-model="salesFilter" clearable placeholder="本页销售筛选" style="width: 140px">
        <el-option v-for="s in salesList" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="batchDept" clearable placeholder="批量部门" style="width: 140px">
        <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
      </el-select>
      <el-button size="small" type="primary" @click="batchSave">对本页筛选批量归类</el-button>
      <span class="muted">共 {{ total }} 条 · 第 {{ page }}/{{ pages }} 页 · 本页 {{ shown.length }}</span>
      <el-button size="small" :disabled="page <= 1 || loading" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">
      智云下单源头没填「部门」→ 排名灰显「（未填）」。列表<strong>分页加载</strong>（每页 {{ pageSize }}
      行），避免大数字徽章点进后全量渲染卡死。
    </div>

    <el-table :data="shown" v-loading="loading" border stripe height="calc(100vh - 300px)">
      <el-table-column
        prop="下单日期"
        label="下单日期"
        width="120"
        :filters="[...new Set(shown.map((r) => String(r['下单日期'] || '')).filter(Boolean))].slice(0, 40).map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Record<string, unknown>) => String(row['下单日期'] || '') === v"
      >
        <template #default="{ row }">{{ row['下单日期'] }}</template>
      </el-table-column>
      <el-table-column prop="订单号" label="订单号" min-width="120">
        <template #default="{ row }">{{ row['订单号'] }}</template>
      </el-table-column>
      <el-table-column
        prop="销售"
        label="销售"
        width="100"
        :filters="[...new Set(shown.map((r) => String(r['销售'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
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
