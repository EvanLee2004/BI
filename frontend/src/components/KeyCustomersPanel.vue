<script setup lang="ts">
/**
 * 3.4.2 重点客户下单分析 · Layer3
 * L-A：上双饼 · 中名单满宽（默认全开限高）· 下连续月折线满宽
 * 默认不选中；多销售金额降序；去主销售；前端零金额/分级运算。
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
  pieEmphasis,
  pieGlowItemStyle,
  pointGlowStyle,
  SERIES_PALETTE,
} from '../chart-fx'
import { cssColor } from '../utils/cssColor'
import { themeMode } from '../utils/theme'

export type KcSales = {
  name: string
  amount_disp: string
  wo?: number
}

export type KcItem = {
  name: string
  ytd_disp: string
  sales_disp: string
  sales?: KcSales[]
  silent?: boolean
  mkey?: string
  wo?: number
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

export type KcPie = {
  labels: string[]
  values: number[]
  values_disp: string[]
  pct_disp: string[]
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
  metric_label?: string
  tiers?: KcTier[]
  pie_count?: KcPie
  pie_amount?: KcPie
  monthly?: Record<string, KcMonthRow[]>
  empty?: boolean
  totals?: { count?: number; amount_disp?: string }
}

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

const openMap = reactive<Record<string, boolean>>({})
const itemsCache = reactive<Record<string, KcItem[]>>({})
const loadErr = reactive<Record<string, string>>({})
const loadingTier = reactive<Record<string, boolean>>({})
const monthlyExtra = reactive<Record<string, KcMonthRow[]>>({})
const selectedKey = ref('')
const selectedItem = ref<KcItem | null>(null)
const monthModal = ref(false)
const monthTitle = ref('')
const monthRows = ref<KcMonthRow[]>([])
/** 防 BU/VM 切换中途串名单：ensure 写缓存前校验代数 */
let seedGen = 0
const inflightTier = new Set<string>()

/** BU/整体 VM 切换时必须清空本地缓存，否则会泄漏上一 scope 客户名 */
function clearLocalCaches() {
  for (const k of Object.keys(itemsCache)) delete itemsCache[k]
  for (const k of Object.keys(monthlyExtra)) delete monthlyExtra[k]
  for (const k of Object.keys(loadErr)) delete loadErr[k]
  for (const k of Object.keys(loadingTier)) delete loadingTier[k]
  for (const k of Object.keys(openMap)) delete openMap[k]
  inflightTier.clear()
  selectedKey.value = ''
  selectedItem.value = null
}

function itemKey(it: KcItem): string {
  return it.mkey || `name:${it.name || ''}`
}

function monthRowsFor(it: KcItem | null): KcMonthRow[] {
  if (!it?.mkey) return []
  return monthlyExtra[it.mkey] || kc.value?.monthly?.[it.mkey] || []
}

function selectCustomer(it: KcItem | null) {
  if (!it) {
    selectedKey.value = ''
    selectedItem.value = null
    return
  }
  selectedKey.value = itemKey(it)
  selectedItem.value = it
}

function seedFromVm(d: KeyCustomersVM | null) {
  const gen = ++seedGen
  clearLocalCaches()
  if (!d?.tiers) return
  for (const t of d.tiers) {
    // 3.4.2：default_open 全 true；仍尊重后端字段
    openMap[t.id] = t.default_open !== false && !!t.default_open
    // 若后端未下发 default_open（旧包），也默认开
    if (t.default_open == null) openMap[t.id] = true
    if (!t.lazy) {
      itemsCache[t.id] = t.items || []
    }
  }
  // 3.4.2：默认不选中任何客户；折线空态
  // 默认全开时自动 ensureTier 拉 lazy 档（C/D/E），禁止假空
  for (const t of d.tiers) {
    if (openMap[t.id]) {
      void ensureTier(t, gen)
    }
  }
}

// scope + buName + year + VM 引用任一变 → 重置（防 BU→BU 脏缓存）
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

