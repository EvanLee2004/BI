<script setup lang="ts">
import { inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { jget, jpost } from '../api'
import { BUDGET_METRICS, fmtThousands, parseAmount, wanToYuan, yuanToWan, yearOptions } from '../utils'

const dirtyApi = inject<{
  setBudgetDirty: (n: number) => void
  budgetDirty: { value: number }
}>('adminDirty')
const reloadDash = inject<() => void>('reloadDash', () => {})

const d = new Date()
const year = ref(String(Math.max(d.getFullYear(), 2026)))
const yOpts = yearOptions(false)
const scopes = ref<string[]>(['全公司'])
/** cells[metric][scope] = { orig, val, pct, wan } */
const cells = ref<Record<string, Record<string, { orig: string; val: string; pct: boolean; wan: boolean }>>>({})
const saving = ref(false)
const sumTips = ref<Record<string, { text: string; warn: boolean }>>({})

function recount() {
  let n = 0
  for (const mk of Object.keys(cells.value)) {
    for (const sc of Object.keys(cells.value[mk])) {
      const c = cells.value[mk][sc]
      if (c.val.replace(/,/g, '').trim() !== c.orig.replace(/,/g, '').trim()) n++
    }
  }
  dirtyApi?.setBudgetDirty(n)
  updateSumTips()
}

function updateSumTips() {
  const tips: Record<string, { text: string; warn: boolean }> = {}
  for (const it of BUDGET_METRICS) {
    if (!it.sumBu) continue
    let buSum = 0
    let has = false
    for (const sc of scopes.value) {
      if (sc === '全公司') continue
      const c = cells.value[it.k]?.[sc]
      if (!c) continue
      const cur = c.val.replace(/,/g, '').trim()
      if (cur === '') continue
      const num = Number(cur)
      if (isNaN(num)) continue
      buSum += num
      has = true
    }
    if (!has) {
      tips[it.k] = { text: '', warn: false }
      continue
    }
    const co = cells.value[it.k]?.['全公司']
    const coRaw = co ? co.val.replace(/,/g, '').trim() : ''
    const coN = coRaw === '' ? null : Number(coRaw)
    const text = '各 BU 合计 ' + fmtThousands(Math.round(buSum * 1e2) / 1e2) + ' 万'
    const warn = coN != null && !isNaN(coN) && buSum > coN + 1e-9
    tips[it.k] = { text, warn }
  }
  sumTips.value = tips
}

async function load() {
  let bus: { name: string }[] = []
  try {
    const d0 = await jget<{ bus?: { name: string }[] }>('/api/bu_config')
    bus = d0.bus || []
  } catch {
    /* ignore */
  }
  scopes.value = ['全公司'].concat(bus.map((b) => b.name).filter(Boolean))
  const cur = await jget<{ 指标: string; 范围?: string; 金额: unknown }[]>(
    `/api/budget?year=${encodeURIComponent(year.value)}`,
  )
  const map: Record<string, Record<string, unknown>> = {}
  ;(cur || []).forEach((x) => {
    const k = x['指标']
    if (!k || k === '费用年预算') return
    const sc = x['范围'] || '全公司'
    if (!map[k]) map[k] = {}
    map[k][sc] = x['金额']
  })
  const next: typeof cells.value = {}
  for (const it of BUDGET_METRICS) {
    next[it.k] = {}
    for (const sc of scopes.value) {
      const old = map[it.k]?.[sc]
      let orig = ''
      let val = ''
      if (old != null && old !== '') {
        if (it.pct) {
          orig = String(old)
          val = String(old)
        } else if (it.wan) {
          const w = yuanToWan(old)
          orig = String(w)
          val = fmtThousands(w)
        } else {
          orig = String(old)
          val = fmtThousands(old)
        }
      }
      next[it.k][sc] = { orig, val, pct: it.pct, wan: it.wan }
    }
  }
  cells.value = next
  recount()
}

async function safeLoad() {
  if (dirtyApi?.budgetDirty.value) {
    try {
      await ElMessageBox.confirm('有未保存修改，确定重新查询？', '提示')
    } catch {
      return
    }
  }
  await load()
}

async function discard() {
  if (!dirtyApi?.budgetDirty.value) return
  try {
    await ElMessageBox.confirm('放弃业绩目标未保存修改？', '确认')
  } catch {
    return
  }
  await load()
}

async function save() {
  const budgets: { 指标: string; 金额: number; 范围: string; 年份: string }[] = []
  for (const it of BUDGET_METRICS) {
    for (const sc of scopes.value) {
      const c = cells.value[it.k]?.[sc]
      if (!c) continue
      const cur = c.val.replace(/,/g, '').trim()
      const orig = c.orig.replace(/,/g, '').trim()
      if (cur === orig || cur === '') continue
      let n = parseAmount(c.val)
      if (isNaN(n)) {
        ElMessage.error(`「${it.label} · ${sc}」数值无效`)
        return
      }
      if (c.pct) {
        if (n < 0 || n > 100) {
          ElMessage.error(`「${it.label} · ${sc}」请填 0~100`)
          return
        }
      } else if (n < 0) {
        ElMessage.error(`「${it.label} · ${sc}」不能为负`)
        return
      }
      if (c.wan) {
        if (n > 0 && n < 10) {
          try {
            await ElMessageBox.confirm(`「${it.label} · ${sc}」=${n} 万，目标似乎过小，仍保存？`, '确认')
          } catch {
            return
          }
        }
        n = wanToYuan(n)
      }
      budgets.push({ 指标: it.k, 金额: n, 范围: sc, 年份: year.value })
    }
  }
  if (!budgets.length) {
    ElMessage.info('没有需要保存的更改')
    return
  }
  saving.value = true
  try {
    await jpost('/api/budget_batch', { items: budgets })
    dirtyApi?.setBudgetDirty(0)
    ElMessage.success(`✓ 已保存 ${budgets.length} 项业绩目标并重算`)
    reloadDash()
    await load()
  } catch (e) {
    ElMessage.error('保存失败：' + String(e))
  } finally {
    saving.value = false
  }
}

function displayCur(it: (typeof BUDGET_METRICS)[number], sc: string): string {
  const c = cells.value[it.k]?.[sc]
  if (!c || c.orig === '') return '（未填）'
  if (it.pct) return c.orig + '%'
  if (it.wan) return fmtThousands(c.orig) + ' 万'
  return fmtThousands(c.orig)
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select v-model="year" style="width: 110px">
        <el-option v-for="o in yOpts" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-button type="primary" @click="safeLoad">查询</el-button>
      <span class="muted">金额填万元、毛利率填百分数；存储键名不变。</span>
    </div>
    <div class="admin-note">🎯 业绩目标 · 下单/回款填<strong>万元</strong>，毛利率填百分数。年目标行在全公司列旁显示各 BU 合计。</div>

    <div class="matrix-wrap">
      <table class="b-matrix">
        <thead>
          <tr>
            <th class="b-metric">指标</th>
            <th v-for="sc in scopes" :key="sc">{{ sc === '全公司' ? '全公司' : 'BU · ' + sc }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in BUDGET_METRICS" :key="it.k">
            <td class="b-metric">
              <div class="b-lab">{{ it.label }}</div>
              <div class="muted b-tip">{{ it.tip }}</div>
            </td>
            <td v-for="sc in scopes" :key="sc">
              <div class="b-cur muted">{{ displayCur(it, sc) }}</div>
              <div class="b-edit">
                <el-input
                  v-if="cells[it.k]?.[sc]"
                  v-model="cells[it.k][sc].val"
                  size="small"
                  :placeholder="it.wan ? '如 8,000' : '如 35'"
                  style="width: 110px"
                  @input="recount"
                />
                <span v-if="it.pct" class="pct">%</span>
                <span v-else-if="it.wan" class="pct">万</span>
              </div>
              <div
                v-if="it.sumBu && sc === '全公司' && sumTips[it.k]?.text"
                class="b-sum-tip"
                :class="{ warn: sumTips[it.k]?.warn }"
              >
                {{ sumTips[it.k]?.text }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="dirtyApi && dirtyApi.budgetDirty.value > 0" class="admin-dirty-bar">
      <span>有 <b>{{ dirtyApi.budgetDirty.value }}</b> 项未保存</span>
      <el-button @click="discard">放弃更改</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存业绩目标</el-button>
    </div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.muted { color: var(--admin-mut, #94a3b8); font-size: 12px; }
.matrix-wrap { overflow: auto; max-width: 100%; }
.b-matrix { border-collapse: collapse; width: 100%; font-size: 12.5px; }
.b-matrix th, .b-matrix td { border: 1px solid var(--admin-line, #2a364d); padding: 8px 10px; vertical-align: top; }
.b-lab { font-weight: 600; }
.b-tip { margin-top: 2px; }
.b-cur { margin-bottom: 4px; }
.b-edit { display: flex; align-items: center; gap: 4px; }
.pct { font-size: 12px; color: var(--admin-mut); }
.b-sum-tip { margin-top: 4px; font-size: 11.5px; color: var(--admin-mut); }
.b-sum-tip.warn { color: #fbbf24; font-weight: 600; }
</style>
