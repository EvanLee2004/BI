<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { jget } from '../api'
import { useClientPager } from '../composables/useClientPager'

const cat = ref('')
const categories = ref<string[]>([])
const rows = ref<{ 时间?: string; 操作账号?: string; 类别?: string; 摘要?: string }[]>([])
const loading = ref(false)
const { page, pages, pageRows, pageInfo, resetPage, prevPage, nextPage } = useClientPager(rows)

async function load() {
  loading.value = true
  try {
    const d = await jget<{
      categories?: string[]
      changes?: { 时间?: string; 操作账号?: string; 类别?: string; 摘要?: string }[]
    }>('/api/config_changes' + (cat.value ? '?category=' + encodeURIComponent(cat.value) : ''))
    if (!categories.value.length && d.categories) categories.value = d.categories
    rows.value = d.changes || []
    resetPage()
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    loading.value = false
  }
}

watch(cat, () => {
  void load()
})

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
      <el-select v-model="cat" clearable placeholder="全部类别" style="width: 160px">
        <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
      </el-select>
      <span class="muted">{{ pageInfo }}{{ cat ? '（' + cat + '）' : '' }}</span>
      <el-button size="small" :disabled="page <= 1 || loading" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">谁在什么时候改了哪项配置都在这里，倒序、最近 200 条。只记变更摘要，不含密码明文。</div>
    <el-table :data="pageRows" v-loading="loading" border height="calc(100vh - 260px)">
      <el-table-column prop="时间" label="时间" width="170" />
      <el-table-column prop="操作账号" label="操作账号" width="120" />
      <el-table-column prop="类别" label="类别" width="120" />
      <el-table-column prop="摘要" label="变更摘要" min-width="280" show-overflow-tooltip />
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
</style>