function tierItems(t: KcTier): KcItem[] {
  if (Object.prototype.hasOwnProperty.call(itemsCache, t.id)) return itemsCache[t.id]
  return t.items || []
}

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

async function toggleTier(t: KcTier) {
  const next = !openMap[t.id]
  openMap[t.id] = next
  if (next) await ensureTier(t)
}

function onItemClick(it: KcItem) {
  selectCustomer(it)
}

function openMonthModal() {
  const it = selectedItem.value
  if (!it) return
  const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
  monthTitle.value = `${it.name} · ${y}各月下单`
  monthRows.value = monthRowsFor(it)
  monthModal.value = true
}

/** 行内销售文案：≤3 全写；>3 前三 + 另有 N 人；title 看全列表 */
function salesLine(it: KcItem): { text: string; title: string } {
  const sales = it.sales || []
  if (sales.length) {
    const parts = sales.map((s) => `${s.name} ${s.amount_disp}`)
    const full = parts.join(' · ')
    if (parts.length <= 3) return { text: full, title: full }
    const head = parts.slice(0, 3).join(' · ')
    return { text: `${head} · 另有 ${parts.length - 3} 人`, title: full }
  }
  // 旧 VM 兜底
  const fallback = it.sales_disp || '—'
  return { text: fallback, title: fallback }
}

function pieOption(pie: KcPie | undefined, centerTitle: string) {
  void themeMode.value
  const labels = pie?.labels || []
  const values = pie?.values || []
  const valuesDisp = pie?.values_disp || []
  const pctDisp = pie?.pct_disp || []
  const data = labels.map((name, i) => ({
    name,
    value: Number(values[i] || 0),
    itemStyle: { color: SERIES_PALETTE[i % SERIES_PALETTE.length] },
  }))
  const ink = chartTextColor()
  const mut = chartMutedColor()
  return {
    ...animBlock(),
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p: { dataIndex: number; name: string }) => {
        const i = p.dataIndex
        return `${p.name}<br/>${valuesDisp[i] || '—'}（${pctDisp[i] || '—'}）`
      },
    },
    color: SERIES_PALETTE,
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        data,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderColor: cssColor('--chart-label-stroke-dark') || cssColor('--panel-bg'),
          borderWidth: 2,
          ...pieGlowItemStyle(cssColor('--blue')),
        },
        emphasis: pieEmphasis(),
      },
    ],
    graphic: [
      {
        type: 'group',
        left: 'center',
        top: 'middle',
        children: [
          {
            type: 'text',
            style: {
              text: centerTitle,
              fill: mut,
              fontSize: 11,
              textAlign: 'center',
            },
            top: -8,
          },
          {
            type: 'text',
            style: {
              text: '',
              fill: ink,
              fontSize: 0,
              textAlign: 'center',
            },
          },
        ],
      },
    ],
  }
}

const pieCountOption = computed(() => {
  const t = kc.value?.totals?.count
  return pieOption(kc.value?.pie_count, t != null ? `共${t}户` : '数量')
})
const pieAmountOption = computed(() => {
  const a = kc.value?.totals?.amount_disp || ''
  return pieOption(kc.value?.pie_amount, a ? a : '金额')
})

/**
 * 高亮月：顶栏 period 能解析出具体月则用该月；
 * 否则用系统当前月。禁止因切月重算等级。
 */
const highlightMonth = computed((): number => {
  const p = String(store.period || '')
  // 精确月：2026年6月（排除 1-3 月区间）
  const m = p.match(/年(\d{1,2})月$/)
  if (m) {
    const n = Number(m[1])
    if (n >= 1 && n <= 12) return n
  }
  return new Date().getMonth() + 1
})

