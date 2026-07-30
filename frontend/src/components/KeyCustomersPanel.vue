<script setup lang="ts">
/**
 * 3.4.3 重点客户经营作战台 · Layer3
 * 四摘要卡 + 双结构条 + 三经营池 + 客户洞察（行动队列 / 最多三客比较）
 * 前端零金额求和、零档位判断、零业务占比；只渲染后端 VM。
 */
import '../styles/components/KeyCustomersPanel.css'
import { computed, reactive, ref, watch } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import DataModal from './base/DataModal.vue'
import RankBar from './base/RankBar.vue'
import EchartsHost from './charts/EchartsHost.vue'
import {
  animBlock,
  areaGradient,
  axisLabelStyle,
  chartMutedColor,
  chartTextColor,
  lineGlowStyle,
  pointGlowStyle,
} from '../chart-fx'
import { cssColor } from '../utils/cssColor'
import { themeMode } from '../utils/theme'

export type KcSales = {
  name: string
  amount_disp: string
  wo?: number
}

export type KcTrend = {
  peak_month?: number
  peak_disp?: string
  avg_disp?: string
  complete_month_count?: number
  recent_trend?: string
  recent_disp?: string
  consecutive_silent_complete?: number
  silent_complete_disp?: string
  incomplete_month?: number
  incomplete_hint?: string
}

export type KcItem = {
  name: string
  ytd_disp: string
  sales_disp: string
  sales?: KcSales[]
  silent?: boolean
  mkey?: string
  wo?: number
  tier?: string
  pool?: string
  gap_fen?: number | null
  gap_disp?: string
  near_upgrade?: boolean
  next_tier?: string | null
  status_disp?: string
  trend?: KcTrend
  spark_wo?: number[]
  ytd_fen?: number
  tier_rank?: number
}

export type KcTier = {
  id: string
  label: string
  range_disp: string
  count: number
  amount_disp: string
  pct_count_disp: string
  pct_amount_disp: string
  default_open: boolean
  lazy: boolean
  items: KcItem[]
}

export type KcSeg = {
  id: string
  label: string
  count?: number
  count_disp?: string
  amount_disp?: string
  pct_disp?: string
  wo?: number
}

export type KcPool = {
  id: string
  label: string
  hint?: string
  tiers?: string[]
  count?: number
  count_disp?: string
  amount_disp?: string
}

export type KcActionRow = {
  name?: string
  mkey?: string
  tier?: string
  ytd_disp?: string
  status_disp?: string
  silent?: boolean
  near_upgrade?: boolean
  gap_disp?: string
}

export type KcCard = {
  label?: string
  count?: number
  count_disp?: string
  amount_disp?: string
  value_disp?: string
  pct_disp?: string
  tip?: string
}

export type KcMonthRow = { i?: number; name: string; order_disp: string; wo?: number }

export type KeyCustomersVM = {
  year?: number
  year_label?: string
  panel_title?: string
  caption?: string
  help_lines?: string[]
  sales_col_label?: string
  sales_col_tip?: string
  silent_tip?: string
  near_tip?: string
  metric_label?: string
  default_pool?: string
  compare_max?: number
  guide_text?: string
  pools?: KcPool[]
  summary_cards?: {
    total?: KcCard
    focus_contrib?: KcCard
    silent_focus?: KcCard
    near_upgrade?: KcCard
  }
  structure_bars?: {
    count?: { label?: string; segments?: KcSeg[] }
    amount?: { label?: string; segments?: KcSeg[] }
  }
  action_queues?: { silent?: KcActionRow[]; near?: KcActionRow[] }
  tiers?: KcTier[]
  monthly?: Record<string, KcMonthRow[]>
  empty?: boolean
  totals?: { count?: number; amount_disp?: string }
}

type FilterMode = 'all' | 'silent' | 'near'
type PoolId = 'focus' | 'nurture' | 'longtail'

const store = useCockpitStore()

const kc = computed((): KeyCustomersVM | null => {
  const v = store.vm as { key_customers?: KeyCustomersVM } | null
  return v?.key_customers || null
})

const visible = computed(() => {
  const d = kc.value
  if (!d) return false
  if (d.empty && !(d.tiers && d.tiers.length)) return false
  return !!(d.tiers && d.tiers.length)
})

const itemsCache = reactive<Record<string, KcItem[]>>({})
const loadErr = reactive<Record<string, string>>({})
const loadingTier = reactive<Record<string, boolean>>({})
const monthlyExtra = reactive<Record<string, KcMonthRow[]>>({})
const selectedKey = ref('')
const selectedItem = ref<KcItem | null>(null)
/** 对比集 mkey 列表，最多 compare_max（默认 3） */
const compareKeys = ref<string[]>([])
const compareHint = ref('')
const activePool = ref<PoolId>('focus')
const filterMode = ref<FilterMode>('all')
const searchQ = ref('')
const monthModal = ref(false)
const monthTitle = ref('')
const monthRows = ref<KcMonthRow[]>([])
let seedGen = 0
const inflightTier = new Set<string>()

