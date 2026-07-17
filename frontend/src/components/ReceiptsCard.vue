<script setup lang="ts">
/**
 * 回款情况：54.2 对照基准 = 紫柱下单 + 青柱回款（双柱）+ 年轴 1–12 + Y 轴盖峰值。
 * 显示串全 VM；前端零金额运算。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  animDuration,
  axisLabelStyle,
  barGlowStyle,
  dataLabelStyle,
  legendTextStyle,
} from '../chart-fx'
import { axisMaxCover, padYearMonths } from '../chart-months'
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
  const rawLabels = (r.value.labels || []).map((x) => String(x))
  const rawRecs = (r.value.receipts || []).map((x) => Number(x) || 0)
  const rawOrds = (r.value.orders || []).map((x) => Number(x) || 0)
  const rawRd = (r.value.receipts_disp || []).map((x) => String(x ?? ''))
  const rawOd = (r.value.orders_disp || []).map((x) => String(x ?? ''))
  const padded = padYearMonths(rawLabels, [rawRecs, rawOrds], [rawRd, rawOd])
  const labels = padded.labels
  const recs = padded.series[0]
  const ords = padded.series[1]
  const rd = padded.disps[0]
  const od = padded.disps[1]
  const empty = (i: number) => !rd[i] && !od[i]
  const recPlot = recs.map((v, i) => (empty(i) ? null : v))
  const ordPlot = ords.map((v, i) => (empty(i) ? null : v))
  const ticks = r.value.y_axis_ticks || []
  const maxV0 = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
  const maxV = axisMaxCover(maxV0, interval, [...recs, ...ords])
  const cOrd = '#a78bfa'
  const cRec = '#22d3ee'
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        return `${labels[i] || ''}<br/>下单 ${od[i] || '—'}万<br/>回款 ${rd[i] || '—'}万`
      },
    },
    legend: {
      data: ['下单', '回款'],
      bottom: 0,
      textStyle: legendTextStyle(),
    },
    grid: { left: 64, right: 28, top: 40, bottom: 48 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: axisLabelStyle({ interval: 0 }),
    },
    yAxis: {
      type: 'value',
      min: minV,
      max: maxV,
      interval,
      axisLabel: {
        formatter: (val: number) => {
          const lab = tickLabel(ticks, val)
          if (lab) return lab
          if (val === 0) return '0'
          return ''
        },
        ...axisLabelStyle(),
      },
    },
    series: [
      {
        name: '下单',
        type: 'bar',
        data: ordPlot,
        barMaxWidth: 28,
        itemStyle: barGlowStyle(cOrd),
        label: dataLabelStyle({
          position: 'top',
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: 11,
        }),
      },
      {
        name: '回款',
        type: 'bar',
        data: recPlot,
        barMaxWidth: 28,
        itemStyle: barGlowStyle(cRec),
        label: dataLabelStyle({
          position: 'top',
          formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
          fontSize: 11,
        }),
      },
    ],
    ...animBlock(animDuration(700)),
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
</script>
<template>
  <SciFiPanel id="receiptsCard" title="回款情况" panel-class="rc-card">
    <div v-if="hasSeries" class="rc-body" data-chart="receipts">
      <EchartsHost :option="option" />
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </SciFiPanel>
</template>
