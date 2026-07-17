<script setup lang="ts">
/** 收入·毛利趋势：轴标签/数据标签后端下发；无技术字样。任务书51·B7：轴刻度精确查表。 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import { themeInkColor } from '../echarts-theme'
import type { AxisTick, TrendVM } from '../types/vm'

const store = useCockpitStore()
const trend = computed((): Partial<TrendVM> => store.vm?.trend || {})

/** 后端 ticks 精确匹配（禁最近刻度扫描）。 */
function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return String(t.label ?? '')
  }
  return ''
}

const option = computed(() => {
  const t = trend.value
  const labels = (t.labels || []).map((x) => String(x))
  const rev = (t.revenue || []).map((x) => Number(x) || 0)
  const cost = (t.cost || []).map((x) => Number(x) || 0)
  const margin = (t.margin_pct || []).map((x) => Number(x) || 0)
  const revD = (t.revenue_disp || []).map((x) => String(x ?? ''))
  const costD = (t.cost_disp || []).map((x) => String(x ?? ''))
  const marD = (t.margin_pct_disp || []).map((x) => String(x ?? ''))
  const ticks = t.y_axis_ticks || []
  const maxV = t.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    t.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = t.y_axis_min ?? 0
  const ink = themeInkColor()
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        return `${labels[i] || ''}<br/>收入 ${revD[i] || '—'}万<br/>成本 ${costD[i] || '—'}万<br/>毛利率 ${marD[i] || '—'}`
      },
    },
    legend: { data: ['收入', '成本', '毛利率'], textStyle: { color: ink } },
    grid: { left: 64, right: 48, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: labels },
    yAxis: [
      {
        type: 'value',
        min: minV,
        max: maxV,
        interval,
        axisLabel: {
          formatter: (val: number) => tickLabel(ticks, val),
          color: ink,
        },
      },
      {
        type: 'value',
        max: 100,
        axisLabel: { formatter: '{value}%', color: ink },
      },
    ],
    series: [
      {
        name: '收入',
        type: 'bar',
        data: rev,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#22d3ee' },
        label: {
          show: true,
          position: 'top',
          formatter: (p: { dataIndex: number }) => revD[p.dataIndex] || '',
          fontSize: 10,
          color: ink,
        },
      },
      {
        name: '成本',
        type: 'bar',
        data: cost,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#64769e' },
        label: {
          show: true,
          position: 'top',
          formatter: (p: { dataIndex: number }) => costD[p.dataIndex] || '',
          fontSize: 10,
          color: ink,
        },
      },
      {
        name: '毛利率',
        type: 'line',
        yAxisIndex: 1,
        data: margin,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#c084fc' },
        lineStyle: { width: 2, color: '#c084fc' },
        label: {
          show: true,
          formatter: (p: { dataIndex: number }) => marD[p.dataIndex] || '',
          fontSize: 10,
          color: ink,
        },
      },
    ],
    animationDuration: 700,
  }
})
</script>
<template>
  <SciFiPanel id="trendChartCard" title="收入 · 毛利趋势" panel-class="trend-chart-card">
    <div class="rc-body" data-chart="trend">
      <EchartsHost :option="option" />
    </div>
  </SciFiPanel>
</template>
