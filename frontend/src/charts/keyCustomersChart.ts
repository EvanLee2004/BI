/**
 * 重点客户连续月折线 option 纯函数（3.5.0）
 * 默认金额共同轴 value_wan；节奏指数可选。禁止默认 0–100 隐藏轴伪装金额。
 */
import {
  animBlock,
  areaGradient,
  axisLabelStyle,
  chartMutedColor,
  chartTextColor,
  lineGlowStyle,
  pointGlowStyle,
} from '../chart-fx'
import { cssColor } from '../utils/cssColor'
import type { KeyCustomersItem } from '../types/vm'
import { resolveAmountAxisMax } from './keyCustomersAxis'

export type ChartMode = 'amount' | 'rhythm'

export type KcMonthPoint = {
  i?: number
  name?: string
  order_disp?: string
  value_disp?: string
  value_wan?: number | null
  value_fen?: number | null
  status?: string
  rhythm_index?: number | null
  wo?: number | null
}

export type AmountAxis = {
  unit?: string
  name?: string
  min?: number
  max?: number
  interval?: number
  ticks?: { value: number; label: string }[]
}

export type BuildKcChartInput = {
  seriesItems: KeyCustomersItem[]
  monthlyFor: (it: KeyCustomersItem) => KcMonthPoint[]
  mode: ChartMode
  amountAxis?: AmountAxis | null
  highlightMonth?: number
  amountTitle?: string
  rhythmTitle?: string
  rhythmDisclaimer?: string
  yAxisNameAmount?: string
}

/** 最多 5 客：颜色 + 线型 + symbol 组合保证唯一（token 驱动，三主题可读） */
export const COMPARE_SERIES_STYLES: {
  color: string
  lineType: 'solid' | 'dashed' | 'dotted'
  symbol: 'circle' | 'rect' | 'triangle' | 'diamond' | 'roundRect'
}[] = [
  { color: 'var(--blue)', lineType: 'solid', symbol: 'circle' },
  { color: 'var(--purple)', lineType: 'dashed', symbol: 'diamond' },
  { color: 'var(--orange)', lineType: 'dotted', symbol: 'triangle' },
  { color: 'var(--pos)', lineType: 'solid', symbol: 'rect' },
  { color: 'var(--teal)', lineType: 'dashed', symbol: 'roundRect' },
]

/** @deprecated 兼容旧引用；请用 COMPARE_SERIES_STYLES */
const COMPARE_LINE_COLORS = COMPARE_SERIES_STYLES.map((s) => s.color)

function labelIndexes(plot: (number | null)[]): Set<number> {
  /** 峰值 + 最新非空；单系列数据少时标全部非零 */
  const out = new Set<number>()
  let peakI = -1
  let peakV = -Infinity
  let lastI = -1
  let nonNull = 0
  for (let i = 0; i < plot.length; i++) {
    const v = plot[i]
    if (v == null || Number.isNaN(Number(v))) continue
    nonNull++
    if (Number(v) > peakV) {
      peakV = Number(v)
      peakI = i
    }
    if (Number(v) !== 0) lastI = i
    else if (lastI < 0) lastI = i
  }
  if (peakI >= 0) out.add(peakI)
  if (lastI >= 0) out.add(lastI)
  if (nonNull > 0 && nonNull <= 4) {
    for (let i = 0; i < plot.length; i++) {
      const v = plot[i]
      if (v != null && Number(v) !== 0) out.add(i)
    }
  }
  return out
}

