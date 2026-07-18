<script setup lang="ts">
/**
 * 回款情况：紫柱下单 + 青柱回款 + 金黄回款率线 + 月均预算虚线 + 右侧摘要条。
 * 显示串全 VM；前端零金额运算（铁律2）。
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
  lineGlowStyle,
  pointGlowStyle,
} from '../chart-fx'
import { axisMaxCover, padYearMonths } from '../chart-months'
import type { AxisTick, ReceiptsVM } from '../types/vm'

const store = useCockpitStore()
const r = computed((): Partial<ReceiptsVM> => store.vm?.receipts || {})

function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

const side = computed(() => {
  const map = r.value.summary_by_period || {}
  const pk = store.period || ''
  return map[pk] || map[store.vm?.year_key || ''] || null
})

const option = computed(() => {
  const rawLabels = (r.value.labels || []).map((x) => String(x))
  const rawRecs = (r.value.receipts || []).map((x) => Number(x) || 0)
  const rawOrds = (r.value.orders || []).map((x) => Number(x) || 0)
  const rawRd = (r.value.receipts_disp || []).map((x) => String(x ?? ''))
  const rawOd = (r.value.orders_disp || []).map((x) => String(x ?? ''))
  // 回款率金黄线：几何取自后端已下发的百分比显示串，标签用该串——前端不做比率运算
  const rawRatioD = (r.value.ratio_pct_disp || []).map((x) => String(x ?? ''))
  const rawRatio = rawRatioD.map((s) => {
    const n = parseFloat(s)
    return Number.isFinite(n) ? n : 0
  })
  const padded = padYearMonths(
    rawLabels,
    [rawRecs, rawOrds, rawRatio],
    [rawRd, rawOd, rawRatioD],
  )
  const labels = padded.labels
  const recs = padded.series[0]
  const ords = padded.series[1]
  const ratio = padded.series[2]
  const rd = padded.disps[0]
  const od = padded.disps[1]
  const ratioD = padded.disps[2]
  const empty = (i: number) => !rd[i] && !od[i]
  const recPlot = recs.map((v, i) => (empty(i) ? null : v))
  const ordPlot = ords.map((v, i) => (empty(i) ? null : v))
  const ratioPlot = ratio.map((v, i) => (empty(i) || !ratioD[i] ? null : v))
  const ticks = r.value.y_axis_ticks || []
  const maxV0 = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
  const maxV = axisMaxCover(maxV0, interval, [...recs, ...ords])
  const cOrd = '#a78bfa'
  const cRec = '#22d3ee'
  const cRatio = '#fbbf24'
  const bud = Number(r.value.budget_month) || 0
  const budDisp = String(r.value.budget_month_disp || r.value.receipts_budget || '')
  const series: Record<string, unknown>[] = [
    {
      name: '下单',
      type: 'bar',
      data: ordPlot,
      barMaxWidth: 28,
      itemStyle: barGlowStyle(cOrd),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
        fontSize: 11,
      }),
    },
    {
      name: '回款',
      type: 'bar',
      data: recPlot,
      barMaxWidth: 28,
      itemStyle: barGlowStyle(cRec),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
        fontSize: 11,
      }),
    },
    {
      name: '回款率',
      type: 'line',
      yAxisIndex: 1,
      data: ratioPlot,
      symbol: 'circle',
      symbolSize: 8,
      connectNulls: false,
      z: 5,
      itemStyle: pointGlowStyle(cRatio),
      lineStyle: lineGlowStyle(cRatio, 2.5),
      label: dataLabelStyle({
        formatter: (p: { dataIndex: number }) => ratioD[p.dataIndex] || '',
      }),
      emphasis: { focus: 'series', scale: true },
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
        width: 1.5,
        color: '#2dd4bf',
      },
      itemStyle: { color: '#2dd4bf' },
      label: {
        show: true,
        position: 'end',
        formatter: () => (budDisp ? `月均预算 ${budDisp}万` : '月均预算'),
        color: '#2dd4bf',
        fontSize: 11,
      },
      tooltip: { show: true },
      z: 3,
    })
  }
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number; seriesName?: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        const tail = ratioD[i] ? `<br/>回款率 ${ratioD[i]}` : ''
        const budLine = budDisp ? `<br/>月均预算 ${budDisp}万` : ''
        return `${labels[i] || ''}<br/>下单 ${od[i] || '—'}万<br/>回款 ${rd[i] || '—'}万${tail}${budLine}`
      },
    },
    legend: {
      data: bud > 0 ? ['下单', '回款', '回款率', '月均预算'] : ['下单', '回款', '回款率'],
      bottom: 0,
      textStyle: legendTextStyle(),
    },
    grid: { left: 64, right: 52, top: 40, bottom: 48 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: axisLabelStyle({ interval: 0 }),
    },
    yAxis: [
      {
        type: 'value',
        min: minV,
        max: maxV,
        interval,
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
      {
        type: 'value',
        min: 0,
        max: 100,
        splitLine: { show: false },
        axisLabel: { formatter: '{value}%', ...axisLabelStyle() },
      },
    ],
    series,
    ...animBlock(),
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
</script>
<template>
  <SciFiPanel id="receiptsCard" title="回款情况" panel-class="rc-card">
    <div v-if="hasSeries" class="rc-layout">
      <div class="rc-body" data-chart="receipts">
        <EchartsHost :option="option" />
      </div>
      <aside v-if="side" class="rc-side" aria-label="回款摘要">
        <div class="rc-hero">
          <div class="rc-hero-row">
            <span class="rc-k">总下单</span>
            <span class="rc-v">{{ side.orders_disp }}<em>万</em></span>
          </div>
          <div class="rc-hero-row">
            <span class="rc-k">总回款</span>
            <span class="rc-v rc-v-rec">{{ side.receipts_disp }}<em>万</em></span>
          </div>
          <div class="rc-hero-row rc-gap">
            <span class="rc-k">{{ side.gap_hint }}</span>
            <span class="rc-v">{{ side.gap_disp }}<em>万</em></span>
          </div>
          <div v-if="side.period_label" class="rc-pl">{{ side.period_label }}</div>
        </div>
        <div class="rc-rate">
          <div class="rc-rate-h">
            <span>回款占下单</span>
            <strong>{{ side.ratio_disp }}</strong>
          </div>
          <div class="rc-rate-bar"><i :style="{ width: (side.bar_w || '0') + '%' }" /></div>
        </div>
        <div v-if="side.receipt_target_disp" class="rc-bud">
          <div class="rc-bud-h">
            <span>{{ side.receipt_title || '回款年目标' }}</span>
            <strong>{{ side.receipt_pct_disp }}</strong>
          </div>
          <div class="rc-bud-sub">目标 {{ side.receipt_target_disp }}万</div>
          <div class="rc-bud-bar"><i :style="{ width: (side.receipt_bar_w || '0') + '%' }" /></div>
        </div>
        <div v-if="side.order_target_disp" class="rc-bud">
          <div class="rc-bud-h">
            <span>{{ side.order_title || '下单年目标' }}</span>
            <strong>{{ side.order_pct_disp }}</strong>
          </div>
          <div class="rc-bud-sub">目标 {{ side.order_target_disp }}万</div>
          <div class="rc-bud-bar"><i :style="{ width: (side.order_bar_w || '0') + '%' }" /></div>
        </div>
      </aside>
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </SciFiPanel>
</template>

<style scoped>
.rc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 240px);
  gap: 12px;
  align-items: stretch;
  min-height: 280px;
}
.rc-body {
  min-width: 0;
  min-height: 280px;
}
.rc-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px 4px 8px;
  border-left: 1px solid rgba(125, 211, 252, 0.12);
  font-size: 12.5px;
}
.rc-hero-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
}
.rc-k {
  color: var(--note, #8b9bb4);
  font-weight: 500;
}
.rc-v {
  font-family: var(--num-font, ui-monospace, monospace);
  font-weight: 700;
  color: var(--ink, #e8eef8);
}
.rc-v em {
  font-style: normal;
  font-size: 11px;
  font-weight: 600;
  opacity: 0.75;
  margin-left: 1px;
}
.rc-v-rec {
  color: #22d3ee;
}
.rc-pl {
  font-size: 11px;
  color: var(--note, #8b9bb4);
  margin-top: 2px;
}
.rc-rate-h,
.rc-bud-h {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
  font-weight: 600;
}
.rc-rate-bar,
.rc-bud-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(125, 211, 252, 0.12);
  overflow: hidden;
}
.rc-rate-bar i,
.rc-bud-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #22d3ee, #a78bfa);
  border-radius: 3px;
}
.rc-bud-sub {
  font-size: 11px;
  color: var(--note, #8b9bb4);
  margin-bottom: 3px;
}
@media (max-width: 900px) {
  .rc-layout {
    grid-template-columns: 1fr;
  }
  .rc-side {
    border-left: none;
    border-top: 1px solid rgba(125, 211, 252, 0.12);
    padding: 10px 0 0;
  }
}
</style>