/** 主区连续月折线：y 用后端 wo；tooltip 用 order_disp；月高亮 */
const trackOption = computed(() => {
  void themeMode.value
  const it = selectedItem.value
  const rows = monthRowsFor(it)
  const byI = new Map<number, KcMonthRow>()
  for (const r of rows) {
    const m = Number(r.i) || 0
    if (m >= 1 && m <= 12) byI.set(m, r)
  }
  const labels: string[] = []
  const plot: number[] = []
  const disps: string[] = []
  for (let m = 1; m <= 12; m++) {
    labels.push(`${m}月`)
    const row = byI.get(m)
    if (row) {
      plot.push(Number(row.wo) || 0)
      disps.push(String(row.order_disp || '—'))
    } else {
      plot.push(0)
      disps.push('—')
    }
  }
  const ink = chartTextColor()
  const mut = chartMutedColor()
  const lineC = cssColor('--blue')
  const area = areaGradient(lineC)
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
  const symbolSizes = labels.map((_, i) => (i + 1 === hm ? 12 : 7))
  return {
    ...animBlock(),
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const tag = i + 1 === hm ? '（当前高亮月）' : ''
        return `${labels[i] || ''}${tag}<br/>下单预估 ${disps[i] || '—'}`
      },
    },
    grid: { left: 36, right: 16, top: 28, bottom: 28, containLabel: true },
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
    series: [
      {
        name: '各月下单',
        type: 'line',
        data: plot,
        smooth: 0.2,
        symbol: 'circle',
        symbolSize: (_v: number, params: { dataIndex: number }) =>
          symbolSizes[params.dataIndex] ?? 7,
        connectNulls: false,
        itemStyle: pointGlowStyle(lineC),
        lineStyle: lineGlowStyle(lineC, 2.5),
        ...(area ? { areaStyle: area } : {}),
        ...(markArea ? { markArea } : {}),
        label: {
          show: false,
          color: ink,
        },
      },
    ],
  }
})