const COMPARE_MAX = computed(() => {
  const n = Number(kc.value?.compare_max)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 3
})

function clearLocalCaches() {
  for (const k of Object.keys(itemsCache)) delete itemsCache[k]
  for (const k of Object.keys(monthlyExtra)) delete monthlyExtra[k]
  for (const k of Object.keys(loadErr)) delete loadErr[k]
  for (const k of Object.keys(loadingTier)) delete loadingTier[k]
  inflightTier.clear()
  selectedKey.value = ''
  selectedItem.value = null
  compareKeys.value = []
  compareHint.value = ''
  filterMode.value = 'all'
  searchQ.value = ''
  activePool.value = (kc.value?.default_pool as PoolId) || 'focus'
}

function itemKey(it: { mkey?: string; name?: string } | null): string {
  if (!it) return ''
  return it.mkey || `name:${it.name || ''}`
}

function monthRowsFor(it: KcItem | null): KcMonthRow[] {
  if (!it?.mkey) return []
  return monthlyExtra[it.mkey] || kc.value?.monthly?.[it.mkey] || []
}

function selectCustomer(it: KcItem | null) {
  compareHint.value = ''
  if (!it) {
    selectedKey.value = ''
    selectedItem.value = null
    return
  }
  selectedKey.value = itemKey(it)
  selectedItem.value = it
}

function findItemByKey(key: string): KcItem | null {
  if (!key) return null
  for (const tid of Object.keys(itemsCache)) {
    for (const it of itemsCache[tid] || []) {
      if (itemKey(it) === key) return it
    }
  }
  for (const t of kc.value?.tiers || []) {
    for (const it of t.items || []) {
      if (itemKey(it) === key) return it
    }
  }
  return null
}

async function ensureTierForPool(pool: PoolId, gen?: number) {
  const myGen = gen ?? seedGen
  const poolMeta = (kc.value?.pools || []).find((p) => p.id === pool)
  const tids = poolMeta?.tiers || (pool === 'focus' ? ['S', 'A', 'B'] : pool === 'nurture' ? ['C', 'D'] : ['E'])
  const tiers = kc.value?.tiers || []
  for (const tid of tids) {
    const t = tiers.find((x) => x.id === tid)
    if (t) await ensureTier(t, myGen)
  }
}

function seedFromVm(d: KeyCustomersVM | null) {
  const gen = ++seedGen
  clearLocalCaches()
  if (!d?.tiers) return
  activePool.value = (d.default_pool as PoolId) || 'focus'
  for (const t of d.tiers) {
    if (!t.lazy) {
      itemsCache[t.id] = t.items || []
    }
  }
  // 默认重点池：拉齐 S/A/B（非 lazy 已有）；切培育/长尾时再 ensure
  void ensureTierForPool(activePool.value, gen)
}

watch(
  () =>
    [
      store.scope,
      store.buName,
      kc.value?.year ?? 0,
      kc.value?.totals?.count ?? 0,
      kc.value?.totals?.amount_disp ?? '',
      store.vm,
    ] as const,
  () => {
    seedFromVm(kc.value)
  },
  { immediate: true },
)

async function ensureTier(t: KcTier, gen?: number) {
  const myGen = gen ?? seedGen
  if (!t.lazy) {
    if (myGen !== seedGen) return
    itemsCache[t.id] = t.items || []
    return
  }
  if (Object.prototype.hasOwnProperty.call(itemsCache, t.id)) return
  if (inflightTier.has(t.id)) return
  if (store.snapshotMode) {
    if (myGen !== seedGen) return
    itemsCache[t.id] = t.items || []
    if (!itemsCache[t.id].length) {
      loadErr[t.id] = '快照中无该档名单'
    }
    return
  }
  inflightTier.add(t.id)
  loadingTier[t.id] = true
  loadErr[t.id] = ''
  try {
    const buQ =
      store.scope === 'bu' && store.buName
        ? `&bu=${encodeURIComponent(store.buName)}`
        : ''
    const r = await fetch(
      `/api/v1/key-customers/tier?tier=${encodeURIComponent(t.id)}${buQ}`,
      { credentials: 'same-origin' },
    )
    if (myGen !== seedGen) return
    if (!r.ok) {
      loadErr[t.id] =
        r.status === 403
          ? '无权查看该档名单'
          : r.status === 401
            ? '请先登录'
            : '加载该档名单失败'
      return
    }
    const d = (await r.json()) as {
      items?: KcItem[]
      monthly?: Record<string, KcMonthRow[]>
    }
    if (myGen !== seedGen) return
    itemsCache[t.id] = d.items || []
    for (const [k, rows] of Object.entries(d.monthly || {})) {
      monthlyExtra[k] = rows
    }
  } catch {
    if (myGen !== seedGen) return
    loadErr[t.id] = '网络异常，请稍后重试'
  } finally {
    inflightTier.delete(t.id)
    if (myGen === seedGen) {
      loadingTier[t.id] = false
    }
  }
}

