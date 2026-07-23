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
const allocByBuText = ref('')
const remainCompany = ref('—')
/** 2.4.0 公共明细两轴行 */
type DetailRow = {
  category: string
  amount_disp: string
  amount_orig: string
  amount_val: string
  amount_editable: boolean
  amount_source: string
  mode_orig: string
  mode: string // '' | 比例 | 金额
  bu_orig: Record<string, string>
  bu_val: Record<string, string>
}
const detailRows = ref<DetailRow[]>([])
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
  for (const r of detailRows.value) {
    if (r.amount_editable && r.amount_val.replace(/,/g, '').trim() !== r.amount_orig.replace(/,/g, '').trim()) n++
    if ((r.mode || '') !== (r.mode_orig || '')) n++
    for (const b of buNames.value) {
      if ((r.bu_val[b] || '').trim() !== (r.bu_orig[b] || '').trim()) n++
    }
  }
  for (const r of detaxRows.value) {
    if (r.val.trim() !== r.orig.trim()) n++
  }
  dirtyApi?.setFormDirty(n)
  aSum()
  detailSumHint()
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
    allocSumText.value = '默认比例有不是 0~100 的数字'
    return
  }
  if (sum > 100.05) {
    allocSumText.value = `默认比例合计 ${sum}%，超过 100%——保存会被拒绝`
    return
  }
  const remain = Math.round((100 - sum) * 10) / 10
  allocSumText.value = `默认比例合计 ${sum}% · 剩余 ${remain}% 走公司层（未精配明细）`
}

