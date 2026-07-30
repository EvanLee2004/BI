<script setup lang="ts">
/**
 * 3.4.1 重点客户分析 · Layer3
 * 上：级分布双饼 · 下：客户名单 + 连续月追踪折线
 * 前端零金额/分级运算；日查不换本块；切月不重算等级。
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

export type KcItem = {
  name: string
  ytd_disp: string
  sales_disp: string
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

/** BU/整体 VM 切换时必须清空本地缓存，否则会泄漏上一 scope 客户名 */
function clearLocalCaches() {
  for (const k of Object.keys(itemsCache)) delete itemsCache[k]
  for (const k of Object.keys(monthlyExtra)) delete monthlyExtra[k]
  for (const k of Object.keys(loadErr)) delete loadErr[k]
  for (const k of Object.keys(loadingTier)) delete loadingTier[k]
  for (const k of Object.keys(openMap)) delete openMap[k]
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

/** 最高非空档（S→E）第一客户；无可用 items 则空 */
function selectDefaultCustomer(d: KeyCustomersVM | null) {
  if (!d?.tiers?.length) {
    selectCustomer(null)
    return
  }
  for (const t of d.tiers) {
    const items = tierItems(t)
    if (items.length) {
      selectCustomer(items[0])
      return
    }
  }
  selectCustomer(null)
}

function seedFromVm(d: KeyCustomersVM | null) {
  clearLocalCaches()
  if (!d?.tiers) return
  for (const t of d.tiers) {
    // 3.4.1 策略 A：default_open 全 false；仍尊重后端字段（若未来策略 B）
    openMap[t.id] = !!t.default_open
    if (!t.lazy) {
      itemsCache[t.id] = t.items || []
    }
  }
  selectDefaultCustomer(d)
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

async function ensureTier(t: KcTier) {
  if (!t.lazy) {
    itemsCache[t.id] = t.items || []
    return
  }
  if (Object.prototype.hasOwnProperty.call(itemsCache, t.id)) return
  if (store.snapshotMode) {
    itemsCache[t.id] = t.items || []
    if (!itemsCache[t.id].length) {
      loadErr[t.id] = '快照中无该档名单'
    }
    return
  }
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
    itemsCache[t.id] = d.items || []
    for (const [k, rows] of Object.entries(d.monthly || {})) {
      monthlyExtra[k] = rows
    }
  } catch {
    loadErr[t.id] = '网络异常，请稍后重试'
  } finally {
    loadingTier[t.id] = false
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

/** 主区连续月折线：y 用后端 wo（相对强度），tooltip 用 order_disp；禁止前端算金额 */
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
  const plot: (number | null)[] = []
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
  return {
    ...animBlock(),
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>下单预估 ${disps[i] || '—'}`
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
        symbolSize: 7,
        connectNulls: false,
        itemStyle: pointGlowStyle(lineC),
        lineStyle: lineGlowStyle(lineC, 2.5),
        ...(area ? { areaStyle: area } : {}),
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

const helpLines = computed(() => {
  const lines = kc.value?.help_lines
  if (lines && lines.length) return lines
  // 兜底：旧 VM 无 help_lines 时仍展示口径 caption
  const c = kc.value?.caption
  return c ? [c] : []
})

const salesColLabel = computed(() => kc.value?.sales_col_label || '主销售')
const salesColTip = computed(
  () => kc.value?.sales_col_tip || '本年下单预估最多的销售，非唯一绑定',
)
const silentTip = computed(
  () => kc.value?.silent_tip || '近 2 个已过去完整自然月下单预估为 0（当前月不计入）',
)

const dailyOn = computed(() => !!store.dailyActive)

function isSelected(it: KcItem): boolean {
  return selectedKey.value === itemKey(it)
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
        <span>重点客户分析 · {{ kc?.year_label || '' }}</span>
      </template>

      <!-- 顶区 help_lines：口径 · 静默 · 主销售（后端下发） -->
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

        <!-- 【下】客户名单 + 连续月追踪 -->
        <section class="kc-bottom" data-testid="kc-bottom" aria-label="客户与连续月追踪">
          <div class="kc-list" data-testid="kc-list">
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
                      :title="salesColTip"
                    >
                      <span class="kc-row__sales-label">{{ salesColLabel }}</span>
                      {{ it.sales_disp }}
                    </span>
                    <span class="kc-row__ytd">{{ it.ytd_disp }}</span>
                  </button>
                </template>
              </div>
            </div>
          </div>

          <div class="kc-track" data-testid="kc-track">
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
              点击左侧客户查看 1～12 月下单
            </div>
            <div v-else class="kc-track-chart" data-testid="kc-track-chart">
              <EchartsHost :option="trackOption" />
            </div>
          </div>
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
