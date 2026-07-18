<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'

const reloadDash = inject<() => void>('reloadDash', () => {})

type Adj = {
  id: number
  创建时间?: string
  经手人?: string
  目标表?: string
  字段?: string
  原值?: string
  新值?: string
  类型?: string
  状态?: string
}

const list = ref<Adj[]>([])
const expOnly = ref(false)
const confirmHtml = ref('')
const loading = ref(false)

const shown = computed(() => (expOnly.value ? list.value.filter((a) => a['状态'] === '过期疑似') : list.value))
const nExp = computed(() => list.value.filter((a) => a['状态'] === '过期疑似').length)

function rowClassName({ row }: { row: Adj }) {
  return row['状态'] === '过期疑似' ? 'exp-row' : ''
}

async function load() {
  loading.value = true
  try {
    list.value = await jget('/api/adjustments')
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    loading.value = false
  }
}

async function revoke(id: number) {
  try {
    await ElMessageBox.confirm('撤销该调整？（=认可源头新值）', '确认')
  } catch {
    return
  }
  try {
    await jpost(`/api/adjust/${id}/revoke`, {})
    ElMessage.success('已撤销')
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error(String(e))
  }
}

async function rearm(id: number) {
  const a: Adj = list.value.find((x) => x.id === id) || { id }
  try {
    await ElMessageBox.confirm(
      `坚持我的数？\n${a['目标表'] || ''} · ${a['字段'] || ''}：将继续使用「${a['新值'] || ''}」`,
      '确认',
    )
  } catch {
    return
  }
  try {
    await jpost(`/api/adjust/${id}/rearm`, {})
    ElMessage.success('已重新生效')
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error(String(e))
  }
}

function batchAsk() {
  if (!nExp.value) return
  confirmHtml.value = `将批量撤销 ${nExp.value} 条「过期疑似」= 全部认可源头新值`
}

async function batchDo() {
  confirmHtml.value = ''
  try {
    const r = await jpost<{ revoked?: number }>('/api/adjust/expired/revoke_all', {})
    ElMessage.success('已批量撤销 ' + (r.revoked || 0) + ' 条')
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error(String(e))
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新台账</el-button>
      <el-checkbox v-model="expOnly">只看过期疑似</el-checkbox>
      <el-button v-if="nExp" type="warning" size="small" @click="batchAsk">一键听源头新值（批量撤销过期疑似）</el-button>
      <span class="muted">共 {{ list.length }} 条（过期疑似 {{ nExp }}）</span>
    </div>
    <div class="admin-note">过期疑似（红）= 源头已改、我的调整未套用，页面现用源头新值。处理：「坚持我的数」或「撤销」。</div>
    <el-alert v-if="confirmHtml" type="warning" :closable="false" style="margin-bottom: 10px">
      {{ confirmHtml }}
      <el-button size="small" type="primary" style="margin-left: 8px" @click="batchDo">确认保存</el-button>
      <el-button size="small" @click="confirmHtml = ''">取消</el-button>
    </el-alert>

    <el-table :data="shown" v-loading="loading" border stripe height="calc(100vh - 280px)"
      :row-class-name="rowClassName">
      <el-table-column prop="id" label="id" width="70" />
      <el-table-column prop="创建时间" label="时间" width="160" />
      <el-table-column prop="经手人" label="操作账号" width="100" />
      <el-table-column prop="目标表" label="目标表" width="120" />
      <el-table-column prop="字段" label="字段" width="100" />
      <el-table-column label="原值→新值" min-width="160">
        <template #default="{ row }">{{ row['原值'] }} → {{ row['新值'] }}</template>
      </el-table-column>
      <el-table-column prop="类型" label="类型" width="80" />
      <el-table-column prop="状态" label="状态" width="100" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row['状态'] === '过期疑似' && row['类型'] === '改值'" size="small" @click="rearm(row.id)">坚持我的数</el-button>
          <el-button v-if="row['状态'] !== '已撤销'" size="small" text @click="revoke(row.id)">撤销</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
:deep(.exp-row) { --el-table-tr-bg-color: #3b1d1d; }
</style>
