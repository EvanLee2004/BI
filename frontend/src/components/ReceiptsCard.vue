<script setup lang="ts">
import '../styles/components/ReceiptsCard.css'
/**
 * 下单/回款情况：紫柱下单 + 青柱回款 + 月均预算虚线 + 右侧摘要（本年下单/回款 + 年目标进度条）。
 * 任务书61·A：删尚待回款/年标签/回款占下单/黄回款率线；目标进度条有则显。
 * 任务书61·C-2：x 轴裁到当前系统月。显示串全 VM；前端零金额运算（铁律2）。
 * 2.2.4·C：y 轴 max 覆盖 budget_month，月均预算虚线不再被裁。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  axisLabelStyle,
  barGlowStyle,
  dataLabelStyle,
  legendTextStyle,
} from '../chart-fx'
import { axisMaxCover, clipToCurrentMonth, padYearMonths, resolveMonthCap } from '../chart-months'
import { cssColor } from '../utils/cssColor'
import { withWanUnit } from '../utils/disp'
import { themeMode } from '../utils/theme'
import type { AxisTick, ReceiptsVM } from '../types/vm'

const store = useCockpitStore()
const r = computed((): Partial<ReceiptsVM> => store.vm?.receipts || {})

function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

/** 3.6.1：系列峰值下标（null/NaN 忽略）；并列取最后一个 */
function peakIndex(vals: (number | null)[]): number {
  let best = -1
  let bestV = -Infinity
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i]
    if (v == null || Number.isNaN(Number(v))) continue
    const n = Number(v)
    if (n >= bestV) {
      bestV = n
      best = i
    }
  }
  return best
}

const side = computed(() => {
  const map = r.value.summary_by_period || {}
  const pk = store.period || ''
  return map[pk] || map[store.vm?.year_key || ''] || null
})

/** 右侧摘要：有本年下单/回款 或 任一年目标条才显示 */
const sideVisible = computed(() => {
  const s = side.value
  if (!s) return false
  if (s.orders_disp || s.receipts_disp) return true
  if (s.receipt_target_disp || s.order_target_disp) return true
  return false
})

