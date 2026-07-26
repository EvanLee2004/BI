<script setup lang="ts">

function cssVar(name: string, fallback = ''): string {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}
import '../styles/components/ExpenseHeatmap.css'
/**
 * 54.14 R-26：费用明细区「月份 × 报表大类」热力格子图（ECharts heatmap）。
 * 数据全部来自 VM expense.area_*（后端已聚合）；前端零金额运算，仅映射坐标与显示串。
 * 视觉：深空青→金渐变；浅色适配；375 可横滚。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import { animBlock, axisLabelStyle, chartMutedColor, chartTextColor } from '../chart-fx'
import { withWanUnit } from '../utils/disp'
import { buildExpenseHeatPack } from '../utils/expense-heat'
import { resolveMonthCap } from '../chart-months'
import { themeMode } from '../utils/theme'
import type { ExpenseVM } from '../types/vm'

const store = useCockpitStore()
const exp = computed((): Partial<ExpenseVM> => store.vm?.expense || {})

/** 格子数据：[[xIdx, yIdx, value], ...] + 平行 disp — 同源 utils/expense-heat；C-2 裁未来月 */
const heatPack = computed(() => {
  const cap = resolveMonthCap({
    chartMonthMax: (store.vm as { chart_month_max?: number } | null)?.chart_month_max,
    defaultEnd: store.vm?.daily?.default_end,
  })
  return buildExpenseHeatPack(exp.value.area_labels, exp.value.area_series, cap)
})

const option = computed(() => {
  void themeMode.value
  const { labels, cats, data, dispMap, vmax } = heatPack.value
  const light = themeMode.value === 'light'
  const ink = chartTextColor()
  const mut = chartMutedColor()
  // 青 → 金（深空）；浅色略加深底
  const colors = light
    ? [
        [0, cssVar('--heat-l0')],
        [0.35, cssVar('--heat-l1')],
        [0.65, cssVar('--blue')],
        [1, cssVar('--heat-l3')],
      ]
    : [
        [0, cssVar('--heat-d0')],
        [0.25, cssVar('--heat-d1')],
        [0.55, cssVar('--blue')],
        [0.8, cssVar('--orange')],
        [1, cssVar('--heat-d4')],
      ]
  const maxV = vmax > 0 ? vmax : 1
  return {
    /* R-31：confine 防卡片裁切；顶行留白 + visMap 底边距 */
    tooltip: {
      position: 'top',
      confine: true,
      extraCssText: 'max-width: 240px; z-index: 80;',
      formatter: (p: { value?: number[] }) => {
        const v = p?.value || []
        const xi = Number(v[0])
        const yi = Number(v[1])
        const lab = labels[xi] || ''
        const cat = cats[yi] || ''
        const d = dispMap[`${xi},${yi}`] || '0.0'
        return `${lab} · ${cat}<br/>${withWanUnit(d)}`
      },
    },
    grid: {
      left: 12,
      right: 28,
      top: 28,
      bottom: 56,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: true },
      axisLabel: axisLabelStyle({ interval: 0 }),
    },
    yAxis: {
      type: 'category',
      data: cats,
      splitArea: { show: true },
      axisLabel: { ...axisLabelStyle(), width: 96, overflow: 'truncate' },
    },
    visualMap: {
      min: 0,
      max: maxV,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 12,
      itemHeight: 100,
      textStyle: { color: mut, fontSize: 12 },
      inRange: { color: colors.map((c) => c[1] as string) },
      // 不显示数值（金额单位在 tooltip；避免前端再格式化）
      formatter: () => '',
    },
    series: [
      {
        name: '费用',
        type: 'heatmap',
        data,
        label: {
          show: false,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 6,
            shadowColor: light
              ? cssVar('--line-cyan-35')
              : cssVar('--rank-others-border-hover'),
          },
        },
        itemStyle: {
          borderColor: light
            ? cssVar('--chart-label-stroke-light')
            : cssVar('--chart-label-stroke-dark'),
          borderWidth: 1,
        },
      },
    ],
    textStyle: { color: ink },
    ...animBlock(),
  }
})

const hasData = computed(() => (heatPack.value.data || []).some((d) => d[2] > 0))
</script>

<template>
  <SciFiPanel
    id="expHeatCard"
    title="费用热力 · 月份×报表大类"
    tag="格子深浅=金额 · 悬停显示"
    panel-class="exp-heat-card"
    style="margin-top: 16px"
  >
    <div v-if="hasData" class="exp-heat-scroll" data-testid="expense-heatmap-scroll">
      <div class="exp-heat-fill" data-chart="expense-heatmap" data-testid="expense-heatmap">
        <EchartsHost :option="option" />
      </div>
    </div>
    <div v-else class="ev-empty" data-testid="expense-heatmap-empty">本年无费用热力数据（格子为全年各月，不随顶栏周期切片）</div>
  </SciFiPanel>
</template>

