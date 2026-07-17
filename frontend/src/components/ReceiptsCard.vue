<script setup lang="ts">
/** 回款柱线：序列与轴标签来自 VM；任务书51·B7：轴刻度精确查表。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import type { AxisTick, ReceiptsVM } from '../types/vm'

const store = useCockpitStore()
const r = computed((): Partial<ReceiptsVM> => store.vm?.receipts || {})

function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

const option = computed(() => {
  const labels = r.value.labels || []
  const recs = r.value.receipts || []
  const ords = r.value.orders || []
  const rd = r.value.receipts_disp || []
  const od = r.value.orders_disp || []
  const ticks = r.value.y_axis_ticks || []
  const maxV = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
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
      min: minV,
      max: maxV,
      interval,
      axisLabel: { formatter: (val: number) => tickLabel(ticks, val) },
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
          position: 'top',
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: 10,
        },
      },
    ],
    animationDuration: 700,
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
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
