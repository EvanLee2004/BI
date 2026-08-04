<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'
import { useClientPager } from '../composables/useClientPager'

const reloadDash = inject<() => void>('reloadDash', () => {})

type Adj = {
  id: number
  创建时间?: string
  经手人?: string
  目标表?: string
  定位键?: string
  字段?: string
  原值?: string
  新值?: string
  原因?: string
  类型?: string
  状态?: string
  订单号?: string
  客户?: string
  销售?: string
}

const list = ref<Adj[]>([])
const expOnly = ref(false)
/** 3.7.13 A2：按 SO / 客户 / 定位键 / 原因 文本搜索 */
const searchQ = ref('')
const confirmHtml = ref('')
const loading = ref(false)

const filtered = computed(() => {
  let rows = list.value
  if (expOnly.value) {
    rows = rows.filter((a) => a['状态'] === '过期疑似')
  }
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((a) => {
    const bag = [
      a['订单号'],
      a['客户'],
      a['销售'],
      a['定位键'],
      a['原因'],
      a['字段'],
      a['目标表'],
      a['经手人'],
    ]
      .map((x) => String(x || '').toLowerCase())
      .join(' ')
    return bag.includes(q)
  })
})

const nExp = computed(() => list.value.filter((a) => a['状态'] === '过期疑似').length)
const { page, pages, pageRows, pageInfo, resetPage, prevPage, nextPage } = useClientPager(filtered)
watch([expOnly, searchQ], () => resetPage())

function rowClassName({ row }: { row: Adj }) {
  return row['状态'] === '过期疑似' ? 'exp-row' : ''
}

/** 原值=新值 的过期疑似：提示可直接撤销 */
function sameValueTip(row: Adj): boolean {
  if (row['状态'] !== '过期疑似') return false
  const a = String(row['原值'] ?? '').trim()
  const b = String(row['新值'] ?? '').trim()
  return a !== '' && a === b
}

async function load() {
  loading.value = true
  try {
    list.value = await jget('/api/v1/admin/adjustments')
    resetPage()
  } catch (e) {
    ElMessage.error(String(e))
  } finally {
    loading.value = false
  }
}

async function revoke(id: number) {
  let reason = ''
  try {
    // 任务书63·H-03：可选理由（可留空）
    const { value } = await ElMessageBox.prompt(
      '撤销该调整？（=认可源头新值）。理由可选，可留空。',
      '确认撤销',
      { inputPlaceholder: '理由（可选）', inputValue: '', confirmButtonText: '确认撤销', cancelButtonText: '取消' },
    )
    reason = String(value || '').trim()
  } catch {
    return
  }
  try {
    await jpost(`/api/v1/admin/adjust/${id}/revoke`, { reason })
    ElMessage.success('已撤销')
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error(String(e))
  }
}

