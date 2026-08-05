/**
 * 下单/回款双条排名 option 工厂（默认榜与按时间段查询共用，保证样子/顺序一致）。
 * 铁律2：wo/wr/显示串均来自后端；前端只摆图。
 */
import {
  animBlock,
  axisLabelStyle,
  dataLabelStyle,
  legendTextStyle,
} from './chart-fx'
import type { RankItem } from './types/vm'
import { cssColor } from './utils/cssColor'

export type DualRankBlkLike = {
  items?: RankItem[] | null
  empty?: boolean
  title?: string
  dim?: string
}

export type DualRankOptionOpts = {
  /** 2.6.2：≤520 时压缩左栏+省略长名，桌面默认 false 保持原 V6 折行不截断 */
  narrow?: boolean
}

export function dualRankBarOption(
  blk: DualRankBlkLike | null | undefined,
  opts?: DualRankOptionOpts,
): Record<string, unknown> {
  const narrow = !!opts?.narrow
  const items = [...(blk?.items || [])].reverse() // 横向条图顶=第1名
  const names = items.map((it) => it.name)
  const orders = items.map((it) => Number(it.wo) || 0)
  const receipts = items.map((it) => Number(it.wr) || 0)
  const od = items.map((it) => it.order_disp || '')
  const rd = items.map((it) => it.receipt_disp || '')
  // FE-002：双条色走 token（cssColor），禁硬编码 hex
  const cO = cssColor('--rank-primary-alt')
  const cR = cssColor('--rank-secondary')
  const cOEnd = cssColor('--rank-primary-soft-end')
  const cREnd = cssColor('--rank-secondary-soft-end')
  const cOGlow = cssColor('--rank-primary-glow')
  const cRGlow = cssColor('--rank-secondary-glow')
  const n = Math.max(items.length, 1)
  /* 行高随条数放大：默认≥10 行时每行约 40px，最少 420 */
  const chartH = Math.max(narrow ? 360 : 420, n * (narrow ? 40 : 44) + 56)
  const maxChars = names.reduce((m, s) => Math.max(m, String(s || '').length), 4)
  /* 桌面：不截断折行；窄屏：限宽 + ellipsis 防撑破 */
  const nameColW = narrow
    ? Math.min(96, Math.max(64, Math.min(maxChars, 8) * 12 + 4))
    : Math.min(200, Math.max(112, maxChars * 13 + 8))
  const leftPad = nameColW + (narrow ? 8 : 16)
  const labelFs = narrow ? 10 : 12
  return {
    _chartH: chartH,
    _nameColW: nameColW,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      confine: true,
      formatter: (params: { dataIndex: number; seriesName: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const it = items[i]
        return `${it?.name || ''}<br/>下单 ${od[i]}<br/>回款 ${rd[i]}`
      },
    },
    legend: {
      data: ['下单', '回款'],
      textStyle: legendTextStyle(narrow ? { fontSize: 11 } : {}),
      top: 0,
    },
    grid: {
      left: leftPad,
      right: narrow ? 44 : 80,
      top: 36,
      bottom: 12,
      containLabel: false,
    },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%', ...axisLabelStyle(narrow ? { fontSize: 10 } : {}) },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        width: nameColW,
        overflow: narrow ? 'truncate' : 'break',
        ellipsis: narrow ? '…' : undefined,
        interval: 0,
        hideOverlap: false,
        ...axisLabelStyle({ fontSize: labelFs, lineHeight: narrow ? 14 : 16 }),
      },
      triggerEvent: true,
    },
    series: [
      {
        name: '下单',
        type: 'bar',
        data: orders,
        barMaxWidth: narrow ? 12 : 14,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: cO },
              { offset: 1, color: cOEnd },
            ],
          },
          borderRadius: [0, 4, 4, 0],
          shadowBlur: 0,
          shadowColor: 'transparent',
        },
        label: dataLabelStyle({
          position: 'right',
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: labelFs,
        }),
        emphasis: {
          itemStyle: { shadowBlur: 4, shadowColor: cOGlow },
        },
      },
      {
        name: '回款',
        type: 'bar',
        data: receipts,
        barMaxWidth: narrow ? 12 : 14,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: cR },
              { offset: 1, color: cREnd },
            ],
          },
          borderRadius: [0, 4, 4, 0],
          shadowBlur: 0,
          shadowColor: 'transparent',
        },
        label: dataLabelStyle({
          position: 'right',
          formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
          fontSize: labelFs,
        }),
        emphasis: {
          itemStyle: { shadowBlur: 4, shadowColor: cRGlow },
        },
      },
    ],
    ...animBlock(),
  }
}

/** 点击 dataIndex → 原 items 顺序中的项（与 reverse 对称） */
export function dualRankItemAt(
  blk: DualRankBlkLike | null | undefined,
  dataIndex: number | undefined,
): RankItem | null {
  if (!blk?.items || dataIndex == null) return null
  const items = [...blk.items].reverse()
  return items[dataIndex] || null
}
