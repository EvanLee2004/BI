<script setup lang="ts">
/** 板块二左：收入·成本柱 + 毛利率线。数据/显示串全部来自 VM，前端零运算。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'

const store = useCockpitStore()
const trend = computed(() => (store.vm?.trend || {}) as Record<string, unknown>)

const option = computed(() => {
  const t = trend.value
  const labels = (t.labels as string[]) || []
  const rev = (t.revenue as number[]) || []
  const cost = (t.cost as number[]) || []
  const margin = (t.margin_pct as number[]) || []
  const revD = (t.revenue_disp as string[]) || []
  const costD = (t.cost_disp as string[]) || []
  const marD = (t.margin_pct_disp as string[]) || []
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>收入 ${revD[i] || '—'}万<br/>成本 ${costD[i] || '—'}万<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: { data: ['收入', '成本', '毛利率'] },
    xAxis: { type: 'category', data: labels },
    yAxis: [
      { type: 'value', name: '万' },
      { type: 'value', name: '%', max: 100 },
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
    <div class="card-h">收入 · 毛利趋势 <span class="tag">ECharts</span></div>
    <div class="rc-body">
      <EchartsHost :option="option" />
    </div>
  </div>
</template>
