<script setup lang="ts">
/** 费用月度堆叠面积图：序列/轴标签来自 VM（任务书52·F-4 接 area_y_axis_ticks）。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
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
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { seriesName: string; dataIndex: number; value: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const lines = [`${labels[i] || ''} 合计 ${totals[i] || '—'}万`]
        for (const p of params || []) {
          const s = seriesIn.find((x) => x.name === p.seriesName)
          const d = s?.data_disp?.[i] || String(p.value)
          lines.push(`${p.seriesName}: ${d}万`)
        }
        return lines.join('<br/>')
      },
    },
    legend: { data: seriesIn.map((s) => s.name) },
    xAxis: { type: 'category', data: labels, boundaryGap: false },
    yAxis: {
      type: 'value',
      min: minV,
      max: maxV,
      interval,
      axisLabel: { formatter: (v: number) => tickLabel(ticks, v) },
    },
    series: seriesIn.map((s) => ({
      name: s.name,
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.72 },
      emphasis: { focus: 'series' },
      data: s.data,
      smooth: true,
    })),
    animationDuration: 800,
  }
})
</script>
<template>
  <div class="card exp-trend-card" id="expTrendCard">
    <div class="card-h">
      费用月度趋势 · 按报表大类
      <span class="tag">按有数月份 · 面积</span>
    </div>
    <div class="rc-body">
      <EchartsHost :option="option" />
    </div>
  </div>
</template>
