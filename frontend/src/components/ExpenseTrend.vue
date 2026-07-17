<script setup lang="ts">
/** 费用月度堆叠面积图：序列/轴标签来自 VM（任务书52·F-4 接 area_y_axis_ticks）。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
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
    xAxis: { type: 'category', data: labels, boundaryGap: true },
    yAxis: {
      type: 'value',
      min: minV,
      max: maxV,
      interval,
      axisLabel: { formatter: (v: number) => tickLabel(ticks, v) },
    },
    /* 任务书54·C：唯一换图型 — 堆叠面积 → 按月堆叠柱 + 柱顶合计 */
    series: [
      ...seriesIn.map((s) => ({
        name: s.name,
        type: 'bar' as const,
        stack: 'total',
        emphasis: { focus: 'series' as const },
        data: s.data,
        barMaxWidth: 36,
      })),
      {
        name: '合计',
        type: 'bar' as const,
        stack: 'total',
        data: seriesIn.length
          ? (seriesIn[0].data || []).map(() => 0)
          : [],
        itemStyle: { color: 'transparent' },
        label: {
          show: true,
          position: 'top' as const,
          formatter: (p: { dataIndex: number }) => totals[p.dataIndex] || '',
          fontSize: 10,
          color: 'var(--ink, #eaf1ff)',
        },
        tooltip: { show: false },
        silent: true,
        barMaxWidth: 36,
      },
    ],
    animationDuration: 800,
  }
})
</script>
<template>
  <SciFiPanel
    id="expTrendCard"
    title="费用月度趋势 · 按报表大类"
    tag="按有数月份 · 堆叠柱"
    panel-class="exp-trend-card"
  >
    <div class="rc-body">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
