<script setup lang="ts">
/**
 * 费用月度趋势：任务书54·C 唯一换图型 — 按月堆叠柱 + 柱顶合计数字。
 * 序列/轴/合计显示串全部来自 VM（area_*）；前端零金额运算。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import { themeInkColor } from '../echarts-theme'
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
  const ink = themeInkColor()
  const n = labels.length
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { seriesName: string; dataIndex: number; value: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const lines = [`${labels[i] || ''} 合计 ${totals[i] || '—'}万`]
        for (const p of params || []) {
          if (p.seriesName === '_柱顶合计') continue
          const s = seriesIn.find((x) => x.name === p.seriesName)
          const d = s?.data_disp?.[i] || String(p.value)
          lines.push(`${p.seriesName}: ${d}万`)
        }
        return lines.join('<br/>')
      },
    },
    legend: { data: seriesIn.map((s) => s.name) },
    grid: { left: 54, right: 24, top: 52, bottom: 36, containLabel: false },
    xAxis: { type: 'category', data: labels, boundaryGap: true },
    yAxis: {
      type: 'value',
      min: minV,
      // 柱顶数字留白：轴 max 略抬一格（仅视觉，刻度仍用 VM ticks）
      max: maxV != null && interval ? maxV + interval : maxV,
      interval,
      axisLabel: { formatter: (v: number) => tickLabel(ticks, v) || '' },
    },
    /*
     * 堆叠柱 + 柱顶合计：
     * 真实大类 series 全 stack；再叠一层极小透明柱，label = VM area_totals_disp。
     * 0.001 相对万元轴不可见，但保证 ECharts 对「零高」也画 label。
     * label.color 必须用 themeInkColor() 解析后的 hex（canvas 不认 CSS var）。
     */
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
        name: '_柱顶合计',
        type: 'bar' as const,
        stack: 'total',
        data: Array.from({ length: n }, () => 0.001),
        itemStyle: { color: 'transparent', borderWidth: 0 },
        barMaxWidth: 36,
        label: {
          show: true,
          position: 'top' as const,
          distance: 4,
          formatter: (p: { dataIndex: number }) => totals[p.dataIndex] || '',
          fontSize: 11,
          fontWeight: 600,
          color: ink,
        },
        labelLayout: { hideOverlap: false },
        clip: false,
        tooltip: { show: false },
        silent: true,
        legendHoverLink: false,
        z: 10,
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
    <div class="rc-body" data-chart="expense-trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
