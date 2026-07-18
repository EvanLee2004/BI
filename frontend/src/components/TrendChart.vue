<script setup lang="ts">
/** 收入·毛利趋势：轴标签/数据标签后端下发；无技术字样。任务书51·B7：轴刻度精确查表。
 *  任务书54.1：V4 呼吸发光 + V6 文字清晰度。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  animDuration,
  axisLabelStyle,
  barGlowStyle,
  breathScatterSeries,
  dataLabelStyle,
  legendTextStyle,
  lineGlowStyle,
  pointGlowStyle,
} from '../chart-fx'
import { axisMaxCover, padYearMonths } from '../chart-months'
import type { AxisTick, TrendVM } from '../types/vm'

const store = useCockpitStore()
const trend = computed((): Partial<TrendVM> => store.vm?.trend || {})

/** 后端 ticks 精确匹配（禁最近刻度扫描）。 */
function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return String(t.label ?? '')
  }
  return ''
}

const option = computed(() => {
  const t = trend.value
  const rawLabels = (t.labels || []).map((x) => String(x))
  const rawRev = (t.revenue || []).map((x) => Number(x) || 0)
  const rawCost = (t.cost || []).map((x) => Number(x) || 0)
  const rawMar = (t.margin_pct || []).map((x) => Number(x) || 0)
  const rawRevD = (t.revenue_disp || []).map((x) => String(x ?? ''))
  const rawCostD = (t.cost_disp || []).map((x) => String(x ?? ''))
  const rawMarD = (t.margin_pct_disp || []).map((x) => String(x ?? ''))
  const padded = padYearMonths(
    rawLabels,
    [rawRev, rawCost, rawMar],
    [rawRevD, rawCostD, rawMarD],
  )
  const labels = padded.labels
  const rev = padded.series[0]
  const cost = padded.series[1]
  const margin = padded.series[2]
  const revD = padded.disps[0]
  const costD = padded.disps[1]
  const marD = padded.disps[2]
  const empty = (i: number) => !revD[i] && !costD[i] && !marD[i]
  const revPlot = rev.map((v, i) => (empty(i) ? null : v))
  const costPlot = cost.map((v, i) => (empty(i) ? null : v))
  const marPlot = margin.map((v, i) => (empty(i) ? null : v))
  const ticks = t.y_axis_ticks || []
  const maxV0 = t.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    t.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = t.y_axis_min ?? 0
  const maxV = axisMaxCover(maxV0, interval, [...rev, ...cost])
  /* 54.2 对照基准：收入青柱 / 成本灰柱 / 毛利率金黄线 */
  const cRev = '#22d3ee'
  const cCost = '#64769e'
  const cMar = '#fbbf24'
  const series: Record<string, unknown>[] = [
    {
      name: '收入',
      type: 'bar',
      data: revPlot,
      itemStyle: barGlowStyle(cRev),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => revD[p.dataIndex] || '',
      }),
      emphasis: {
        itemStyle: { shadowBlur: 20, shadowColor: 'rgba(34,211,238,0.65)' },
      },
    },
    {
      name: '成本',
      type: 'bar',
      data: costPlot,
      itemStyle: barGlowStyle(cCost, true),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => costD[p.dataIndex] || '',
      }),
    },
    {
      name: '毛利率',
      type: 'line',
      yAxisIndex: 1,
      data: marPlot,
      symbol: 'circle',
      symbolSize: 8,
      connectNulls: false,
      itemStyle: pointGlowStyle(cMar),
      lineStyle: lineGlowStyle(cMar, 2.5),
      label: dataLabelStyle({
        formatter: (p: { dataIndex: number }) => marD[p.dataIndex] || '',
      }),
      emphasis: { focus: 'series', scale: true },
    },
  ]
  const breath = breathScatterSeries(
    '毛利率',
    marPlot.map((x) => (x == null ? 0 : x)),
    cMar,
    1,
  )
  if (breath) {
    breath.data = marPlot.map((x) => (x == null ? '-' : x))
    series.push(breath)
  }
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        return `${labels[i] || ''}<br/>收入 ${revD[i] || '—'}万<br/>成本 ${costD[i] || '—'}万<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: {
      data: ['收入', '成本', '毛利率'],
      bottom: 0,
      textStyle: legendTextStyle(),
    },
    grid: { left: 64, right: 48, top: 40, bottom: 48 },
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
          formatter: (val: number) => tickLabel(ticks, val),
          ...axisLabelStyle(),
        },
      },
      {
        type: 'value',
        max: 100,
        axisLabel: { formatter: '{value}%', ...axisLabelStyle() },
      },
    ],
    series,
    ...animBlock(animDuration(700)),
  }
})
</script>
<template>
  <SciFiPanel id="trendChartCard" title="收入 · 毛利趋势" panel-class="trend-chart-card">
    <!-- 54.3：图区随面板高自适应填充（禁固定高溢出被压缩面板 overflow:hidden 裁掉月份轴，营销等小值BU踩过） -->
    <div class="rc-body trend-fill" data-chart="trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
