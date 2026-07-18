<script setup lang="ts">
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

const salesList = computed(() => {
  const s = new Set(
    rows.value
      .map((r) => String(r['销售'] || '').trim())
      .filter(Boolean),
  )
  return [...s].sort()
})

const shown = computed(() => {
  if (!salesFilter.value) return rows.value
  return rows.value.filter((r) => String(r['销售'] || '').trim() === salesFilter.value)
})

async function load() {
  loading.value = true
  rows.value = []
  try {
    depts.value = await jget('/api/order_depts')
  } catch {
    depts.value = []
  }
  let page = 1
  let pages = 1
  try {
    do {
      const d = await jget<{ pages: number; total: number; rows: Record<string, unknown>[] }>(
        `/api/detail?table=${encodeURIComponent('下单')}&unfilled_dept=1&page=${page}&page_size=200`,
      )
      pages = d.pages
      rows.value = rows.value.concat(d.rows || [])
      page++
    } while (page <= pages && page <= 50)
  } catch (e) {
    ElMessage.error('查询失败:' + String(e))
  } finally {
    loading.value = false
  }
  await refreshExceptions()
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
      `将把 ${list.length} 笔${salesFilter.value ? '（销售=' + salesFilter.value + '）' : ''} 全部归到「${batchDept.value}」？`,
      '批量归类',
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
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新清单</el-button>
      <el-select v-model="salesFilter" clearable placeholder="全部销售" style="width: 140px">
        <el-option v-for="s in salesList" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="batchDept" clearable placeholder="批量部门" style="width: 140px">
        <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
      </el-select>
      <el-button size="small" type="primary" @click="batchSave">对筛选结果批量归类</el-button>
      <span class="muted">待归类 {{ rows.length }} 笔 · 显示 {{ shown.length }}</span>
    </div>
    <div class="admin-note">智云下单源头没填「部门」→ 排名灰显「（未填）」。可按销售筛选后批量归类。</div>

    <el-table :data="shown" v-loading="loading" border height="calc(100vh - 280px)">
      <el-table-column prop="下单日期" label="下单日期" width="120">
        <template #default="{ row }">{{ row['下单日期'] }}</template>
      </el-table-column>
      <el-table-column prop="订单号" label="订单号" min-width="120">
        <template #default="{ row }">{{ row['订单号'] }}</template>
      </el-table-column>
      <el-table-column prop="销售" label="销售" width="100">
        <template #default="{ row }">{{ row['销售'] }}</template>
      </el-table-column>
      <el-table-column prop="下单预估额" label="金额" width="120">
        <template #default="{ row }">{{ row['下单预估额'] }}</template>
      </el-table-column>
      <el-table-column label="归到哪个部门" width="160">
        <template #default="{ row }">
          <el-select v-model="rowDept[String(row['定位键'])]" placeholder="选部门…" size="small" style="width: 130px">
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
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