const option = computed(() => {
  void themeMode.value
  const rawLabels = (r.value.labels || []).map((x) => String(x))
  const rawRecs = (r.value.receipts || []).map((x) => Number(x) || 0)
  const rawOrds = (r.value.orders || []).map((x) => Number(x) || 0)
  const rawRd = (r.value.receipts_disp || []).map((x) => String(x ?? ''))
  const rawOd = (r.value.orders_disp || []).map((x) => String(x ?? ''))
  const padded = padYearMonths(rawLabels, [rawRecs, rawOrds], [rawRd, rawOd])
  const monthCap = resolveMonthCap({
    chartMonthMax: (r.value as { chart_month_max?: number }).chart_month_max
      ?? (store.vm as { chart_month_max?: number } | null)?.chart_month_max,
    defaultEnd: store.vm?.daily?.default_end,
  })
  const clipped = clipToCurrentMonth(padded.labels, padded.series, padded.disps, monthCap)
  const labels = clipped.labels
  const recs = clipped.series[0]
  const ords = clipped.series[1]
  const rd = clipped.disps[0]
  const od = clipped.disps[1]
  const empty = (i: number) => !rd[i] && !od[i]
  const recPlot = recs.map((v, i) => (empty(i) ? null : v))
  const ordPlot = ords.map((v, i) => (empty(i) ? null : v))
  const ticks = r.value.y_axis_ticks || []
  const maxV0 = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
  // 2.2.4·C：先算 bud，再纳入 y 轴上限（游戏等低量 BU 的月均预算虚线不再被裁出画面）
  const bud = Number(r.value.budget_month) || 0
  const maxV = axisMaxCover(maxV0, interval, [...recs, ...ords, bud])
  // canvas 必须实色，禁止 var(--)
  const cOrd = cssColor('--rank-primary-alt')
  const cRec = cssColor('--blue')
  const cTeal = cssColor('--teal')
  // budget_month_disp 为裸数字；receipts_budget 已含「月均预算 X万」整句——勿双拼
  const budRaw = String(r.value.budget_month_disp || '').trim()
  const budFallback = String(r.value.receipts_budget || '').trim()
  const budLabel = budRaw
    ? `月均预算 ${withWanUnit(budRaw)}`
    : budFallback || '月均预算'
  // 3.6.1：顶标仅峰值 + 非空月，避免过密遮挡；空月仍 null 不画假 0
  const peakOrdIdx = peakIndex(ordPlot)
  const peakRecIdx = peakIndex(recPlot)
  const series: Record<string, unknown>[] = [
    {
      name: '下单',
      type: 'bar',
      data: ordPlot,
      barMaxWidth: 28,
      barGap: '12%',
      barCategoryGap: '28%',
      itemStyle: {
        ...barGlowStyle(cOrd),
        borderRadius: [6, 6, 0, 0],
      },
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) =>
          p.dataIndex === peakOrdIdx && od[p.dataIndex] ? od[p.dataIndex] : '',
        fontSize: 12,
      }),
    },
    {
      name: '回款',
      type: 'bar',
      data: recPlot,
      barMaxWidth: 28,
      itemStyle: {
        ...barGlowStyle(cRec),
        borderRadius: [6, 6, 0, 0],
      },
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) =>
          p.dataIndex === peakRecIdx && rd[p.dataIndex] ? rd[p.dataIndex] : '',
        fontSize: 12,
      }),
    },
  ]
  // 月均预算虚线（后端 budget_month 已下发；标签用 budget_month_disp）
  if (bud > 0) {
    series.push({
      name: '月均预算',
      type: 'line',
      data: labels.map(() => bud),
      symbol: 'none',
      lineStyle: {
        type: 'dashed',
        width: 1.25,
        color: cTeal,
        opacity: 0.85,
      },
      itemStyle: { color: cTeal },
      label: {
        show: true,
        position: 'end',
        formatter: () => budLabel,
        color: cTeal,
        fontSize: 11,
        opacity: 0.9,
      },
      tooltip: { show: true },
      z: 3,
    })
  }
  // 3.6.1：减弱网格噪音（色走 token/cssColor，禁硬编码 rgba）
  const gridLine = cssColor('--line-soft') || cssColor('--line') || cssColor('--mut2')
  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { dataIndex: number; seriesName?: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        const budLine = budLabel && budLabel !== '月均预算' ? `<br/>${budLabel}` : ''
        return `${labels[i] || ''}<br/>下单 ${withWanUnit(od[i] || '—')}<br/>回款 ${withWanUnit(rd[i] || '—')}${budLine}`
      },
    },
    legend: {
      data: bud > 0 ? ['下单', '回款', '月均预算'] : ['下单', '回款'],
      bottom: 0,
      itemGap: 16,
      textStyle: legendTextStyle({ fontSize: 12 }),
    },
    grid: { left: 52, right: 28, top: 40, bottom: 52, containLabel: true },
    xAxis: {
      type: 'category',
      data: labels,
      axisTick: { alignWithLabel: true, length: 3 },
      axisLine: { lineStyle: { color: gridLine, width: 1 } },
      axisLabel: axisLabelStyle({
        interval: labels.length > 8 ? 1 : 0,
        margin: 10,
      }),
    },
    yAxis: [
      {
        type: 'value',
        min: minV,
        max: maxV,
        interval,
        splitLine: {
          show: true,
          lineStyle: {
            color: gridLine,
            type: 'dashed',
            width: 1,
            opacity: 0.45,
          },
        },
        axisLabel: {
          formatter: (val: number) => {
            const lab = tickLabel(ticks, val)
            if (lab) return lab
            if (val === 0) return '0'
            return ''
          },
          ...axisLabelStyle(),
        },
      },
    ],
    series,
    ...animBlock(),
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
</script>
<template>
  <SciFiPanel id="receiptsCard" title="下单/回款情况" panel-class="rc-card">
    <div v-if="hasSeries" class="rc-layout" :class="{ 'rc-solo': !sideVisible }">
      <div class="rc-body" data-chart="receipts">
        <EchartsHost :option="option" />
      </div>
      <aside v-if="sideVisible && side" class="rc-side" aria-label="下单/回款摘要" data-testid="rc-year-progress">
        <div class="rc-side-title">年度进度</div>
        <div class="rc-metric" data-testid="rc-metric-order">
          <div class="rc-metric-label">本年下单</div>
          <div class="rc-metric-value">{{ withWanUnit(side.orders_disp) }}</div>
          <template v-if="side.order_target_disp">
            <div class="rc-bud-h">
              <span>完成率</span>
              <strong data-testid="rc-order-pct">{{ side.order_pct_disp }}</strong>
            </div>
            <div class="rc-bud-sub">
              目标 {{ withWanUnit(side.order_target_disp) }}
              <span v-if="side.order_remain_disp" class="rc-remain">
                · {{ side.order_remain_hint || '尚差' }} {{ withWanUnit(side.order_remain_disp) }}
              </span>
            </div>
            <div class="rc-bud-bar" data-testid="rc-bud-order">
              <i :style="{ width: (side.order_bar_w || '0') + '%' }" />
            </div>
          </template>
        </div>
        <div class="rc-metric" data-testid="rc-metric-receipt">
          <div class="rc-metric-label">本年回款</div>
          <div class="rc-metric-value rc-v-rec">{{ withWanUnit(side.receipts_disp) }}</div>
          <template v-if="side.receipt_target_disp">
            <div class="rc-bud-h">
              <span>完成率</span>
              <strong data-testid="rc-receipt-pct">{{ side.receipt_pct_disp }}</strong>
            </div>
            <div class="rc-bud-sub">
              目标 {{ withWanUnit(side.receipt_target_disp) }}
              <span v-if="side.receipt_remain_disp" class="rc-remain">
                · {{ side.receipt_remain_hint || '尚差' }} {{ withWanUnit(side.receipt_remain_disp) }}
              </span>
            </div>
            <div class="rc-bud-bar" data-testid="rc-bud-receipt">
              <i :style="{ width: (side.receipt_bar_w || '0') + '%' }" />
            </div>
          </template>
        </div>
      </aside>
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </SciFiPanel>
</template>

