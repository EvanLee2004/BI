<script setup lang="ts">
/** 费用月度堆叠面积图：系列数据/标签来自 VM。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const exp = computed(() => (store.vm?.expense || {}) as Record<string, unknown>)

const option = computed(() => {
  const e = exp.value
  const labels = (e.area_labels as string[]) || []
  const seriesIn = (e.area_series as { name: string; data: number[]; data_disp: string[] }[]) || []
  const totals = (e.area_totals_disp as string[]) || []
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
      axisLabel: {
        // 显示原值；金额标签在 tooltip 用 data_disp（后端串）
        formatter: (v: number) => String(v),
      },
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
    <div class="card-h">费用月度趋势 · 按报表大类 <span class="tag">1~12 月 · 面积</span></div>
    <div class="rc-body">
      <EchartsHost :option="option" />
    </div>
  </div>
</template>