const trackTitle = computed(() => {
  const it = selectedItem.value
  if (!it) return '连续月下单追踪'
  const y = kc.value?.year_label || (kc.value?.year ? `${kc.value.year}年` : '')
  return `${it.name} · ${y}各月下单`
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

const salesColTip = computed(
  () => kc.value?.sales_col_tip || '本年各销售下单预估金额（降序）',
)
const silentTip = computed(
  () =>
    kc.value?.silent_tip ||
    '近 2 个已过去完整自然月下单预估为 0（当前月不计入）；当月有单仍可能静默',
)

const dailyOn = computed(() => !!store.dailyActive)

const selectedSales = computed((): KcSales[] => {
  const it = selectedItem.value
  if (!it?.sales?.length) return []
  return it.sales
})

function isSelected(it: KcItem): boolean {
  return selectedKey.value === itemKey(it)
}

function barWidth(wo: number | undefined): string {
  const n = Number(wo) || 0
  const clamped = Math.max(0, Math.min(100, n))
  return `${clamped}%`
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

      <!-- 顶区 help_lines：口径 · 静默（当前月不计入）· 点击提示 -->
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

      <!-- L-A：饼 → 名单 → 折线（纵向，禁止左名单|右折线主结构） -->
      <div class="kc-layout" data-testid="kc-layout">
        <!-- 【上】级分布双饼 -->
        <section class="kc-pies" data-testid="kc-pies" aria-label="级分布结构总览">
          <div class="kc-section-label">级分布 · 结构总览</div>
          <div class="kc-pies__row">
            <div class="kc-pie-block">
              <div class="kc-pie-title">数量环 · 共{{ kc?.totals?.count ?? '—' }}户</div>
              <div class="kc-pie-chart">
                <EchartsHost :option="pieCountOption" />
              </div>
              <ul class="kc-pie-legend">
                <li v-for="(lab, i) in kc?.pie_count?.labels || []" :key="'pc' + lab">
                  <span class="kc-pie-dot" :data-i="i" />
                  <span>{{ lab }}</span>
                  <span>{{ kc?.pie_count?.values_disp?.[i] }}户</span>
                  <span>{{ kc?.pie_count?.pct_disp?.[i] }}</span>
                </li>
              </ul>
            </div>
            <div class="kc-pie-block">
              <div class="kc-pie-title">金额环 · {{ kc?.totals?.amount_disp || '—' }}</div>
              <div class="kc-pie-chart">
                <EchartsHost :option="pieAmountOption" />
              </div>
              <ul class="kc-pie-legend">
                <li v-for="(lab, i) in kc?.pie_amount?.labels || []" :key="'pa' + lab">
                  <span class="kc-pie-dot" :data-i="i" />
                  <span>{{ lab }}</span>
                  <span>{{ kc?.pie_amount?.values_disp?.[i] }}</span>
                  <span>{{ kc?.pie_amount?.pct_disp?.[i] }}</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <!-- 【中】六档名单满宽 -->
        <section class="kc-list" data-testid="kc-list" aria-label="客户名单六档">
          <div class="kc-section-label">客户名单 · 六档</div>
          <div
            v-for="t in kc?.tiers || []"
            :key="t.id"
            class="kc-tier"
            :data-tier="t.id"
            :data-open="openMap[t.id] ? '1' : '0'"
          >
            <button
              type="button"
              class="kc-tier__head"
              :data-testid="'kc-tier-head-' + t.id"
              :aria-expanded="openMap[t.id] ? 'true' : 'false'"
              @click="toggleTier(t)"
            >
              <span class="kc-tier__id">{{ t.label }}</span>
              <span class="kc-tier__range">{{ t.range_disp }}</span>
              <span class="kc-tier__meta">
                <span>{{ t.count }}户</span>
                <span>{{ t.amount_disp }}</span>
                <span>{{ t.pct_amount_disp }}</span>
              </span>
              <span class="kc-tier__chev">{{ openMap[t.id] ? '▾' : '▸' }}</span>
            </button>
            <div
              v-if="openMap[t.id]"
              class="kc-tier__body"
              :data-testid="'kc-tier-body-' + t.id"
            >
              <div v-if="loadingTier[t.id]" class="kc-tier__loading">加载中…</div>
              <div v-else-if="loadErr[t.id]" class="kc-tier__err">{{ loadErr[t.id] }}</div>
              <div v-else-if="!tierItems(t).length" class="kc-tier__empty">
                {{ t.count ? '暂无名单' : '该档暂无客户' }}
              </div>
              <template v-else>
                <button
                  v-for="(it, idx) in tierItems(t)"
                  :key="t.id + '-' + idx + '-' + it.name"
                  type="button"
                  class="kc-row"
                  :class="{ 'is-selected': isSelected(it) }"
                  data-testid="kc-customer-row"
                  :aria-pressed="isSelected(it) ? 'true' : 'false'"
                  @click="onItemClick(it)"
                >
                  <span class="kc-row__name">
                    {{ it.name }}
                    <span
                      v-if="it.silent"
                      class="kc-row__silent"
                      :title="silentTip"
                    >静默</span>
                  </span>
                  <span
                    class="kc-row__sales"
                    :title="salesLine(it).title || salesColTip"
                  >
                    {{ salesLine(it).text }}
                  </span>
                  <span class="kc-row__ytd">{{ it.ytd_disp }}</span>
                </button>
              </template>
            </div>
          </div>
        </section>

        <!-- 【下】连续月折线满宽 -->
        <section class="kc-track" data-testid="kc-track" aria-label="连续月下单追踪">
          <div class="kc-track__head">
            <div class="kc-section-label kc-track__title" data-testid="kc-track-title">
              {{ trackTitle }}
            </div>
            <button
              v-if="selectedItem"
              type="button"
              class="kc-track__zoom"
              data-testid="kc-track-zoom"
              title="放大查看"
              @click="openMonthModal"
            >
              放大
            </button>
          </div>
          <div v-if="!selectedItem" class="kc-track__empty" data-testid="kc-track-empty">
            点击上方客户查看 1～12 月下单
          </div>
          <template v-else>
            <div
              v-if="selectedSales.length"
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
                  <div
                    class="kc-sales-bars__fill"
                    :style="{ width: barWidth(s.wo) }"
                  />
                </div>
                <span class="kc-sales-bars__amt">{{ s.amount_disp }}</span>
              </div>
            </div>
            <div class="kc-track-chart" data-testid="kc-track-chart">
              <EchartsHost :option="trackOption" />
            </div>
          </template>
        </section>
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
