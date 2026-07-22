<script setup lang="ts">
/** 收入·毛利趋势：轴标签/数据标签后端下发；无技术字样。任务书51·B7：轴刻度精确查表。
 *  任务书54.4：零持续动画 + 无呼吸特效；54.3 图区自适应保留。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  areaGradient,
  axisLabelStyle,
  barGlowStyle,
  dataLabelStyle,
  legendTextStyle,
  lineGlowStyle,
  pointGlowStyle,
} from '../chart-fx'
import { currentThemeMode } from '../echarts-theme'
import { axisMaxCover, clipToCurrentMonth, padYearMonths, ratioAxisBounds, resolveMonthCap } from '../chart-months'
import { withWanUnit } from '../utils/disp'
import { themeMode } from '../utils/theme'
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
  void themeMode.value
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
  const monthCap = resolveMonthCap({
    chartMonthMax: (t as { chart_month_max?: number }).chart_month_max
      ?? (store.vm as { chart_month_max?: number } | null)?.chart_month_max,
    defaultEnd: store.vm?.daily?.default_end,
  })
  const clipped = clipToCurrentMonth(padded.labels, padded.series, padded.disps, monthCap)
  const labels = clipped.labels
  const rev = clipped.series[0]
  const cost = clipped.series[1]
  const margin = clipped.series[2]
  const revD = clipped.disps[0]
  const costD = clipped.disps[1]
  const marD = clipped.disps[2]
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
  const marBounds = ratioAxisBounds(marPlot)
  /* 54.2 对照基准；2.3.0 霓虹提亮 */
  const neon = currentThemeMode() === 'neon'
  const cRev = neon ? '#2ff3ff' : '#22d3ee'
  const cCost = neon ? '#6b7fa0' : '#64769e'
  const cMar = neon ? '#ffd23f' : '#fbbf24'
  const area = areaGradient(cRev)
  const series: Record<string, unknown>[] = [
    {
      name: '收入',
      type: 'bar',
      data: revPlot,
      itemStyle: barGlowStyle(cRev),
      ...(area ? { areaStyle: area } : {}),
      /* 54.5：只标收入柱顶，避免与成本/毛利率三重叠难辨 */
      label: dataLabelStyle({
        position: 'top',
        distance: 4,
        formatter: (p: { dataIndex: number }) => revD[p.dataIndex] || '',
      }),
      emphasis: {
        focus: 'series',
        itemStyle: { shadowBlur: neon ? 10 : 4, shadowColor: neon ? 'rgba(47,243,255,0.45)' : 'rgba(34,211,238,0.4)' },
      },
    },
    {
      name: '成本',
      type: 'bar',
      data: costPlot,
      itemStyle: barGlowStyle(cCost, true),
      label: { show: false },
      emphasis: { focus: 'series' },
    },
    {
      name: '毛利率',
      type: 'line',
      yAxisIndex: 1,
      data: marPlot,
      symbol: 'circle',
      symbolSize: neon ? 9 : 8,
      connectNulls: false,
      itemStyle: pointGlowStyle(cMar),
      lineStyle: lineGlowStyle(cMar, 2.5),
      /* 面积渐变仅毛利率线可选；收入柱已有 area 占位跳过 */
      ...(neon ? { areaStyle: areaGradient(cMar) } : {}),
      label: dataLabelStyle({
        position: 'top',
        distance: 8,
        color: cMar,
        formatter: (p: { dataIndex: number }) => marD[p.dataIndex] || '',
      }),
      emphasis: { focus: 'series', scale: true },
    },
  ]
  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        return `${labels[i] || ''}<br/>收入 ${withWanUnit(revD[i] || '—')}<br/>成本 ${withWanUnit(costD[i] || '—')}<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: {
      data: ['收入', '成本', '毛利率'],
      bottom: 4,
      left: 'center',
      textStyle: legendTextStyle(),
    },
    /* R-05：grid 底边距含图例+月份轴，避免 BU 页底部裁切 */
    grid: { left: 56, right: 48, top: 48, bottom: 64, containLabel: true },
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
        min: marBounds.min,
        max: marBounds.max,
        axisLabel: { formatter: '{value}%', ...axisLabelStyle() },
      },
    ],
    series,
    ...animBlock(),
  }
})
</script>
<template>
  <SciFiPanel id="trendChartCard" title="收入 · 毛利趋势" panel-class="trend-chart-card">
    <!-- 54.3 / 54.14 R-23：图区随面板高自适应填充 -->
    <div class="rc-body trend-fill" data-chart="trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>

<style scoped>
.trend-fill {
  min-height: 360px;
  height: 400px;
}
</style>
