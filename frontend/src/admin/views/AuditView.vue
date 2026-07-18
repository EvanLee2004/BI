<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { jget } from '../api'

const cat = ref('')
const categories = ref<string[]>([])
const rows = ref<{ 时间?: string; 操作账号?: string; 类别?: string; 摘要?: string }[]>([])
const info = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await jget<{
      categories?: string[]
      changes?: { 时间?: string; 操作账号?: string; 类别?: string; 摘要?: string }[]
    }>('/api/config_changes' + (cat.value ? '?category=' + encodeURIComponent(cat.value) : ''))
    if (!categories.value.length && d.categories) categories.value = d.categories
    rows.value = d.changes || []
    info.value = '共 ' + rows.value.length + ' 条' + (cat.value ? '（' + cat.value + '）' : '')
  } catch (e) {
    ElMessage.error(String(e))
    info.value = '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
      <el-select v-model="cat" clearable placeholder="全部类别" style="width: 160px" @change="load">
        <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
      </el-select>
      <span class="muted">{{ info }}</span>
    </div>
    <div class="admin-note">谁在什么时候改了哪项配置都在这里，倒序、最近 200 条。只记变更摘要，不含密码明文。</div>
    <el-table :data="rows" v-loading="loading" border height="calc(100vh - 260px)">
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
