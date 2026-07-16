<script setup lang="ts">
/** 回款柱线：序列来自 VM。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const r = computed(() => (store.vm?.receipts || {}) as Record<string, unknown>)
const html = computed(() => (r.value.receipts_budget as string) || (r.value.receipts_html as string) || '')

const option = computed(() => {
  const labels = (r.value.labels as string[]) || []
  const recs = (r.value.receipts as number[]) || []
  const ords = (r.value.orders as number[]) || []
  const rd = (r.value.receipts_disp as string[]) || []
  const od = (r.value.orders_disp as string[]) || []
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>回款 ${rd[i] || '—'}万<br/>下单 ${od[i] || '—'}万`
      },
    },
    legend: { data: ['回款', '下单'] },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value' },
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
    <div class="card-h">回款情况 <span class="tag">ECharts</span></div>
    <div v-if="hasSeries" class="rc-body">
      <EchartsHost :option="option" />
    </div>
    <div v-else v-html="html"></div>
  </div>
</template>