async function setPool(pid: PoolId) {
  activePool.value = pid
  filterMode.value = 'all'
  compareHint.value = ''
  await ensureTierForPool(pid)
}

function setFilter(m: FilterMode) {
  filterMode.value = m
}

const poolTiers = computed((): KcTier[] => {
  const poolMeta = (kc.value?.pools || []).find((p) => p.id === activePool.value)
  const tids = new Set(
    poolMeta?.tiers ||
      (activePool.value === 'focus'
        ? ['S', 'A', 'B']
        : activePool.value === 'nurture'
          ? ['C', 'D']
          : ['E']),
  )
  return (kc.value?.tiers || []).filter((t) => tids.has(t.id))
})

const poolLoading = computed(() => poolTiers.value.some((t) => loadingTier[t.id]))
const poolError = computed(() => {
  for (const t of poolTiers.value) {
    if (loadErr[t.id]) return loadErr[t.id]
  }
  return ''
})

const poolItemsRaw = computed((): KcItem[] => {
  const out: KcItem[] = []
  for (const t of poolTiers.value) {
    const items = Object.prototype.hasOwnProperty.call(itemsCache, t.id)
      ? itemsCache[t.id]
      : t.items || []
    for (const it of items) {
      out.push(it.tier ? it : { ...it, tier: t.id })
    }
  }
  return out
})

/** 排序：前端只比较后端给的 tier_rank / ytd_fen / gap_fen，不算业务 */
function sortItems(list: KcItem[], mode: FilterMode): KcItem[] {
  const arr = list.slice()
  if (mode === 'near') {
    arr.sort((a, b) => {
      const ga = a.gap_fen != null ? a.gap_fen : Number.MAX_SAFE_INTEGER
      const gb = b.gap_fen != null ? b.gap_fen : Number.MAX_SAFE_INTEGER
      if (ga !== gb) return ga - gb
      const ya = Number(a.ytd_fen) || 0
      const yb = Number(b.ytd_fen) || 0
      if (yb !== ya) return yb - ya
      return String(a.name || '').localeCompare(String(b.name || ''), 'zh')
    })
    return arr
  }
  // all / silent：等级 S→E，档内金额降序
  arr.sort((a, b) => {
    const ra = a.tier_rank != null ? a.tier_rank : 9
    const rb = b.tier_rank != null ? b.tier_rank : 9
    if (ra !== rb) return ra - rb
    const ya = Number(a.ytd_fen) || 0
    const yb = Number(b.ytd_fen) || 0
    if (yb !== ya) return yb - ya
    return String(a.name || '').localeCompare(String(b.name || ''), 'zh')
  })
  return arr
}

const filteredPoolItems = computed((): KcItem[] => {
  let list = poolItemsRaw.value
  if (filterMode.value === 'silent') {
    list = list.filter((it) => !!it.silent)
  } else if (filterMode.value === 'near') {
    list = list.filter((it) => !!it.near_upgrade)
  }
  const q = searchQ.value.trim().toLowerCase()
  if (q) {
    list = list.filter((it) => String(it.name || '').toLowerCase().includes(q))
  }
  return sortItems(list, filterMode.value)
})

const cards = computed(() => kc.value?.summary_cards || {})
const structureCount = computed(() => kc.value?.structure_bars?.count)
const structureAmount = computed(() => kc.value?.structure_bars?.amount)
const nearTip = computed(
  () =>
    kc.value?.near_tip ||
    '距上一级门槛不超过10%，仅作销售跟进提示，不改变客户等级',
)
const silentTip = computed(
  () =>
    kc.value?.silent_tip ||
    '近 2 个已过去完整自然月下单预估为 0（当前月不计入）；当月有单仍可能静默',
)
const salesColTip = computed(
  () => kc.value?.sales_col_tip || '本年各销售下单预估金额（降序）',
)
const guideText = computed(
  () => kc.value?.guide_text || '从左侧客户池选择客户，或点行动队列开始跟进',
)
const dailyOn = computed(() => !!store.dailyActive)

