<script setup lang="ts">
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
import { cssColor } from '../utils/cssColor'
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
  const {
    labels,
    cats,
    data,
    dispMap,
    missingMap,
    vmax,
    vmin_disp,
    vmid_disp,
    vmax_disp,
    unit,
    legend_range,
  } = heatPack.value
  const light = themeMode.value === 'light'
  const ink = chartTextColor()
  const mut = chartMutedColor()
  // 青 → 金（深空）；浅色略加深底；缺失用独立底色
  const colors = light
    ? [
        [0, cssColor('--heat-l0')],
        [0.35, cssColor('--heat-l1')],
        [0.65, cssColor('--blue')],
        [1, cssColor('--heat-l3')],
      ]
    : [
        [0, cssColor('--heat-d0')],
        [0.25, cssColor('--heat-d1')],
        [0.55, cssColor('--blue')],
        [0.8, cssColor('--orange')],
        [1, cssColor('--heat-d4')],
      ]
  // visualMap 与格子 value 同尺（库内分）；展示文案只用 *_disp / legend_range
  const maxV = vmax > 0 ? vmax : 1
  const hiLabel = withWanUnit(vmax_disp || '0.0')
  const loLabel = withWanUnit(vmin_disp || '0.0')
  // 缺失哨兵 -1 → 画为 0 但不进 visualMap 主色：映射到 0 并用 itemStyle 区分
  const plotData = data.map(([xi, yi, v]) => {
    const key = `${xi},${yi}`
    if (missingMap[key] || v < 0) {
      return {
        value: [xi, yi, 0],
        itemStyle: {
          color: light ? cssColor('--panel2') : cssColor('--panel2'),
          borderColor: cssColor('--line-soft') || cssColor('--line'),
          borderWidth: 1,
          borderRadius: 4,
          opacity: 0.35,
        },
      }
    }
    return {
      value: [xi, yi, v],
      itemStyle: {
        borderRadius: 4,
        borderWidth: 2,
        borderColor: light
          ? cssColor('--chart-label-stroke-light')
          : cssColor('--chart-label-stroke-dark'),
      },
    }
  })
  // 图例：单位 + 万级范围（data_disp），禁止把分值当万展示
  const rangeHint = `单位 ${unit} · ${legend_range}`
  return {
    /* R-31：confine 防卡片裁切；顶行留白 + visMap 底边距 */
    tooltip: {
      position: 'top',
      confine: true,
      extraCssText: 'max-width: 260px; z-index: 80; white-space: normal;',
      formatter: (p: { value?: number[] | { value?: number[] }; data?: { value?: number[] } }) => {
        const raw = (p as { data?: { value?: number[] }; value?: number[] })?.data?.value
          || (p as { value?: number[] })?.value
          || []
        const xi = Number(raw[0])
        const yi = Number(raw[1])
        const lab = labels[xi] || ''
        const cat = cats[yi] || ''
        const key = `${xi},${yi}`
        if (missingMap[key]) return `${lab} · ${cat}<br/>暂无数据`
        const d = dispMap[key]
        const isZero = Number(raw[2]) === 0 && d !== '—'
        const body = d === '—' || d == null || d === ''
          ? (isZero ? withWanUnit('0') : '—')
          : withWanUnit(d)
        return `${lab} · ${cat}<br/>${body}${isZero && d !== '—' ? '（确认 0）' : ''}`
      },
    },
    grid: {
      left: 12,
      right: 28,
      top: 28,
      bottom: 72,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: false },
      axisLabel: {
        ...axisLabelStyle({ interval: 0 }),
        hideOverlap: false,
        rotate: labels.length > 8 ? 30 : 0,
      },
    },
    yAxis: {
      type: 'category',
      data: cats,
      splitArea: { show: false },
      axisLabel: { ...axisLabelStyle(), width: 100, overflow: 'truncate' },
    },
    visualMap: {
      min: 0,
      max: maxV,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 12,
      itemHeight: 120,
      text: [`高 ${hiLabel}`, `低 ${loLabel}`],
      textStyle: { color: mut, fontSize: 11 },
      inRange: { color: colors.map((c) => c[1] as string) },
      // 着色轴用分值；刻度文案不回显分（避免与「单位 万」矛盾）
      formatter: () => '',
    },
    series: [
      {
        name: '费用',
        type: 'heatmap',
        data: plotData,
        label: {
          show: false,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 8,
            shadowColor: light
              ? cssColor('--line-cyan-35')
              : cssColor('--rank-others-border-hover'),
          },
        },
      },
    ],
    textStyle: { color: ink },
    // 图例范围说明（展示用，数值来自 pack 权威统计）
    graphic: [
      {
        type: 'text',
        left: 'center',
        bottom: 28,
        style: {
          text: rangeHint,
          fill: mut,
          fontSize: 11,
        },
      },
    ],
    ...animBlock(),
  }
})

const hasData = computed(() => (heatPack.value.data || []).some((d) => d[2] > 0))
/** 图例：单位 + data_disp 万级范围（withWanUnit 幂等，不二次运算金额） */
const heatLegend = computed(() => {
  const p = heatPack.value
  const lo = withWanUnit(p.vmin_disp || '0.0')
  const mid = withWanUnit(p.vmid_disp || '0.0')
  const hi = withWanUnit(p.vmax_disp || '0.0')
  return `单位 ${p.unit} · 最小 ${lo} / 中位 ${mid} / 最大 ${hi}`
})
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
      <div class="exp-heat-legend" data-testid="expense-heatmap-legend">{{ heatLegend }}</div>
      <div class="exp-heat-fill" data-chart="expense-heatmap" data-testid="expense-heatmap">
        <EchartsHost :option="option" />
      </div>
    </div>
    <div v-else class="ev-empty" data-testid="expense-heatmap-empty">本年无费用热力数据（格子为全年各月，不随顶栏周期切片）</div>
  </SciFiPanel>
</template>

