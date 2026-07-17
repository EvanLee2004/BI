<script setup lang="ts">
/** 回款柱线：序列与轴标签来自 VM；任务书51·B7：轴刻度精确查表。
 *  54.1 补刀：年视图 X 轴 1~12 月铺满；Y 轴盖住峰值防折线出画。
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
  breathScatterSeries,
  dataLabelStyle,
  legendTextStyle,
  lineGlowStyle,
  pointGlowStyle,
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
  /* 无数月 → null（不画柱/断折线）；有数月保留 0 */
  const recPlot = recs.map((v, i) => (rd[i] === '' && od[i] === '' ? null : v))
  const ordPlot = ords.map((v, i) => (rd[i] === '' && od[i] === '' ? null : v))
  const ticks = r.value.y_axis_ticks || []
  const maxV0 = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
  const maxV = axisMaxCover(
    maxV0,
    interval,
    [...recs, ...ords].filter((x) => x != null) as number[],
  )
  const cRec = '#22d3ee'
  const cOrd = '#c084fc'
  const series: Record<string, unknown>[] = [
    {
      name: '回款',
      type: 'bar',
      data: recPlot,
      itemStyle: barGlowStyle(cRec),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
      }),
      emphasis: {
        itemStyle: { shadowBlur: 18, shadowColor: 'rgba(34,211,238,0.6)' },
      },
    },
    {
      name: '下单',
      type: 'line',
      data: ordPlot,
      symbol: 'circle',
      symbolSize: 8,
      showSymbol: true,
      connectNulls: false,
      itemStyle: pointGlowStyle(cOrd),
      lineStyle: lineGlowStyle(cOrd, 2.5),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
      }),
    },
  ]
  const breathData = ordPlot.map((x) => (x == null ? 0 : x))
  const breath = breathScatterSeries('下单', breathData, cOrd, 0)
  if (breath) {
    breath.data = ordPlot.map((x) => (x == null ? '-' : x))
    series.push(breath)
  }
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: { dataIndex: number }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (!rd[i] && !od[i]) return `${labels[i] || ''} · 暂无数据`
        return `${labels[i] || ''}<br/>回款 ${rd[i] || '—'}万<br/>下单 ${od[i] || '—'}万`
      },
    },
    legend: { data: ['回款', '下单'], textStyle: legendTextStyle() },
    grid: { left: 64, right: 28, top: 52, bottom: 36 },
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
          /* 非 VM 刻度不裸印大数（防 10000000 脏轴） */
          return ''
        },
        ...axisLabelStyle(),
      },
    },
    series,
    ...animBlock(animDuration(700)),
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
</script>
<template>
  <SciFiPanel id="receiptsCard" title="回款情况" panel-class="rc-card">
    <div v-if="hasSeries" class="rc-body" data-chart="receipts" style="min-height: 360px; height: 380px">
      <EchartsHost :option="option" />
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </SciFiPanel>
</template>
