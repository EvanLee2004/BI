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
  const labels = (t.labels || []).map((x) => String(x))
  const rev = (t.revenue || []).map((x) => Number(x) || 0)
  const cost = (t.cost || []).map((x) => Number(x) || 0)
  const margin = (t.margin_pct || []).map((x) => Number(x) || 0)
  const revD = (t.revenue_disp || []).map((x) => String(x ?? ''))
  const costD = (t.cost_disp || []).map((x) => String(x ?? ''))
  const marD = (t.margin_pct_disp || []).map((x) => String(x ?? ''))
  const ticks = t.y_axis_ticks || []
  const maxV = t.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    t.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = t.y_axis_min ?? 0
  const cRev = '#22d3ee'
  const cCost = '#64769e'
  const cMar = '#c084fc'
  const series: Record<string, unknown>[] = [
    {
      name: '收入',
      type: 'bar',
      data: rev,
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
      data: cost,
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
      data: margin,
      symbol: 'circle',
      symbolSize: 8,
      itemStyle: pointGlowStyle(cMar),
      lineStyle: lineGlowStyle(cMar, 2.5),
      label: dataLabelStyle({
        formatter: (p: { dataIndex: number }) => marD[p.dataIndex] || '',
      }),
      emphasis: { focus: 'series', scale: true },
    },
  ]
  const breath = breathScatterSeries('毛利率', margin, cMar, 1)
  if (breath) series.push(breath)
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>收入 ${revD[i] || '—'}万<br/>成本 ${costD[i] || '—'}万<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: { data: ['收入', '成本', '毛利率'], textStyle: legendTextStyle() },
    grid: { left: 64, right: 48, top: 36, bottom: 28 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: axisLabelStyle(),
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
    <div class="rc-body" data-chart="trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
