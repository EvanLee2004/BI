<script setup lang="ts">
/** 收入·毛利趋势：轴标签/数据标签后端下发；无技术字样。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const trend = computed(() => (store.vm?.trend || {}) as Record<string, unknown>)

function axisFormatter(ticks: { value: number; label: string }[]) {
  return (val: number) => {
    if (!ticks.length) return ''
    let best = ticks[0]
    let bestD = Math.abs(val - best.value)
    for (const t of ticks) {
      const d = Math.abs(val - t.value)
      if (d < bestD) {
        best = t
        bestD = d
      }
    }
    // 仅在接近某个后端刻度时显示，避免乱标
    if (bestD > (ticks[1] ? Math.abs(ticks[1].value - ticks[0].value) * 0.25 : 1)) return ''
    return best.label
  }
}

const option = computed(() => {
  const t = trend.value
  const labels = (t.labels as string[]) || []
  const rev = (t.revenue as number[]) || []
  const cost = (t.cost as number[]) || []
  const margin = (t.margin_pct as number[]) || []
  const revD = (t.revenue_disp as string[]) || []
  const costD = (t.cost_disp as string[]) || []
  const marD = (t.margin_pct_disp as string[]) || []
  const ticks = (t.y_axis_ticks as { value: number; label: string }[]) || []
  const maxV = ticks.length ? ticks[ticks.length - 1].value : undefined
  const interval = ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>收入 ${revD[i] || '—'}万<br/>成本 ${costD[i] || '—'}万<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: { data: ['收入', '成本', '毛利率'] },
    grid: { left: 64, right: 48, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: labels },
    yAxis: [
      {
        type: 'value',
        min: 0,
        max: maxV,
        interval,
        axisLabel: { formatter: axisFormatter(ticks) },
      },
      { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    ],
    series: [
      {
        name: '收入',
        type: 'bar',
        data: rev,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: 'top',
          formatter: (p: { dataIndex: number }) => revD[p.dataIndex] || '',
          fontSize: 10,
        },
      },
      {
        name: '成本',
        type: 'bar',
        data: cost,
        label: {
          show: true,
          position: 'top',
          formatter: (p: { dataIndex: number }) => costD[p.dataIndex] || '',
          fontSize: 10,
        },
      },
      {
        name: '毛利率',
        type: 'line',
        yAxisIndex: 1,
        data: margin,
        label: {
          show: true,
          formatter: (p: { dataIndex: number }) => marD[p.dataIndex] || '',
          fontSize: 10,
        },
      },
    ],
    animationDuration: 700,
  }
})
</script>
<template>
  <div class="card">
    <div class="card-h">收入 · 毛利趋势</div>
    <div class="rc-body">
      <EchartsHost :option="option" />
    </div>
  </div>
</template>
