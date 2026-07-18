<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { jget } from '../api'

const rows = ref<Record<string, unknown>[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  rows.value = []
  let page = 1
  let pages = 1
  try {
    do {
      const d = await jget<{ pages: number; total: number; rows: Record<string, unknown>[] }>(
        `/api/detail?table=${encodeURIComponent('费用明细')}&unclassified=1&page=${page}&page_size=200`,
      )
      pages = d.pages
      total.value = d.total
      rows.value = rows.value.concat(d.rows || [])
      page++
    } while (page <= pages && page <= 50)
  } catch (e) {
    ElMessage.error('查询失败:' + String(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新清单</el-button>
      <span class="muted">未分类 {{ total }} 笔</span>
    </div>
    <div class="admin-note">收单（费用）台账明细还没填「对应报表大类」→ 暂未计入费用。请在源头补填，下次更新自动计入。</div>
    <el-table :data="rows" v-loading="loading" border stripe height="calc(100vh - 260px)">
      <el-table-column label="收单日期" width="140">
        <template #default="{ row }">{{ row['收单日期'] || row['收单月份'] }}</template>
      </el-table-column>
      <el-table-column label="金额" width="120">
        <template #default="{ row }">{{ row['含税金额'] }}</template>
      </el-table-column>
      <el-table-column label="预算明细费用类型" min-width="200">
        <template #default="{ row }">{{ row['预算明细费用类型'] }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
