<script setup lang="ts">
/**
 * 费用月度趋势：任务书54.1·V7 — 多系列发光折线图（替换旧面积/柱图型）。
 * 序列/轴/合计显示串全部来自 VM（area_*）；前端零金额运算；数据零变化。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  animDuration,
  axisLabelStyle,
  breathScatterSeries,
  dataLabelStyle,
  legendTextStyle,
  lineGlowStyle,
  pointGlowStyle,
  SERIES_PALETTE,
} from '../chart-fx'
import type { AxisTick, ExpenseVM } from '../types/vm'

const store = useCockpitStore()
const exp = computed((): Partial<ExpenseVM> => store.vm?.expense || {})

function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

const option = computed(() => {
  const e = exp.value
  const labels = e.area_labels || []
  const seriesIn = e.area_series || []
  const totals = e.area_totals_disp || []
  const ticks = e.area_y_axis_ticks || []
  const maxV = e.area_y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    e.area_y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = e.area_y_axis_min ?? 0
  const series: Record<string, unknown>[] = []
  seriesIn.forEach((s, idx) => {
    const hex = SERIES_PALETTE[idx % SERIES_PALETTE.length]
    const data = (s.data || []).map((x) => Number(x) || 0)
    series.push({
      name: s.name,
      type: 'line' as const,
      data,
      smooth: 0.25,
      symbol: 'circle',
      symbolSize: 8,
      showSymbol: true,
      itemStyle: pointGlowStyle(hex),
      lineStyle: lineGlowStyle(hex, 2.6),
      emphasis: { focus: 'series' as const, scale: true },
      label:
        idx === 0
          ? dataLabelStyle({
              position: 'top',
              formatter: (p: { dataIndex: number }) => totals[p.dataIndex] || '',
              fontSize: 11,
            })
          : { show: false },
    })
    const breath = breathScatterSeries(s.name, data, hex, 0)
    if (breath) series.push(breath)
  })
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { seriesName: string; dataIndex: number; value: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const lines = [`${labels[i] || ''} 合计 ${totals[i] || '—'}万`]
        for (const p of params || []) {
          if (String(p.seriesName || '').endsWith('·glow')) continue
          const s = seriesIn.find((x) => x.name === p.seriesName)
          const d = s?.data_disp?.[i] || String(p.value)
          lines.push(`${p.seriesName}: ${d}万`)
        }
        return lines.join('<br/>')
      },
    },
    legend: {
      data: seriesIn.map((s) => s.name),
      textStyle: legendTextStyle(),
      type: 'scroll',
      top: 0,
    },
    grid: { left: 54, right: 24, top: 52, bottom: 36, containLabel: false },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: false,
      axisLabel: axisLabelStyle(),
    },
    yAxis: {
      type: 'value',
      min: minV,
      max: maxV,
      interval,
      axisLabel: {
        formatter: (v: number) => tickLabel(ticks, v) || '',
        ...axisLabelStyle(),
      },
    },
    series,
    ...animBlock(animDuration(800)),
  }
})
</script>
<template>
  <SciFiPanel
    id="expTrendCard"
    title="费用月度趋势 · 按报表大类"
    tag="按有数月份 · 多系列折线"
    panel-class="exp-trend-card"
  >
    <div class="rc-body" data-chart="expense-trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