const actionSilent = computed(() => kc.value?.action_queues?.silent || [])
const actionNear = computed(() => kc.value?.action_queues?.near || [])
const hasAction = computed(
  () => actionSilent.value.length > 0 || actionNear.value.length > 0,
)

function onItemClick(it: KcItem) {
  selectCustomer(it)
}

function onActionClick(row: KcActionRow) {
  const key = itemKey(row)
  const found = findItemByKey(key) || findItemByKey(`name:${row.name || ''}`)
  if (found) {
    selectCustomer(found)
    return
  }
  // 行动队列项可能尚未在当前池缓存：构造最小选中
  selectCustomer({
    name: row.name || '',
    ytd_disp: row.ytd_disp || '',
    sales_disp: '',
    mkey: row.mkey,
    tier: row.tier,
    silent: row.silent,
    near_upgrade: row.near_upgrade,
    status_disp: row.status_disp,
    gap_disp: row.gap_disp,
  })
}

function isSelected(it: KcItem): boolean {
  return selectedKey.value === itemKey(it)
}

function isCompared(it: KcItem): boolean {
  return compareKeys.value.includes(itemKey(it))
}

function toggleCompare(it: KcItem) {
  const key = itemKey(it)
  if (!key) return
  const idx = compareKeys.value.indexOf(key)
  if (idx >= 0) {
    compareKeys.value = compareKeys.value.filter((k) => k !== key)
    compareHint.value = ''
    return
  }
  if (compareKeys.value.length >= COMPARE_MAX.value) {
    compareHint.value = `最多同时比较 ${COMPARE_MAX.value} 个客户，请先移出一位再加入`
    return
  }
  // 主客户优先在对比中
  const next = compareKeys.value.slice()
  if (selectedKey.value && !next.includes(selectedKey.value) && selectedKey.value !== key) {
    // keep as is
  }
  next.push(key)
  compareKeys.value = next
  compareHint.value = ''
  if (!selectedItem.value) selectCustomer(it)
}

function removeCompare(key: string) {
  compareKeys.value = compareKeys.value.filter((k) => k !== key)
  compareHint.value = ''
}

function salesLine(it: KcItem): { text: string; title: string } {
  const sales = it.sales || []
  if (sales.length) {
    const parts = sales.map((s) => `${s.name} ${s.amount_disp}`)
    const full = parts.join(' · ')
    if (parts.length <= 3) return { text: full, title: full }
    const head = parts.slice(0, 3).join(' · ')
    return { text: `${head} · 另有 ${parts.length - 3} 人`, title: full }
  }
  const fallback = it.sales_disp || '—'
  return { text: fallback, title: fallback }
}

function barWidth(wo: number | undefined): string {
  const n = Number(wo) || 0
  const clamped = Math.max(0, Math.min(100, n))
  return `${clamped}%`
}

function openMonthModal() {
  const it = selectedItem.value
  if (!it) return
  const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
  monthTitle.value = `${it.name} · ${y}各月下单`
  monthRows.value = monthRowsFor(it)
  monthModal.value = true
}

/**
 * 高亮月：顶栏 period 能解析出具体月则用该月；
 * 否则用系统当前月。禁止因切月重算等级。
 */
const highlightMonth = computed((): number => {
  const p = String(store.period || '')
  const m = p.match(/年(\d{1,2})月$/)
  if (m) {
    const n = Number(m[1])
    if (n >= 1 && n <= 12) return n
  }
  return new Date().getMonth() + 1
})

const COMPARE_LINE_COLORS = [
  'var(--blue)',
  'var(--purple)',
  'var(--orange)',
]

const trackSeriesItems = computed((): KcItem[] => {
  // 比较集优先；否则单选主客户
  if (compareKeys.value.length) {
    return compareKeys.value
      .map((k) => findItemByKey(k))
      .filter((x): x is KcItem => !!x)
  }
  return selectedItem.value ? [selectedItem.value] : []
})

