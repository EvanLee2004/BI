<script setup lang="ts">
import { inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'
import { fmtThousands, parseAmount, yearOptions, monthOptions, ymString } from '../utils'

const dirtyApi = inject<{
  setFormDirty: (n: number) => void
  formDirty: { value: number }
}>('adminDirty')
const reloadDash = inject<() => void>('reloadDash', () => {})

const d = new Date()
const year = ref(String(Math.max(d.getFullYear(), 2026)))
const month = ref(String(d.getMonth() + 1))
const scope = ref('全公司')
const buNames = ref<string[]>([])
const items = ref<string[]>([])
const manualRows = ref<{ item: string; cur: string; orig: string; val: string }[]>([])
const allocRows = ref<{ bu: string; orig: string; val: string }[]>([])
const allocTotal = ref('—')
const allocInherit = ref('')
const allocSumText = ref('')
const detaxRows = ref<{ cat: string; amount: string; orig: string; val: string }[]>([])
const showAlloc = ref(false)
const showDetax = ref(false)
const saving = ref(false)
const yOpts = yearOptions(false)
const mOpts = monthOptions(false)

function recountDirty() {
  let n = 0
  for (const r of manualRows.value) {
    if (r.val.replace(/,/g, '').trim() !== r.orig.replace(/,/g, '').trim()) n++
  }
  for (const r of allocRows.value) {
    if (r.val.trim() !== r.orig.trim()) n++
  }
  for (const r of detaxRows.value) {
    if (r.val.trim() !== r.orig.trim()) n++
  }
  dirtyApi?.setFormDirty(n)
  aSum()
}

function aSum() {
  if (!showAlloc.value) {
    allocSumText.value = ''
    return
  }
  let sum = 0
  let bad = false
  for (const r of allocRows.value) {
    const cur = r.val.trim()
    if (cur === '') continue
    const n = Number(cur)
    if (isNaN(n) || n < 0 || n > 100) {
      bad = true
      break
    }
    sum += n
  }
  sum = Math.round(sum * 10) / 10
  if (bad) {
    allocSumText.value = '有比例不是 0~100 的数字'
    return
  }
  if (sum > 100.05) {
    allocSumText.value = `本月合计 ${sum}%，超过 100%——保存会被拒绝`
    return
  }
  const remain = Math.round((100 - sum) * 10) / 10
  allocSumText.value = `本月合计 ${sum}% · 剩余 ${remain}% 留公司层`
}

async function loadScopes() {
  try {
    const d0 = await jget<{ bus?: { name: string }[] }>('/api/bu_config')
    buNames.value = (d0.bus || []).map((b) => b.name).filter(Boolean)
  } catch {
    buNames.value = []
  }
}

async function loadItems() {
  try {
    const d0 = await jget<{ items?: string[] }>('/api/manual_items')
    items.value = d0.items || []
  } catch {
    items.value = []
  }
}

async function load() {
  const m = ymString(year.value, month.value)
  if (!m) return
  await loadScopes()
  if (!items.value.length) await loadItems()
  const cur = await jget<{ 项目: string; 金额: unknown }[]>(
    `/api/manual?month=${encodeURIComponent(m)}&scope=${encodeURIComponent(scope.value)}`,
  )
  const map: Record<string, unknown> = {}
  ;(cur || []).forEach((x) => {
    map[x['项目']] = x['金额']
  })
  manualRows.value = items.value.map((it) => {
    const orig = map[it] != null ? String(map[it]) : ''
    return {
      item: it,
      cur: map[it] != null ? fmtThousands(map[it]) : '（空=0）',
      orig,
      val: map[it] != null ? fmtThousands(map[it]) : '',
    }
  })
  await loadAlloc()
  await loadDetax()
  recountDirty()
}

async function loadAlloc() {
  const m = ymString(year.value, month.value)
  if (scope.value !== '全公司' || !m) {
    showAlloc.value = false
    return
  }
  try {
    const d0 = await jget<{
      bus?: string[]
      rates?: Record<string, number>
      month_total_disp?: string
      inherited_from?: string
    }>(`/api/alloc_rates?month=${encodeURIComponent(m)}`)
    if (!d0.bus?.length) {
      showAlloc.value = false
      return
    }
    showAlloc.value = true
    allocTotal.value = d0.month_total_disp || '0.00'
    allocInherit.value = d0.inherited_from
      ? `本月未单独填写，当前沿用 ${d0.inherited_from} 的比例（改动保存后从本月起生效）`
      : ''
    allocRows.value = d0.bus.map((bn) => {
      const v = d0.rates && d0.rates[bn] != null ? String(d0.rates[bn]) : ''
      return { bu: bn, orig: v, val: v }
    })
  } catch {
    showAlloc.value = false
  }
}

async function loadDetax() {
  if (scope.value !== '全公司') {
    showDetax.value = false
    return
  }
  try {
    const d0 = await jget<{
      categories?: { category: string; amount_disp?: string }[]
      rates?: Record<string, number>
    }>('/api/detax_rates')
    if (!d0.categories?.length) {
      showDetax.value = false
      return
    }
    showDetax.value = true
    detaxRows.value = d0.categories.map((c) => {
      const cat = c.category
      const v = d0.rates && d0.rates[cat] != null ? String(d0.rates[cat]) : ''
      return { cat, amount: c.amount_disp || '', orig: v, val: v }
    })
  } catch {
    showDetax.value = false
  }
}

async function safeLoad() {
  if (dirtyApi?.formDirty.value) {
    try {
      await ElMessageBox.confirm('有未保存修改，确定重新查询？', '提示')
    } catch {
      return
    }
  }
  await load()
}

async function discard() {
  if (!dirtyApi?.formDirty.value) return
  try {
    await ElMessageBox.confirm('放弃全部未保存修改？', '确认')
  } catch {
    return
  }
  await load()
}

async function saveAll() {
  const m = ymString(year.value, month.value)
  const manuals: { 项目: string; 金额: number; 范围: string }[] = []
  for (const r of manualRows.value) {
    const cur = r.val.replace(/,/g, '').trim()
    const orig = r.orig.replace(/,/g, '').trim()
    if (cur === orig || cur === '') continue
    const n = parseAmount(r.val)
    if (isNaN(n) || n < 0) {
      ElMessage.error(`「${r.item}」金额无效`)
      return
    }
    manuals.push({ 项目: r.item, 金额: n, 范围: scope.value })
  }
  const allocs: Record<string, number | null> = {}
  let allocSum = 0
  let allocChanged = 0
  for (const r of allocRows.value) {
    const cur = r.val.trim()
    const orig = r.orig.trim()
    if (cur !== '') {
      const n = Number(cur)
      if (isNaN(n) || n < 0 || n > 100) {
        ElMessage.error(`BU「${r.bu}」比例须为 0~100`)
        return
      }
      allocSum += n
    }
    if (cur === orig) continue
    allocs[r.bu] = cur === '' ? null : Number(cur)
    allocChanged++
  }
  if (allocChanged && allocSum > 100.05) {
    ElMessage.error('比例合计超过 100%')
    return
  }
  const detax: Record<string, number | null> = {}
  let detaxChanged = 0
  for (const r of detaxRows.value) {
    const cur = r.val.trim()
    const orig = r.orig.trim()
    if (cur !== '') {
      const n = Number(cur)
      if (isNaN(n) || n < 0 || n > 100) {
        ElMessage.error(`「${r.cat}」去税率须为 0~100`)
        return
      }
    }
    if (cur === orig) continue
    detax[r.cat] = cur === '' ? null : Number(cur)
    detaxChanged++
  }
  if (!manuals.length && !allocChanged && !detaxChanged) {
    ElMessage.info('没有需要保存的更改')
    return
  }
  saving.value = true
  try {
    if (manuals.length) await jpost('/api/manual_batch', { 归属月: m, 范围: scope.value, items: manuals })
    if (allocChanged) await jpost('/api/alloc_rates', { 归属月: m, rates: allocs })
    if (detaxChanged) await jpost('/api/detax_rates', { rates: detax })
    dirtyApi?.setFormDirty(0)
    ElMessage.success(`✓ 已保存 ${manuals.length + allocChanged + detaxChanged} 项并重算`)
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error('保存失败：' + String(e))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select v-model="year" style="width: 110px">
        <el-option v-for="o in yOpts" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="month" style="width: 100px">
        <el-option v-for="o in mOpts" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="scope" style="width: 160px" @change="safeLoad">
        <el-option label="全公司" value="全公司" />
        <el-option v-for="n in buNames" :key="n" :label="'BU · ' + n" :value="n" />
      </el-select>
      <el-button type="primary" @click="safeLoad">查询</el-button>
      <span class="muted">金额填元（千分位）；当月未填=0。全公司与各 BU 手填分开存。</span>
    </div>
    <div class="admin-note">人工填写：人力/补充等。可批量改数，离开会提醒。</div>

    <el-table :data="manualRows" border stripe size="small" style="width: 100%; max-width: 720px">
      <el-table-column prop="item" label="项目" min-width="160" />
      <el-table-column prop="cur" label="当前金额(元)" width="140" />
      <el-table-column label="新值(元)" width="180">
        <template #default="{ row }">
          <el-input v-model="row.val" size="small" placeholder="如 1,000,000" @input="recountDirty" />
        </template>
      </el-table-column>
    </el-table>

    <div v-if="showAlloc" style="margin-top: 20px">
      <h3>🏦 公共费用分摊比例（按月）</h3>
      <div class="admin-note">
        本月公共费用总额 <b>{{ allocTotal }}</b> 元。各 BU 填比例 %；合计可小于 100%。
      </div>
      <p class="muted">{{ allocInherit }}</p>
      <el-table :data="allocRows" border stripe size="small" style="max-width: 480px">
        <el-table-column prop="bu" label="BU" />
        <el-table-column label="本月分摊比例(%)">
          <template #default="{ row }">
            <el-input v-model="row.val" size="small" placeholder="未填=沿用上次" @input="recountDirty" />
          </template>
        </el-table-column>
      </el-table>
      <p class="muted">{{ allocSumText }}</p>
    </div>

    <div v-if="showDetax" style="margin-top: 20px">
      <h3>💧 费用去税率（按类别·全公司）</h3>
      <div class="admin-note">能抵扣进项的费用可填增值税率 %；默认全空=不去税。</div>
      <el-table :data="detaxRows" border stripe size="small" style="max-width: 640px">
        <el-table-column prop="cat" label="费用类别" min-width="140" />
        <el-table-column prop="amount" label="全年含税金额" width="140" />
        <el-table-column label="去税率(%)" width="140">
          <template #default="{ row }">
            <el-input v-model="row.val" size="small" placeholder="留空=不去税" @input="recountDirty" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="dirtyApi && dirtyApi.formDirty.value > 0" class="admin-dirty-bar">
      <span>有 <b>{{ dirtyApi.formDirty.value }}</b> 项未保存</span>
      <el-button @click="discard">放弃更改</el-button>
      <el-button type="primary" :loading="saving" @click="saveAll">保存全部更改</el-button>
    </div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 13px; }
h3 { font-size: 15px; margin: 12px 0 8px; }
</style>
