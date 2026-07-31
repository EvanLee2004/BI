/**
 * 重点客户双饼 option 纯函数（3.6.2）
 * 数值仅用 VM 已给的 count / wo；标签用 count_disp / amount_disp / pct_disp，前端不做金额运算。
 */
import { animBlock, chartMutedColor, chartTextColor, dataLabelStyle } from '../chart-fx'
import { cssColor } from '../utils/cssColor'
import type { KeyCustomersSeg } from '../types/vm'

export type StructurePieKind = 'count' | 'amount'

/** S～E 分色（与 KeyCustomersPanel.css 条/点同源 token） */
export const KC_TIER_COLOR_VARS = [
  'var(--blue)',
  'var(--purple)',
  'var(--orange)',
  'var(--pos)',
  'var(--neg)',
  'var(--teal)',
] as const

export function tierColorAt(index: number): string {
  const token = KC_TIER_COLOR_VARS[index % KC_TIER_COLOR_VARS.length]
  // cssColor 要 --name；pie 也接受已解析 hex
  const m = /^var\((--[^)]+)\)$/.exec(token)
  return m ? cssColor(m[1]) : token
}

export type BuildStructurePieInput = {
  kind: StructurePieKind
  label?: string
  segments?: KeyCustomersSeg[] | null
  /** 当前高亮档 id（图例/强调） */
  activeTier?: string | null
}

/**
 * 饼扇区数值：count 饼用户数；amount 饼用布局占比 wo（已由后端按金额算好）。
 * 禁止前端用 amount_disp 反解。
 */
export function segmentPieValue(kind: StructurePieKind, seg: KeyCustomersSeg): number {
  if (kind === 'count') {
    const c = Number(seg.count)
    if (Number.isFinite(c) && c >= 0) return c
  }
  const wo = Number(seg.wo)
  if (Number.isFinite(wo) && wo > 0) return wo
  // 兜底：count 非数时仍可用 wo
  const c = Number(seg.count)
  return Number.isFinite(c) && c > 0 ? c : 0
}

export function structureHasData(segments?: KeyCustomersSeg[] | null): boolean {
  if (!segments || !segments.length) return false
  return segments.some((s) => segmentPieValue('count', s) > 0 || Number(s.wo) > 0)
}

export function buildKeyCustomersStructurePieOption(input: BuildStructurePieInput) {
  const segs = input.segments || []
  const kind = input.kind
  const ink = chartTextColor()
  const mut = chartMutedColor()
  const active = (input.activeTier || '').trim().toUpperCase()

  const data = segs.map((seg, i) => {
    const id = String(seg.id || seg.label || '').trim()
    const value = segmentPieValue(kind, seg)
    const valueDisp =
      kind === 'count' ? seg.count_disp || String(seg.count ?? '') : seg.amount_disp || ''
    const pct = seg.pct_disp || ''
    const color = tierColorAt(i)
    const isActive = active && id.toUpperCase() === active
    return {
      name: id || seg.label || `t${i}`,
      value,
      tierId: id,
      valueDisp,
      pctDisp: pct,
      itemStyle: {
        color,
        opacity: active && !isActive ? 0.55 : 1,
        borderColor: isActive ? ink : cssColor('--chart-label-stroke-dark'),
        borderWidth: isActive ? 2 : 1,
      },
    }
  })

  const totalLabel = input.label || (kind === 'count' ? '客户数结构' : '金额结构')

  return {
    ...animBlock(0),
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p: {
        data?: { name?: string; valueDisp?: string; pctDisp?: string }
        name?: string
      }) => {
        const d = p.data || {}
        const name = d.name || p.name || ''
        const vd = d.valueDisp || '—'
        const pd = d.pctDisp || '—'
        return `${name}<br/>${vd}（${pd}）`
      },
    },
    series: [
      {
        type: 'pie',
        name: totalLabel,
        radius: ['38%', '68%'],
        center: ['50%', '52%'],
        avoidLabelOverlap: true,
        data,
        label: {
          ...dataLabelStyle({
            fontSize: 11,
            formatter: (p: {
              data?: { name?: string; valueDisp?: string; pctDisp?: string; value?: number }
            }) => {
              const d = p.data || {}
              const v = Number(d.value) || 0
              if (v <= 0) return ''
              const name = d.name || ''
              const vd = d.valueDisp || ''
              // 短标签：档 + 显示串（已含户/万）
              return vd ? `${name}\n${vd}` : name
            },
          }),
        },
        labelLine: {
          show: true,
          length: 8,
          length2: 6,
          lineStyle: { color: mut },
        },
        emphasis: {
          scale: true,
          scaleSize: 4,
          itemStyle: { shadowBlur: 0 },
        },
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: totalLabel,
          textAlign: 'center',
          fill: mut,
          fontSize: 11,
          fontWeight: 600,
        },
      },
    ],
  }
}
