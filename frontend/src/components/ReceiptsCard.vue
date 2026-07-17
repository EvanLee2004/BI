<script setup lang="ts">
/** 回款柱线：序列与轴标签来自 VM；无「ECharts」技术字样。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const r = computed(() => (store.vm?.receipts || {}) as Record<string, unknown>)

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
    if (bestD > (ticks[1] ? Math.abs(ticks[1].value - ticks[0].value) * 0.25 : 1)) return ''
    return best.label
  }
}

const option = computed(() => {
  const labels = (r.value.labels as string[]) || []
  const recs = (r.value.receipts as number[]) || []
  const ords = (r.value.orders as number[]) || []
  const rd = (r.value.receipts_disp as string[]) || []
  const od = (r.value.orders_disp as string[]) || []
  const ticks = (r.value.y_axis_ticks as { value: number; label: string }[]) || []
  const maxV = ticks.length ? ticks[ticks.length - 1].value : undefined
  const interval = ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>回款 ${rd[i] || '—'}万<br/>下单 ${od[i] || '—'}万`
      },
    },
    legend: { data: ['回款', '下单'] },
    grid: { left: 64, right: 16, top: 32, bottom: 28 },
    xAxis: { type: 'category', data: labels },
    yAxis: {
      type: 'value',
      min: 0,
      max: maxV,
      interval,
      axisLabel: { formatter: axisFormatter(ticks) },
    },
    series: [
      {
        name: '回款',
        type: 'bar',
        data: recs,
        label: {
          show: true,
          position: 'top',
          formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
          fontSize: 10,
        },
      },
      {
        name: '下单',
        type: 'line',
        data: ords,
        label: {
          show: true,
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: 10,
        },
      },
    ],
    animationDuration: 700,
  }
})
const hasSeries = computed(() => ((r.value.labels as string[]) || []).length > 0)
</script>
<template>
  <div class="card rc-card">
    <div class="card-h">回款情况</div>
    <div v-if="hasSeries" class="rc-body">
      <EchartsHost :option="option" />
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </div>
</template>