function detailSumHint() {
  // 前端只做提示，不运算金额分摊；超额由后端拒
  const bad: string[] = []
  for (const r of detailRows.value) {
    if (!r.mode) continue
    let sum = 0
    for (const b of buNames.value) {
      const cur = (r.bu_val[b] || '').trim()
      if (cur === '') continue
      const n = Number(cur)
      if (isNaN(n) || n < 0) {
        bad.push(`${r.category} 有无效数字`)
        break
      }
      if (r.mode === '比例' && n > 100) {
        bad.push(`${r.category} 单 BU 比例>100`)
        break
      }
      sum += n
    }
    if (r.mode === '比例' && sum > 100.05) bad.push(`${r.category} 比例合计 ${sum.toFixed(1)}%>100`)
  }
  // 汇总串仍用后端 by_bu_disp（加载时）
  if (bad.length) {
    allocByBuText.value = '⚠ ' + bad.slice(0, 3).join('；')
  }
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
      ratios?: Record<string, number | null>
      month_total_disp?: string
      inherited_from?: string | null
      details?: {
        category: string
        amount_disp?: string
        amount_yuan?: number
        amount_editable?: boolean
        amount_source?: string
        mode?: string | null
        bu_values?: Record<string, number | null>
      }[]
      by_bu_disp?: Record<string, string>
      remain_company_disp?: string
    }>(`/api/alloc_ratios?month=${encodeURIComponent(m)}`)
    if (!d0.bus?.length) {
      showAlloc.value = false
      return
    }
    showAlloc.value = true
    allocTotal.value = d0.month_total_disp || '0.00'
    remainCompany.value = d0.remain_company_disp || '—'
    allocInherit.value = d0.inherited_from
      ? `默认比例：本月未单独填写，当前沿用 ${d0.inherited_from}（改动保存后从本月起生效）`
      : ''
    allocRows.value = d0.bus.map((bn) => {
      const raw = d0.ratios ? d0.ratios[bn] : null
      const v = raw != null && raw !== ('' as unknown) ? String(raw) : ''
      return { bu: bn, orig: v, val: v }
    })
    const parts = (d0.bus || []).map((b) => `${b} ${d0.by_bu_disp?.[b] || '0.00'}元`)
    allocByBuText.value = parts.length
      ? `各BU摊入：${parts.join(' · ')}；剩余留公司 ${remainCompany.value} 元`
      : ''
    detailRows.value = (d0.details || []).map((row) => {
      const bu_orig: Record<string, string> = {}
      const bu_val: Record<string, string> = {}
      for (const b of d0.bus || []) {
        const raw = row.bu_values?.[b]
        const s = raw != null && raw !== ('' as unknown) ? String(raw) : ''
        bu_orig[b] = s
        bu_val[b] = s
      }
      const amt =
        row.amount_source === 'override' && row.amount_yuan != null
          ? String(row.amount_yuan)
          : row.amount_editable
            ? row.amount_yuan != null && row.amount_source === 'override'
              ? String(row.amount_yuan)
              : ''
            : ''
      // 可填金额：orig/val 用覆盖值；只读展示 amount_disp
      const amount_orig =
        row.amount_editable && row.amount_source === 'override' && row.amount_yuan != null
          ? String(row.amount_yuan)
          : ''
      return {
        category: row.category,
        amount_disp: row.amount_disp || '0.00',
        amount_orig,
        amount_val: amount_orig,
        amount_editable: !!row.amount_editable,
        amount_source: row.amount_source || 'auto',
        mode_orig: row.mode || '',
        mode: row.mode || '',
        bu_orig,
        bu_val,
      }
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
        ElMessage.error(`BU「${r.bu}」默认比例须为 0~100`)
        return
      }
      allocSum += n
    }
    if (cur === orig) continue
    allocs[r.bu] = cur === '' ? null : Number(cur)
    allocChanged++
  }
  if (allocChanged && allocSum > 100.05) {
    ElMessage.error('默认比例合计超过 100%')
    return
  }

  const overrides: Record<string, number | null> = {}
  let ovChanged = 0
  const detail_rules: Record<string, { mode: string; values: Record<string, number | null> } | null> = {}
  let frChanged = 0
  for (const r of detailRows.value) {
    if (r.amount_editable) {
      const cur = r.amount_val.replace(/,/g, '').trim()
      const orig = r.amount_orig.replace(/,/g, '').trim()
      if (cur !== orig) {
        if (cur === '') {
          overrides[r.category] = null
        } else {
          const n = parseAmount(r.amount_val)
          if (isNaN(n) || n < 0) {
            ElMessage.error(`「${r.category}」手填金额无效`)
            return
          }
          overrides[r.category] = n
        }
        ovChanged++
      }
    }
    const modeCur = r.mode || ''
    const modeOrig = r.mode_orig || ''
    let buDirty = false
    const values: Record<string, number | null> = {}
    for (const b of buNames.value) {
      const cur = (r.bu_val[b] || '').trim()
      const orig = (r.bu_orig[b] || '').trim()
      if (cur !== orig) buDirty = true
      if (modeCur) {
        if (cur === '') values[b] = null
        else {
          const n = Number(cur)
          if (isNaN(n) || n < 0) {
            ElMessage.error(`「${r.category}」·${b} 值无效`)
            return
          }
          if (modeCur === '比例' && n > 100) {
            ElMessage.error(`「${r.category}」·${b} 比例须 0~100`)
            return
          }
          values[b] = n
        }
      }
    }
    if (modeCur !== modeOrig || buDirty) {
      if (!modeCur) {
        detail_rules[r.category] = null
      } else {
        // 校验比例合计
        if (modeCur === '比例') {
          let s = 0
          for (const v of Object.values(values)) {
            if (v != null) s += v
          }
          if (s > 100.05) {
            ElMessage.error(`「${r.category}」比例合计超过 100%`)
            return
          }
        }
        detail_rules[r.category] = { mode: modeCur, values }
      }
      frChanged++
    }
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
  const nSave = manuals.length + allocChanged + ovChanged + frChanged + detaxChanged
  if (!nSave) {
    ElMessage.info('没有需要保存的更改')
    return
  }
  saving.value = true
  try {
    if (manuals.length) await jpost('/api/manual_batch', { 归属月: m, 范围: scope.value, items: manuals })
    if (allocChanged || ovChanged || frChanged) {
      const body: Record<string, unknown> = { 归属月: m }
      if (allocChanged) body.ratios = allocs
      if (ovChanged) body.overrides = overrides
      if (frChanged) body.detail_rules = detail_rules
      await jpost('/api/alloc_ratios', body)
    }
    if (detaxChanged) await jpost('/api/detax_rates', { rates: detax })
    dirtyApi?.setFormDirty(0)
    ElMessage.success(`✓ 已保存 ${nSave} 项并重算`)
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

    <div v-if="showAlloc" style="margin-top: 20px" data-testid="alloc-panel">
      <h3>🏦 公共费用统一分摊（两轴）</h3>
      <div class="admin-note">
        本月公共费用总额 <b>{{ allocTotal }}</b> 元。顶部为默认比例（未精配明细走这里）；下方按明细项精配比例/金额。
      </div>
      <p class="muted">{{ allocInherit }}</p>
      <el-table :data="allocRows" border stripe size="small" style="max-width: 480px" data-testid="alloc-default-ratios">
        <el-table-column prop="bu" label="BU" />
        <el-table-column label="默认分摊比例(%)">
          <template #default="{ row }">
            <el-input v-model="row.val" size="small" placeholder="未填=沿用上次" @input="recountDirty" />
          </template>
        </el-table-column>
      </el-table>
      <p class="muted">{{ allocSumText }}</p>

      <h4 style="margin-top: 16px">公共明细（台账降序 · 精配优先）</h4>
      <el-table :data="detailRows" border stripe size="small" style="width: 100%" data-testid="alloc-detail-table">
        <el-table-column prop="category" label="明细项" min-width="120" fixed />
        <el-table-column label="本月金额(元)" min-width="140">
          <template #default="{ row }">
            <template v-if="row.amount_editable">
              <el-input
                v-model="row.amount_val"
                size="small"
                :placeholder="row.amount_disp + '（手填覆盖）'"
                @input="recountDirty"
              />
              <span class="muted" style="font-size: 11px">台账 {{ row.amount_disp }} · 〔手填〕</span>
            </template>
            <template v-else>
              <span>{{ row.amount_disp }}</span>
              <span class="muted" style="font-size: 11px"> 〔自动〕</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="分摊方式" width="130">
          <template #default="{ row }">
            <el-select v-model="row.mode" size="small" clearable placeholder="默认" @change="recountDirty">
              <el-option label="比例%" value="比例" />
              <el-option label="金额元" value="金额" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-for="b in buNames" :key="b" :label="b" min-width="100">
          <template #default="{ row }">
            <el-input
              v-model="row.bu_val[b]"
              size="small"
              :disabled="!row.mode"
              :placeholder="row.mode === '金额' ? '元' : row.mode === '比例' ? '%' : '—'"
              @input="recountDirty"
            />
          </template>
        </el-table-column>
      </el-table>
      <p class="muted" data-testid="alloc-summary">{{ allocByBuText }}</p>
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
h4 { font-size: 13px; margin: 8px 0; font-weight: 600; }
</style>