async function rearm(id: number) {
  const a: Adj = list.value.find((x) => x.id === id) || { id }
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      `坚持我的数？\n${a['目标表'] || ''} · ${a['字段'] || ''}：将继续使用「${a['新值'] || ''}」\n理由可选，可留空。`,
      '确认坚持',
      { inputPlaceholder: '理由（可选）', inputValue: '', confirmButtonText: '坚持我的数', cancelButtonText: '取消' },
    )
    reason = String(value || '').trim()
  } catch {
    return
  }
  try {
    await jpost(`/api/v1/admin/adjust/${id}/rearm`, { reason })
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
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('批量撤销过期疑似。理由可选，可留空。', '批量听源头', {
      inputPlaceholder: '理由（可选）',
      inputValue: '',
      confirmButtonText: '确认批量撤销',
      cancelButtonText: '取消',
    })
    reason = String(value || '').trim()
  } catch {
    return
  }
  try {
    const r = await jpost<{ revoked?: number }>('/api/v1/admin/adjust/expired/revoke_all', { reason })
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
      <el-checkbox v-model="expOnly">只显示过期疑似</el-checkbox>
      <el-input
        v-model="searchQ"
        placeholder="搜 SO/客户/定位键/原因…"
        clearable
        style="width: 240px"
      />
      <el-button v-if="nExp" type="warning" size="small" @click="batchAsk">一键听源头新值（批量撤销过期疑似）</el-button>
      <span class="muted">{{ pageInfo }}（过期疑似 {{ nExp }}）</span>
      <el-button size="small" :disabled="page <= 1 || loading" @click="prevPage">上一页</el-button>
      <el-button size="small" :disabled="page >= pages || loading" @click="nextPage">下一页</el-button>
    </div>
    <div class="admin-note">
      <b>过期疑似</b>＝智云/台账源头又改了数，你以前改的那条还没重新套上；页面<strong>当前用的是源头新值</strong>。
      处理方式：「坚持我的数」（继续用你的新值）或「撤销」（认可源头）。可用订单号(SO)/定位键对上原单。
      若原值=新值，说明已与源头一致，直接撤销即可清掉黄灯。
    </div>
    <el-alert v-if="confirmHtml" type="warning" :closable="false" style="margin-bottom: 10px">
      {{ confirmHtml }}
      <el-button size="small" type="primary" style="margin-left: 8px" @click="batchDo">确认保存</el-button>
      <el-button size="small" @click="confirmHtml = ''">取消</el-button>
    </el-alert>

    <div v-if="!loading && !list.length" class="empty-guide" data-testid="ledger-empty">
      <div class="empty-ico" aria-hidden="true">📋</div>
      <p class="empty-title">暂无数据调整记录</p>
      <p class="empty-desc">
        在「数据调整」改数或删行后，记录会出现在这里，可撤销或处理过期疑似。
      </p>
      <el-button type="primary" round @click="$router.push('/admin/edit/detail?table=收入明细')">
        去数据调整
      </el-button>
    </div>
    <div v-else-if="!loading && list.length && !filtered.length" class="empty-guide">
      <p class="empty-title">无匹配记录</p>
      <p class="empty-desc">换个 SO / 客户 / 定位键关键词，或关掉「只显示过期疑似」。</p>
    </div>
    <el-table
      v-else
      :data="pageRows"
      v-loading="loading"
      border
      stripe
      height="calc(100vh - 280px)"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="id" label="id" width="70" />
      <el-table-column prop="创建时间" label="时间" width="160" />
      <el-table-column
        prop="经手人"
        label="操作账号"
        width="100"
        :filters="[...new Set(filtered.map((r) => String(r['经手人'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Adj) => String(row['经手人'] || '') === v"
      />
      <el-table-column
        prop="目标表"
        label="目标表"
        width="110"
        :filters="[...new Set(filtered.map((r) => String(r['目标表'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Adj) => String(row['目标表'] || '') === v"
      />
      <el-table-column prop="订单号" label="SO/订单号" min-width="120" show-overflow-tooltip />
      <el-table-column prop="客户" label="客户" min-width="110" show-overflow-tooltip />
      <el-table-column prop="销售" label="销售" width="90" show-overflow-tooltip />
      <el-table-column prop="定位键" label="定位键" min-width="120" show-overflow-tooltip />
      <el-table-column
        prop="字段"
        label="字段"
        width="100"
        :filters="[...new Set(filtered.map((r) => String(r['字段'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Adj) => String(row['字段'] || '') === v"
      />
      <el-table-column label="原值→新值" min-width="160">
        <template #default="{ row }">
          {{ row['原值'] }} → {{ row['新值'] }}
          <span v-if="sameValueTip(row)" class="same-tip" title="原值=新值，可直接撤销清黄灯">（已与源头一致）</span>
        </template>
      </el-table-column>
      <el-table-column prop="原因" label="原因" min-width="120" show-overflow-tooltip />
      <el-table-column
        prop="类型"
        label="类型"
        width="80"
        :filters="[...new Set(filtered.map((r) => String(r['类型'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Adj) => String(row['类型'] || '') === v"
      />
      <el-table-column
        prop="状态"
        label="状态"
        width="100"
        :filters="[...new Set(filtered.map((r) => String(r['状态'] || '')).filter(Boolean))].map((t) => ({ text: t, value: t }))"
        :filter-method="(v: string, row: Adj) => String(row['状态'] || '') === v"
      />
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
.muted { color: var(--admin-mut); font-size: 13px; }
:deep(.exp-row) { --el-table-tr-bg-color: var(--admin-exp-row); }
.same-tip { color: var(--admin-mut); font-size: 12px; margin-left: 4px; }
.empty-guide {
  margin-top: 48px;
  text-align: center;
  padding: 32px 16px;
  border: 1px dashed var(--admin-line);
  border-radius: 12px;
  background: var(--admin-empty-bg);
}
.empty-ico { font-size: 36px; line-height: 1; margin-bottom: 12px; }
.empty-title { font-size: 16px; font-weight: 600; margin: 0 0 8px; color: var(--admin-ink); }
.empty-desc { margin: 0 auto 16px; max-width: 420px; font-size: 13px; line-height: 1.55; color: var(--admin-mut); }
</style>
