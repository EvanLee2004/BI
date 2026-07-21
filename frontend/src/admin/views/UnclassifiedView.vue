<script setup lang="ts">
/**
 * 费用未分类 · 2.2.5：服务端分页（每页 50），禁止一次拉满万级行。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { jget } from '../api'

const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const pages = ref(1)
const loading = ref(false)

async function load(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const d = await jget<{ pages: number; total: number; rows: Record<string, unknown>[] }>(
      `/api/detail?table=${encodeURIComponent('费用明细')}&unclassified=1&page=${page.value}&page_size=${pageSize}`,
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

onMounted(() => load(true))
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load(true)">刷新清单</el-button>
      <span class="muted">共 {{ total }} 条 · 第 {{ page }}/{{ pages }} 页</span>
      <el-button size="small" :disabled="page <= 1 || loading" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">收单（费用）台账明细还没填「对应报表大类」→ 暂未计入费用。请在源头补填，下次更新自动计入。</div>
    <el-table :data="rows" v-loading="loading" border stripe height="calc(100vh - 260px)">
      <el-table-column
        label="收单日期"
        width="140"
        prop="收单日期"
        :filters="[...new Set(rows.map((r) => String(r['收单日期'] || r['收单月份'] || '')).filter(Boolean))].slice(0, 40).map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Record<string, unknown>) => String(row['收单日期'] || row['收单月份'] || '') === v"
      >
        <template #default="{ row }">{{ row['收单日期'] || row['收单月份'] }}</template>
      </el-table-column>
      <el-table-column label="金额" width="120" prop="含税金额">
        <template #default="{ row }">{{ row['含税金额'] }}</template>
      </el-table-column>
      <el-table-column
        label="预算明细费用类型"
        min-width="200"
        prop="预算明细费用类型"
        :filters="[...new Set(rows.map((r) => String(r['预算明细费用类型'] || '')).filter(Boolean))].slice(0, 40).map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Record<string, unknown>) => String(row['预算明细费用类型'] || '') === v"
      >
        <template #default="{ row }">{{ row['预算明细费用类型'] }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