/** 主区连续月折线：y 用后端 wo；tooltip 用 order_disp；支持最多 3 客 */
const trackOption = computed(() => {
  void themeMode.value
  const seriesItems = trackSeriesItems.value
  const labels = Array.from({ length: 12 }, (_, i) => `${i + 1}月`)
  const ink = chartTextColor()
  const mut = chartMutedColor()
  const hm = highlightMonth.value
  const soft = cssColor('--blue-soft-14')
  const markArea =
    hm >= 1 && hm <= 12 && soft
      ? {
          silent: true,
          itemStyle: { color: soft },
          data: [[{ xAxis: `${hm}月` }, { xAxis: `${hm}月` }]],
        }
      : undefined

  const series = seriesItems.map((it, si) => {
    const rows = monthRowsFor(it)
    const byI = new Map<number, KcMonthRow>()
    for (const r of rows) {
      const m = Number(r.i) || 0
      if (m >= 1 && m <= 12) byI.set(m, r)
    }
    const plot: number[] = []
    const disps: string[] = []
    for (let m = 1; m <= 12; m++) {
      const row = byI.get(m)
      if (row) {
        plot.push(Number(row.wo) || 0)
        disps.push(String(row.order_disp || '—'))
      } else {
        plot.push(0)
        disps.push('—')
      }
    }
    const token = COMPARE_LINE_COLORS[si % COMPARE_LINE_COLORS.length]
    const lineC = cssColor(token.replace('var(', '').replace(')', '')) || cssColor('--blue')
    const area = si === 0 ? areaGradient(lineC) : undefined
    return {
      name: it.name || `客户${si + 1}`,
      type: 'line' as const,
      data: plot,
      disps,
      smooth: 0.2,
      symbol: 'circle',
      symbolSize: (_v: number, params: { dataIndex: number }) =>
        params.dataIndex + 1 === hm ? 11 : 6,
      connectNulls: false,
      itemStyle: pointGlowStyle(lineC),
      lineStyle: {
        ...lineGlowStyle(lineC, si === 0 ? 2.5 : 2),
        type: si === 0 ? 'solid' : si === 1 ? 'dashed' : 'dotted',
      },
      ...(area ? { areaStyle: area } : {}),
      ...(si === 0 && markArea ? { markArea } : {}),
    }
  })

  return {
    ...animBlock(),
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { seriesName: string; dataIndex: number; seriesIndex: number }[]) => {
        if (!params?.length) return ''
        const i = params[0].dataIndex ?? 0
        const tag = i + 1 === hm ? '（当月未完结/高亮）' : ''
        const lines = [`${labels[i] || ''}${tag}`]
        for (const p of params) {
          const s = series[p.seriesIndex]
          const disp = s?.disps?.[i] || '—'
          lines.push(`${p.seriesName}：${disp}`)
        }
        return lines.join('<br/>')
      },
    },
    legend: {
      show: series.length > 1,
      top: 0,
      textStyle: { color: ink, fontSize: 11 },
    },
    grid: {
      left: 36,
      right: 16,
      top: series.length > 1 ? 36 : 28,
      bottom: 28,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: axisLabelStyle({ fontSize: 11, interval: 0, hideOverlap: true }),
      axisLine: { lineStyle: { color: mut } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      show: false,
      splitLine: { show: false },
    },
    series,
  }
})

const trackTitle = computed(() => {
  const items = trackSeriesItems.value
  if (!items.length) return '连续月下单追踪'
  const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
  if (items.length === 1) return `${items[0].name} · ${y}各月下单`
  return `${items.length} 客比较 · ${y}`
})

const panelTitle = computed(() => {
  const base = kc.value?.panel_title || '重点客户下单分析'
  const y = kc.value?.year_label || ''
  return y ? `${base} · ${y}` : base
})

const helpLines = computed(() => {
  const lines = kc.value?.help_lines
  if (lines && lines.length) return lines
  const c = kc.value?.caption
  return c ? [c] : []
})

const selectedSales = computed((): KcSales[] => {
  const it = selectedItem.value
  if (!it?.sales?.length) return []
  return it.sales
})

const selectedTrend = computed((): KcTrend | null => selectedItem.value?.trend || null)

function sparkBars(it: KcItem): number[] {
  const s = it.spark_wo
  if (s && s.length) return s.slice(0, 12)
  return []
}
</script>

