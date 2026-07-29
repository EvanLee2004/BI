<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
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
/** 2.6.9 U-1：手填多列（全公司+各BU），去掉顶部 scope 下拉 */
const scopes = ref<string[]>(['全公司'])
const buNames = ref<string[]>([])
const items = ref<string[]>([])
/** manualCells[item][scope] = { orig, val } 元 */
const manualCells = ref<Record<string, Record<string, { orig: string; val: string }>>>({})
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

/** 顶栏当前编辑月（查询后即本页数据所属月） */
const ymLabel = computed(() => ymString(year.value, month.value) || '—')

function allocCell(bu: string) {
  return allocRows.value.find((r) => r.bu === bu)
}

function recountDirty() {
  let n = 0
  for (const it of items.value) {
    for (const sc of scopes.value) {
      const c = manualCells.value[it]?.[sc]
      if (!c) continue
      if (c.val.replace(/,/g, '').trim() !== c.orig.replace(/,/g, '').trim()) n++
    }
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
    const d0 = await jget<{ bus?: { name: string }[] }>('/api/v1/admin/bu_config')
    buNames.value = (d0.bus || []).map((b) => b.name).filter(Boolean)
  } catch {
    buNames.value = []
  }
}

async function loadItems() {
  try {
    const d0 = await jget<{ items?: string[] }>('/api/v1/admin/manual_items')
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
  scopes.value = ['全公司'].concat(buNames.value)
  const next: typeof manualCells.value = {}
  for (const it of items.value) next[it] = {}
  await Promise.all(
    scopes.value.map(async (sc) => {
      const cur = await jget<{ 项目: string; 金额: unknown }[]>(
        `/api/v1/admin/manual?month=${encodeURIComponent(m)}&scope=${encodeURIComponent(sc)}`,
      )
      const map: Record<string, unknown> = {}
      ;(cur || []).forEach((x) => {
        map[x['项目']] = x['金额']
      })
      for (const it of items.value) {
        const orig = map[it] != null ? String(map[it]) : ''
        next[it][sc] = {
          orig,
          val: map[it] != null ? fmtThousands(map[it]) : '',
        }
      }
    }),
  )
  manualCells.value = next
  await loadAlloc()
  await loadDetax()
  recountDirty()
}

async function loadAlloc() {
  const m = ymString(year.value, month.value)
  if (!m) {
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
    }>(`/api/v1/admin/alloc_rates?month=${encodeURIComponent(m)}`)
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
  // 去税率始终全公司口径（U-1 去掉 scope 下拉后仍按公司层加载）
  if (!ymString(year.value, month.value)) {
    showDetax.value = false
    return
  }
  try {
    const d0 = await jget<{
      categories?: { category: string; amount_disp?: string }[]
      rates?: Record<string, number>
    }>('/api/v1/admin/detax_rates')
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
  for (const it of items.value) {
    for (const sc of scopes.value) {
      const c = manualCells.value[it]?.[sc]
      if (!c) continue
      const cur = c.val.replace(/,/g, '').trim()
      const orig = c.orig.replace(/,/g, '').trim()
      if (cur === orig) continue
      // 清空已填 → 写 0（与「空=0」口径一致）
      if (cur === '') {
        if (orig !== '' && orig !== '0') manuals.push({ 项目: it, 金额: 0, 范围: sc })
        continue
      }
      const n = parseAmount(c.val)
      if (isNaN(n) || n < 0) {
        ElMessage.error(`「${it} · ${sc}」金额无效`)
        return
      }
      manuals.push({ 项目: it, 金额: n, 范围: sc })
    }
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
    // 批量可带行内 范围；顶层 范围 仅作缺省
    if (manuals.length) await jpost('/api/v1/admin/manual_batch', { 归属月: m, 范围: '全公司', items: manuals })
    if (allocChanged || ovChanged || frChanged) {
      const body: Record<string, unknown> = { 归属月: m }
      if (allocChanged) body.ratios = allocs
      if (ovChanged) body.overrides = overrides
      if (frChanged) body.detail_rules = detail_rules
      await jpost('/api/v1/admin/alloc_rates', body)
    }
    if (detaxChanged) await jpost('/api/v1/admin/detax_rates', { rates: detax })
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
  <div class="mf-page" data-testid="manual-page">
    <div class="toolbar">
      <el-select v-model="year" style="width: 110px">
        <el-option v-for="o in yOpts" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="month" style="width: 100px">
        <el-option v-for="o in mOpts" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-button type="primary" @click="safeLoad">查询</el-button>
      <span class="mf-ym" data-testid="manual-ym">当前编辑：{{ ymLabel }}</span>
      <span class="muted">金额填元（千分位）；空=0。改月后请点查询。</span>
    </div>

    <!-- ① 人力/补充：按月 · 全公司+各BU 横填 -->
    <section class="mf-card" data-testid="manual-multi-scope">
      <div class="mf-card-h">
        <h3>① 人工项目（按月 · 全公司 + 各 BU）</h3>
        <p class="muted">列=全公司与各业务线；直接横填。保存后进对应范围。</p>
      </div>
      <div class="matrix-wrap">
        <table class="b-matrix">
          <thead>
            <tr>
              <th class="b-metric">项目</th>
              <th v-for="sc in scopes" :key="sc">{{ sc === '全公司' ? '全公司' : 'BU · ' + sc }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it">
              <td class="b-metric">{{ it }}</td>
              <td v-for="sc in scopes" :key="sc">
                <div class="b-cur muted" v-if="manualCells[it]?.[sc]?.orig">
                  {{ fmtThousands(manualCells[it][sc].orig) }} 元
                </div>
                <div class="b-cur muted" v-else>（空=0）</div>
                <el-input
                  v-if="manualCells[it]?.[sc]"
                  v-model="manualCells[it][sc].val"
                  size="small"
                  placeholder="如 1,000,000"
                  class="mf-input"
                  @input="recountDirty"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ② 公共费用：按月 · 进各 BU（默认比例 + 明细精配） -->
    <section v-if="showAlloc" class="mf-card" data-testid="alloc-panel">
      <div class="mf-card-h">
        <h3>② 公共费用分摊（按月 · 进各 BU）</h3>
        <p class="muted">
          本月公共池总额 <b class="mf-em">{{ allocTotal }}</b> 元。
          默认比例：未精配明细走这里；明细精配：选「比例% / 金额元」后右侧各 BU 可填。
        </p>
        <p v-if="allocInherit" class="muted">{{ allocInherit }}</p>
      </div>

      <h4>默认分摊比例（% · 与上方同一套 BU）</h4>
      <div class="matrix-wrap" data-testid="alloc-default-ratios">
        <table class="b-matrix">
          <thead>
            <tr>
              <th class="b-metric">项</th>
              <th v-for="b in buNames" :key="b">BU · {{ b }}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="b-metric">默认比例 %</td>
              <td v-for="b in buNames" :key="b">
                <el-input
                  v-if="allocCell(b)"
                  v-model="allocCell(b)!.val"
                  size="small"
                  placeholder="未填=沿用"
                  class="mf-input"
                  @input="recountDirty"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted">{{ allocSumText }}</p>

      <h4>公共明细精配（台账降序 · 优先于默认比例）</h4>
      <p class="muted mf-tip">
        分摊方式选「默认」= 走上面默认比例，BU 列灰掉；
        选「比例%」或「金额元」后，可直接在各 BU 列填写（按月生效）。
      </p>
      <div class="matrix-wrap">
        <table class="b-matrix" data-testid="alloc-detail-table">
          <thead>
            <tr>
              <th class="b-metric">明细项</th>
              <th>本月金额(元)</th>
              <th>分摊方式</th>
              <th v-for="b in buNames" :key="b">BU · {{ b }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in detailRows" :key="row.category">
              <td class="b-metric">{{ row.category }}</td>
              <td>
                <template v-if="row.amount_editable">
                  <el-input
                    v-model="row.amount_val"
                    size="small"
                    :placeholder="row.amount_disp + '（覆盖）'"
                    class="mf-input"
                    @input="recountDirty"
                  />
                  <div class="muted b-cur">台账 {{ row.amount_disp }} · 手填</div>
                </template>
                <template v-else>
                  <span>{{ row.amount_disp }}</span>
                  <span class="muted"> · 自动</span>
                </template>
              </td>
              <td>
                <el-select
                  v-model="row.mode"
                  size="small"
                  clearable
                  placeholder="默认(走比例)"
                  class="mf-select"
                  @change="recountDirty"
                >
                  <el-option label="比例%" value="比例" />
                  <el-option label="金额元" value="金额" />
                </el-select>
              </td>
              <td v-for="b in buNames" :key="b">
                <el-input
                  v-model="row.bu_val[b]"
                  size="small"
                  :disabled="!row.mode"
                  :placeholder="row.mode === '金额' ? '元' : row.mode === '比例' ? '%' : '—'"
                  class="mf-input"
                  @input="recountDirty"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted" data-testid="alloc-summary">{{ allocByBuText }}</p>
    </section>

    <!-- ③ 去税：全局（不算月、不算 BU）——产品口径 -->
    <section v-if="showDetax" class="mf-card" data-testid="detax-panel">
      <div class="mf-card-h">
        <h3>③ 费用去税率（全局 · 不按月 · 不按 BU）</h3>
        <p class="muted">
          按「费用细类」填增值税率；<strong>全公司共用一套</strong>，算账时先对台账行去税，再进公共分摊/各 BU。
          参考金额为库内<strong>全年</strong>含税合计，不随上方月份切换。
        </p>
      </div>
      <div class="matrix-wrap">
        <table class="b-matrix" style="min-width: 480px; max-width: 720px">
          <thead>
            <tr>
              <th class="b-metric">费用类别</th>
              <th>全年含税金额</th>
              <th>去税率 %</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in detaxRows" :key="row.cat">
              <td class="b-metric">{{ row.cat }}</td>
              <td class="muted">{{ row.amount }}</td>
              <td>
                <el-input
                  v-model="row.val"
                  size="small"
                  placeholder="留空=不去税"
                  class="mf-input"
                  @input="recountDirty"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="dirtyApi && dirtyApi.formDirty.value > 0" class="admin-dirty-bar">
      <span>有 <b>{{ dirtyApi.formDirty.value }}</b> 项未保存（{{ ymLabel }}）</span>
      <el-button @click="discard">放弃更改</el-button>
      <el-button type="primary" :loading="saving" @click="saveAll">保存全部更改</el-button>
    </div>
  </div>
</template>

<style scoped>
.mf-page {
  padding-bottom: 24px;
  color: var(--admin-fg);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.mf-ym {
  font-size: 13px;
  font-weight: 600;
  color: var(--admin-cyan);
  padding: 4px 10px;
  border-radius: var(--admin-radius-sm);
  border: 1px solid var(--admin-line);
  background: var(--admin-panel2);
}
.muted {
  color: var(--admin-mut);
  font-size: 12.5px;
}
.mf-em {
  color: var(--admin-fg);
  font-weight: 600;
}
.mf-card {
  margin-bottom: 14px;
  padding: 14px 16px 16px;
  border-radius: var(--admin-radius);
  border: 1px solid var(--admin-line);
  background: var(--admin-panel);
}
.mf-card-h {
  margin-bottom: 10px;
}
.mf-card-h h3 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 650;
  color: var(--admin-fg);
}
.mf-card-h p {
  margin: 0;
  line-height: 1.5;
}
h4 {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--admin-us-title, var(--admin-fg));
}
.mf-tip {
  margin: 0 0 8px;
  line-height: 1.45;
}
.matrix-wrap {
  overflow-x: auto;
  max-width: 100%;
}
.b-matrix {
  border-collapse: collapse;
  width: 100%;
  min-width: 720px;
  font-size: 12.5px;
}
.b-matrix th,
.b-matrix td {
  border: 1px solid var(--admin-line);
  padding: 8px 10px;
  vertical-align: top;
}
.b-matrix th {
  background: var(--admin-panel2);
  color: var(--admin-fg);
  font-weight: 600;
  white-space: nowrap;
}
.b-metric {
  font-weight: 600;
  white-space: nowrap;
  min-width: 110px;
}
.b-cur {
  margin-bottom: 4px;
  font-size: 11.5px;
}
.mf-input {
  width: 120px;
  max-width: 100%;
}
.mf-select {
  width: 128px;
}
</style>
