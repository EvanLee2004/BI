<script setup lang="ts">
/** 收入·毛利趋势：轴标签/数据标签后端下发；无技术字样。任务书51·B7：轴刻度精确查表。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import type { AxisTick, TrendVM } from '../types/vm'

const store = useCockpitStore()
const trend = computed((): Partial<TrendVM> => store.vm?.trend || {})

/** 后端 ticks 精确匹配（禁最近刻度扫描）。 */
function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

const option = computed(() => {
  const t = trend.value
  const labels = t.labels || []
  const rev = t.revenue || []
  const cost = t.cost || []
  const margin = t.margin_pct || []
  const revD = t.revenue_disp || []
  const costD = t.cost_disp || []
  const marD = t.margin_pct_disp || []
  const ticks = t.y_axis_ticks || []
  const maxV = t.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    t.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = t.y_axis_min ?? 0
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
        min: minV,
        max: maxV,
        interval,
        axisLabel: { formatter: (val: number) => tickLabel(ticks, val) },
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