export function buildKeyCustomersTrackOption(input: BuildKcChartInput) {
  const {
    seriesItems,
    monthlyFor,
    mode,
    amountAxis,
    highlightMonth = 0,
    yAxisNameAmount = '月下单金额（万）',
  } = input
  const labels = Array.from({ length: 12 }, (_, i) => `${i + 1}月`)
  const ink = chartTextColor()
  const mut = chartMutedColor()
  const hm = highlightMonth
  const soft = cssColor('--blue-soft-14')
  const markArea =
    hm >= 1 && hm <= 12 && soft
      ? {
          silent: true,
          itemStyle: { color: soft },
          data: [[{ xAxis: `${hm}月` }, { xAxis: `${hm}月` }]],
        }
      : undefined

  let localMax = 0
  const series = seriesItems.map((it, si) => {
    const rows = monthlyFor(it)
    const byI = new Map<number, KcMonthPoint>()
    for (const r of rows) {
      const m = Number(r.i) || 0
      if (m >= 1 && m <= 12) byI.set(m, r)
    }
    const plot: (number | null)[] = []
    const disps: string[] = []
    const statuses: string[] = []
    for (let m = 1; m <= 12; m++) {
      const row = byI.get(m)
      if (!row) {
        plot.push(null)
        disps.push('—')
        statuses.push('missing')
        continue
      }
      const st = String(row.status || 'actual')
      statuses.push(st)
      if (mode === 'amount') {
        // VM 单源：只认 value_wan；禁止浏览器 value_fen/1e6 换算兜底
        if (st === 'missing' || row.value_wan == null) {
          plot.push(null)
          disps.push(String(row.value_disp || row.order_disp || '—'))
          continue
        }
        const v = Number(row.value_wan)
        const num = Number.isFinite(v) ? v : null
        plot.push(num)
        if (num != null && num > localMax) localMax = num
        disps.push(String(row.value_disp || row.order_disp || '—'))
      } else {
        const r =
          row.rhythm_index != null
            ? Number(row.rhythm_index)
            : row.wo != null
              ? Number(row.wo)
              : st === 'missing'
                ? null
                : 0
        plot.push(r)
        disps.push(
          r == null ? '—' : `${r}${st === 'incomplete' ? '（未完结）' : ''}`,
        )
      }
    }
    const labelIdx = labelIndexes(plot)
    const style =
      COMPARE_SERIES_STYLES[si % COMPARE_SERIES_STYLES.length] ||
      COMPARE_SERIES_STYLES[0]
    const token = style.color
    const lineC =
      cssColor(token.replace('var(', '').replace(')', '')) || cssColor('--blue')
    const area = si === 0 && mode === 'amount' ? areaGradient(lineC) : undefined
    return {
      name: it.name || `客户${si + 1}`,
      type: 'line' as const,
      data: plot,
      disps,
      statuses,
      smooth: 0.2,
      symbol: style.symbol,
      symbolSize: (_v: number | null, params: { dataIndex: number }) =>
        params.dataIndex + 1 === hm ? 12 : 7,
      connectNulls: false,
      itemStyle: pointGlowStyle(lineC),
      lineStyle: {
        ...lineGlowStyle(lineC, si === 0 ? 2.8 : 2.2),
        type: style.lineType,
      },
      label: {
        show: true,
        formatter: (p: { dataIndex: number; value: number | null }) => {
          if (!labelIdx.has(p.dataIndex)) return ''
          if (p.value == null) return ''
          if (mode === 'amount') {
            const d = disps[p.dataIndex]
            return d && d !== '—' ? d : String(p.value)
          }
          return String(p.value)
        },
        fontSize: 11,
        color: ink,
      },
      labelLayout: { hideOverlap: true, moveOverlap: 'shiftY' },
      ...(area ? { areaStyle: area } : {}),
      ...(si === 0 && markArea ? { markArea } : {}),
    }
  })

  // 3.6.0 G4：金额轴 max 仅来自当前选中 seriesItems 的 localMax（共同零轴）；
  // 禁止用全局 amount_axis.max（全客户）把小客压扁。
  const axisMax =
    mode === 'rhythm'
      ? 100
      : resolveAmountAxisMax(localMax, amountAxis?.max)

  const yAxis =
    mode === 'rhythm'
      ? {
          type: 'value' as const,
          min: 0,
          max: 100,
          name: '节奏指数',
          nameTextStyle: { color: mut, fontSize: 12 },
          show: true,
          splitLine: { show: true, lineStyle: { opacity: 0.15 } },
          axisLabel: { color: mut, fontSize: 11 },
        }
      : {
          type: 'value' as const,
          min: 0,
          max: axisMax > 0 ? axisMax : undefined,
          name: amountAxis?.name || yAxisNameAmount || '月下单金额（万）',
          nameTextStyle: { color: mut, fontSize: 12 },
          show: true,
          splitLine: { show: true, lineStyle: { opacity: 0.15 } },
          axisLabel: {
            color: mut,
            fontSize: 11,
            formatter: (v: number) => {
              const ticks = amountAxis?.ticks || []
              const hit = ticks.find((t) => Math.abs(Number(t.value) - v) < 1e-6)
              if (hit?.label) return hit.label
              if (v === 0) return '0'
              return `${v}`
            },
          },
        }

  return {
    ...animBlock(),
    tooltip: {
      trigger: 'axis' as const,
      confine: true,
      formatter: (params: { seriesName: string; dataIndex: number; seriesIndex: number }[]) => {
        if (!params?.length) return ''
        const i = params[0].dataIndex ?? 0
        const tag = i + 1 === hm ? '（当月未完结/高亮）' : ''
        const lines = [`${labels[i] || ''}${tag}`]
        for (const p of params) {
          const s = series[p.seriesIndex] as {
            disps?: string[]
            statuses?: string[]
          }
          const disp = s?.disps?.[i] || '—'
          const st = s?.statuses?.[i]
          const stLab =
            st === 'missing' ? '缺失' : st === 'incomplete' ? '未完结' : ''
          lines.push(
            `${p.seriesName}：${disp}${stLab ? ` · ${stLab}` : ''}`,
          )
        }
        return lines.join('<br/>')
      },
    },
    legend: {
      show: series.length > 1,
      top: 0,
      textStyle: { color: ink, fontSize: 12 },
    },
    grid: {
      left: 52,
      right: 16,
      top: series.length > 1 ? 44 : 34,
      bottom: 30,
      containLabel: true,
    },
    xAxis: {
      type: 'category' as const,
      data: labels,
      axisLabel: axisLabelStyle({ fontSize: 12, interval: 0, hideOverlap: true }),
      axisLine: { lineStyle: { color: mut } },
    },
    yAxis,
    series,
  }
}

export function buildTrackTitle(opts: {
  seriesItems: { name?: string }[]
  yearLabel?: string
  mode: ChartMode
  amountTitle?: string
  rhythmTitle?: string
  compareCount?: number
}): string {
  const y = opts.yearLabel || ''
  if (opts.mode === 'rhythm') {
    const base = opts.rhythmTitle || '连续月下单节奏指数（自身峰值=100）'
    if (!opts.seriesItems.length) return base
    if (opts.seriesItems.length === 1)
      return `${opts.seriesItems[0].name} · ${y}节奏`
    return `${opts.seriesItems.length} 客节奏比较 · ${y}`
  }
  const base = opts.amountTitle || '连续月下单金额（万）'
  if (!opts.seriesItems.length) return base
  if (opts.seriesItems.length === 1)
    return `${opts.seriesItems[0].name} · ${y}各月下单金额`
  return `${opts.seriesItems.length} 客金额比较 · ${y}`
}
