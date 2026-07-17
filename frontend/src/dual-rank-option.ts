/**
 * 下单/回款双条排名 option 工厂（默认榜与按时间段查询共用，保证样子/顺序一致）。
 * 铁律2：wo/wr/显示串均来自后端；前端只摆图。
 */
import {
  animBlock,
  animDuration,
  axisLabelStyle,
  dataLabelStyle,
  legendTextStyle,
} from './chart-fx'
import type { RankItem } from './types/vm'

export type DualRankBlkLike = {
  items?: RankItem[] | null
  empty?: boolean
  title?: string
  dim?: string
}

export function dualRankBarOption(blk: DualRankBlkLike | null | undefined): Record<string, unknown> {
  const items = [...(blk?.items || [])].reverse() // 横向条图顶=第1名
  const names = items.map((it) => it.name)
  const orders = items.map((it) => Number(it.wo) || 0)
  const receipts = items.map((it) => Number(it.wr) || 0)
  const od = items.map((it) => it.order_disp || '')
  const rd = items.map((it) => it.receipt_disp || '')
  const cO = '#a78bfa'
  const cR = '#2dd4bf'
  const n = Math.max(items.length, 1)
  /* 行高随条数放大：默认≥10 行时每行约 40px，最少 420 */
  const chartH = Math.max(420, n * 44 + 56)
  /* V6：行名不截断——按最长名估左栏，禁止 overflow:truncate */
  const maxChars = names.reduce((m, s) => Math.max(m, String(s || '').length), 4)
  const nameColW = Math.min(200, Math.max(112, maxChars * 13 + 8))
  const leftPad = nameColW + 16
  return {
    _chartH: chartH,
    _nameColW: nameColW,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number; seriesName: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const it = items[i]
        return `${it?.name || ''}<br/>下单 ${od[i]}<br/>回款 ${rd[i]}`
      },
    },
    legend: {
      data: ['下单', '回款'],
      textStyle: legendTextStyle(),
      top: 0,
    },
    grid: { left: leftPad, right: 80, top: 36, bottom: 12, containLabel: false },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { formatter: '{value}%', ...axisLabelStyle() },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        width: nameColW,
        /* 不截断：过长则折行，禁止 truncate/ellipsis */
        overflow: 'break',
        interval: 0,
        hideOverlap: false,
        ...axisLabelStyle({ fontSize: 12, lineHeight: 16 }),
      },
      triggerEvent: true,
    },
    series: [
      {
        name: '下单',
        type: 'bar',
        data: orders,
        barMaxWidth: 14,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: cO },
              { offset: 1, color: '#c4b5fd' },
            ],
          },
          borderRadius: [0, 4, 4, 0],
          shadowBlur: 10,
          shadowColor: 'rgba(167,139,250,0.45)',
        },
        label: dataLabelStyle({
          position: 'right',
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: 11,
        }),
        emphasis: {
          itemStyle: { shadowBlur: 18, shadowColor: 'rgba(167,139,250,0.7)' },
        },
      },
      {
        name: '回款',
        type: 'bar',
        data: receipts,
        barMaxWidth: 14,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: cR },
              { offset: 1, color: '#5eead4' },
            ],
          },
          borderRadius: [0, 4, 4, 0],
          shadowBlur: 10,
          shadowColor: 'rgba(45,212,191,0.45)',
        },
        label: dataLabelStyle({
          position: 'right',
          formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
          fontSize: 11,
        }),
        emphasis: {
          itemStyle: { shadowBlur: 18, shadowColor: 'rgba(45,212,191,0.7)' },
        },
      },
    ],
    ...animBlock(animDuration(600)),
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