<template>
  <div
    v-if="visible"
    id="keyCustomers"
    class="kc-host"
    data-testid="key-customers-panel"
    data-source="key_customers"
  >
    <SciFiPanel panel-class="kc-panel">
      <template #header>
        <span data-testid="kc-panel-title">{{ panelTitle }}</span>
      </template>

      <div class="kc-help" data-testid="kc-help">
        <p
          v-for="(line, hi) in helpLines"
          :key="'hl' + hi"
          class="kc-help__line"
          :data-testid="hi === 0 ? 'kc-caption' : undefined"
        >
          {{ line }}
        </p>
        <p v-if="dailyOn" class="kc-daily-hint" data-testid="kc-daily-hint">
          日查仅作用于上方排名；本块仍按自然年分级，不随日区间重算。
        </p>
      </div>

      <div class="kc-layout" data-testid="kc-layout">
        <!-- 四摘要卡 -->
        <section
          class="kc-summary-cards"
          data-testid="kc-summary-cards"
          aria-label="经营摘要"
        >
          <div class="kc-card" data-testid="kc-card-total">
            <div class="kc-card__label">{{ cards.total?.label || '全部客户 / 年累计' }}</div>
            <div class="kc-card__value">{{ cards.total?.value_disp || '—' }}</div>
          </div>
          <div class="kc-card" data-testid="kc-card-contrib" :title="cards.focus_contrib?.tip">
            <div class="kc-card__label">{{ cards.focus_contrib?.label || '重点客户贡献' }}</div>
            <div class="kc-card__value">{{ cards.focus_contrib?.value_disp || '—' }}</div>
            <div class="kc-card__sub">{{ cards.focus_contrib?.amount_disp }}</div>
          </div>
          <div class="kc-card" data-testid="kc-card-silent" :title="cards.silent_focus?.tip || silentTip">
            <div class="kc-card__label">{{ cards.silent_focus?.label || '需跟进重点客' }}</div>
            <div class="kc-card__value">{{ cards.silent_focus?.value_disp || '—' }}</div>
          </div>
          <div
            class="kc-card"
            data-testid="kc-card-near"
            :title="cards.near_upgrade?.tip || nearTip"
          >
            <div class="kc-card__label">{{ cards.near_upgrade?.label || '临界晋级客户' }}</div>
            <div class="kc-card__value">{{ cards.near_upgrade?.value_disp || '—' }}</div>
          </div>
        </section>

        <!-- 双结构条 -->
        <section
          class="kc-structure-bars"
          data-testid="kc-structure-bars"
          aria-label="六档结构"
        >
          <div class="kc-bar-row">
            <div class="kc-bar-row__label">{{ structureCount?.label || '客户数结构' }}</div>
            <div class="kc-bar-track" role="list">
              <div
                v-for="(seg, i) in structureCount?.segments || []"
                :key="'sc' + seg.id"
                class="kc-bar-seg"
                role="listitem"
                :data-tier="seg.id"
                :data-i="i"
                :style="{ width: barWidth(seg.wo) }"
                :title="`${seg.label} · ${seg.count_disp || ''} · ${seg.pct_disp || ''}`"
                tabindex="0"
              />
            </div>
          </div>
          <div class="kc-bar-row">
            <div class="kc-bar-row__label">{{ structureAmount?.label || '金额结构' }}</div>
            <div class="kc-bar-track" role="list">
              <div
                v-for="(seg, i) in structureAmount?.segments || []"
                :key="'sa' + seg.id"
                class="kc-bar-seg"
                role="listitem"
                :data-tier="seg.id"
                :data-i="i"
                :style="{ width: barWidth(seg.wo) }"
                :title="`${seg.label} · ${seg.amount_disp || ''} · ${seg.pct_disp || ''}`"
                tabindex="0"
              />
            </div>
          </div>
          <ul class="kc-bar-legend" aria-label="档位图例">
            <li
              v-for="(seg, i) in structureCount?.segments || []"
              :key="'lg' + seg.id"
            >
              <span class="kc-pie-dot" :data-i="i" :data-tier="seg.id" />
              <span>{{ seg.label }}</span>
            </li>
          </ul>
        </section>

        <!-- 主工作区：左池右洞察 · 固定同高 -->
        <div class="kc-workbench" data-testid="kc-workbench">
          <section class="kc-pool" data-testid="kc-pool" aria-label="客户池">
            <div class="kc-pool__tabs" role="tablist">
              <button
                v-for="p in kc?.pools || []"
                :key="p.id"
                type="button"
                class="kc-chip"
                role="tab"
                :class="{ 'is-active': activePool === p.id }"
                :data-testid="'kc-pool-tab-' + p.id"
                :aria-selected="activePool === p.id ? 'true' : 'false'"
                @click="setPool(p.id as PoolId)"
              >
                {{ p.label }}
                <span class="kc-chip__hint">{{ p.hint }}</span>
                <span class="kc-chip__meta">{{ p.count_disp }}</span>
              </button>
            </div>
            <div class="kc-pool__filters">
              <button
                type="button"
                class="kc-chip kc-chip--sm"
                :class="{ 'is-active': filterMode === 'all' }"
                data-testid="kc-filter-all"
                @click="setFilter('all')"
              >
                全部
              </button>
              <button
                type="button"
                class="kc-chip kc-chip--sm"
                :class="{ 'is-active': filterMode === 'silent' }"
                data-testid="kc-filter-silent"
                @click="setFilter('silent')"
              >
                需跟进
              </button>
              <button
                type="button"
                class="kc-chip kc-chip--sm"
                :class="{ 'is-active': filterMode === 'near' }"
                data-testid="kc-filter-near"
                :title="nearTip"
                @click="setFilter('near')"
              >
                临界晋级
              </button>
              <input
                v-model="searchQ"
                type="search"
                class="kc-search"
                data-testid="kc-search"
                placeholder="搜索客户名"
                aria-label="搜索客户名"
              />
            </div>
            <div class="kc-pool__list" data-testid="kc-pool-list">
              <div v-if="poolLoading" class="kc-tier__loading">加载中…</div>
              <div v-else-if="poolError" class="kc-tier__err">{{ poolError }}</div>
              <div v-else-if="!filteredPoolItems.length" class="kc-tier__empty">
                {{ poolItemsRaw.length ? '无匹配客户' : '该池暂无客户' }}
              </div>
              <template v-else>
                <div
                  v-for="(it, idx) in filteredPoolItems"
                  :key="'row' + idx + itemKey(it)"
                  class="kc-row"
                  :class="{
                    'is-selected': isSelected(it),
                    'is-compare': isCompared(it),
                  }"
                  data-testid="kc-customer-row"
                >
                  <button
                    type="button"
                    class="kc-row__main"
                    :aria-pressed="isSelected(it) ? 'true' : 'false'"
                    @click="onItemClick(it)"
                  >
                    <span class="kc-row__name" :title="it.name">
                      <span class="kc-row__tier" :data-tier="it.tier">{{ it.tier }}</span>
                      {{ it.name }}
                      <span
                        v-if="it.status_disp"
                        class="kc-row__status"
                        :class="{
                          'is-silent': it.silent,
                          'is-near': it.near_upgrade && !it.silent,
                        }"
                        :title="it.silent ? silentTip : nearTip"
                      >{{ it.status_disp }}</span>
                    </span>
                    <span
                      class="kc-row__sales"
                      :title="salesLine(it).title || salesColTip"
                    >{{ salesLine(it).text }}</span>
                    <span class="kc-row__ytd">{{ it.ytd_disp }}</span>
                    <span
                      v-if="sparkBars(it).length"
                      class="kc-spark"
                      aria-hidden="true"
                    >
                      <i
                        v-for="(w, si) in sparkBars(it)"
                        :key="'sp' + si"
                        class="kc-spark__bar"
                        :style="{
                          height: `${Math.max(0, Math.min(100, Number(w) || 0))}%`,
                        }"
                      />
                    </span>
                  </button>
                  <button
                    type="button"
                    class="kc-row__cmp"
                    data-testid="kc-compare-toggle"
                    :aria-pressed="isCompared(it) ? 'true' : 'false'"
                    :title="isCompared(it) ? '移出对比' : '加入对比'"
                    @click.stop="toggleCompare(it)"
                  >
                    {{ isCompared(it) ? '移出' : '对比' }}
                  </button>
                </div>
              </template>
            </div>
            <p v-if="compareHint" class="kc-compare-hint" data-testid="kc-compare-hint">
              {{ compareHint }}
            </p>
          </section>

          <section class="kc-insight" data-testid="kc-insight" aria-label="客户洞察">
            <!-- 未选：行动队列 -->
            <div v-if="!selectedItem" class="kc-insight__empty" data-testid="kc-insight-empty">
              <p class="kc-guide" data-testid="kc-guide">{{ guideText }}</p>
              <div v-if="hasAction" class="kc-action-queue" data-testid="kc-action-queue">
                <div v-if="actionSilent.length" class="kc-action-block">
                  <div class="kc-section-label">需跟进（静默重点）</div>
                  <button
                    v-for="(row, ri) in actionSilent"
                    :key="'as' + ri + row.mkey"
                    type="button"
                    class="kc-action-row"
                    data-testid="kc-action-row"
                    @click="onActionClick(row)"
                  >
                    <span class="kc-row__tier" :data-tier="row.tier">{{ row.tier }}</span>
                    <span class="kc-action-row__name" :title="row.name">{{ row.name }}</span>
                    <span class="kc-action-row__meta">{{ row.ytd_disp }}</span>
                    <span class="kc-row__status is-silent">{{ row.status_disp || '静默' }}</span>
                  </button>
                </div>
                <div v-if="actionNear.length" class="kc-action-block">
                  <div class="kc-section-label" :title="nearTip">临界晋级</div>
                  <button
                    v-for="(row, ri) in actionNear"
                    :key="'an' + ri + row.mkey"
                    type="button"
                    class="kc-action-row"
                    data-testid="kc-action-row"
                    @click="onActionClick(row)"
                  >
                    <span class="kc-row__tier" :data-tier="row.tier">{{ row.tier }}</span>
                    <span class="kc-action-row__name" :title="row.name">{{ row.name }}</span>
                    <span class="kc-action-row__meta">{{ row.ytd_disp }}</span>
                    <span class="kc-row__status is-near">{{ row.status_disp || '临界' }}</span>
                  </button>
                </div>
              </div>
              <div v-else class="kc-tier__empty" data-testid="kc-action-empty">
                当前无需跟进或临界晋级提醒
              </div>
            </div>

            <!-- 已选：摘要 + 销售 + 趋势 -->
            <template v-else>
              <div class="kc-insight__head" data-testid="kc-insight-head">
                <div class="kc-insight__title">
                  <span class="kc-row__tier" :data-tier="selectedItem.tier">{{
                    selectedItem.tier
                  }}</span>
                  <span class="kc-insight__name" :title="selectedItem.name">{{
                    selectedItem.name
                  }}</span>
                  <span class="kc-insight__ytd">{{ selectedItem.ytd_disp }}</span>
                </div>
                <div class="kc-insight__status">
                  <span
                    v-if="selectedItem.status_disp"
                    class="kc-row__status"
                    :class="{
                      'is-silent': selectedItem.silent,
                      'is-near': selectedItem.near_upgrade && !selectedItem.silent,
                    }"
                    :title="selectedItem.silent ? silentTip : nearTip"
                  >{{ selectedItem.status_disp }}</span>
                  <span
                    v-if="selectedItem.gap_disp && selectedItem.next_tier"
                    class="kc-insight__gap"
                    :title="nearTip"
                  >距{{ selectedItem.next_tier }} {{ selectedItem.gap_disp }}</span>
                </div>
                <div class="kc-insight__actions">
                  <button
                    type="button"
                    class="kc-track__zoom"
                    data-testid="kc-compare-toggle-main"
                    @click="toggleCompare(selectedItem)"
                  >
                    {{ isCompared(selectedItem) ? '移出对比' : '加入对比' }}
                  </button>
                  <button
                    type="button"
                    class="kc-track__zoom"
                    data-testid="kc-track-zoom"
                    title="放大查看"
                    @click="openMonthModal"
                  >
                    放大
                  </button>
                </div>
              </div>

              <div
                v-if="compareKeys.length"
                class="kc-compare-tags"
                data-testid="kc-compare-tags"
              >
                <span
                  v-for="ck in compareKeys"
                  :key="'ct' + ck"
                  class="kc-compare-tag"
                >
                  {{ findItemByKey(ck)?.name || ck }}
                  <button type="button" class="kc-compare-tag__x" @click="removeCompare(ck)">
                    ×
                  </button>
                </span>
              </div>
              <p v-if="compareHint" class="kc-compare-hint">{{ compareHint }}</p>

              <div
                v-if="selectedTrend"
                class="kc-trend-summary"
                data-testid="kc-trend-summary"
              >
                <span>峰值 {{ selectedTrend.peak_disp || '—' }}</span>
                <span>月均 {{ selectedTrend.avg_disp || '—' }}</span>
                <span>{{ selectedTrend.recent_disp || '—' }}</span>
                <span>{{ selectedTrend.silent_complete_disp || '—' }}</span>
                <span v-if="selectedTrend.incomplete_hint" class="kc-trend-summary__hint">{{
                  selectedTrend.incomplete_hint
                }}</span>
              </div>

              <div
                v-if="selectedSales.length && trackSeriesItems.length <= 1"
                class="kc-sales-bars"
                data-testid="kc-sales-bars"
                aria-label="各销售下单构成"
              >
                <div
                  v-for="(s, si) in selectedSales"
                  :key="'sb' + si + s.name"
                  class="kc-sales-bars__row"
                >
                  <span class="kc-sales-bars__name" :title="s.name">{{ s.name }}</span>
                  <div class="kc-sales-bars__track">
                    <div class="kc-sales-bars__fill" :style="{ width: barWidth(s.wo) }" />
                  </div>
                  <span class="kc-sales-bars__amt">{{ s.amount_disp }}</span>
                </div>
              </div>

              <div class="kc-track" data-testid="kc-track">
                <div class="kc-track__head">
                  <div
                    class="kc-section-label kc-track__title"
                    data-testid="kc-track-title"
                  >
                    {{ trackTitle }}
                  </div>
                </div>
                <div class="kc-track-chart" data-testid="kc-track-chart">
                  <EchartsHost :option="trackOption" />
                </div>
              </div>
            </template>
          </section>
        </div>
      </div>
    </SciFiPanel>

    <DataModal :open="monthModal" :title="monthTitle" @close="monthModal = false">
      <div v-if="!monthRows.length" class="rank-list__empty">暂无月度下单数据</div>
      <div v-else class="kc-month-list" data-testid="kc-month-modal">
        <RankBar
          v-for="(it, idx) in monthRows"
          :key="'kcm' + idx + it.name"
          :rank="it.i ?? idx + 1"
          :name="String(it.name || '')"
          :primary-width="Number(it.wo) || 0"
          :primary-value="it.order_disp"
        />
      </div>
    </DataModal>
  </div>
</template>
