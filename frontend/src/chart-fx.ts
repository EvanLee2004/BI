/**
 * 任务书54.1 · 图表动效 / 清晰度共享（纯 ECharts 原生，禁新库）。
 * - V4：入场 + 持续发光/呼吸（effectScatter / shadowBlur / hover 光晕）
 * - V6：字号≥11、对比色、数字标签防糊
 * - prefers-reduced-motion 时关闭动效
 */

import { themeInkColor, currentThemeMode } from './echarts-theme'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 入场动画时长；reduced-motion → 0 */
export function animDuration(ms = 700): number {
  return prefersReducedMotion() ? 0 : ms
}

export function animBlock(ms = 700): Record<string, unknown> {
  if (prefersReducedMotion()) {
    return { animation: false, animationDuration: 0, animationDurationUpdate: 0 }
  }
  return {
    animation: true,
    animationDuration: ms,
    animationDurationUpdate: Math.min(400, ms),
    animationEasing: 'cubicOut',
  }
}

/** V6：图内正文/轴/图例统一清晰色（canvas 必须 hex） */
export function chartTextColor(): string {
  return themeInkColor()
}

export function chartMutedColor(): string {
  const light = currentThemeMode() === 'light'
  return light ? '#3d4a5c' : '#c5d0e8'
}

/** 数字标签：字号≥11 + 细描边防糊 */
export function dataLabelStyle(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const ink = chartTextColor()
  const light = currentThemeMode() === 'light'
  return {
    show: true,
    fontSize: 11,
    fontWeight: 600,
    color: ink,
    textBorderColor: light ? 'rgba(255,255,255,0.92)' : 'rgba(4,8,20,0.85)',
    textBorderWidth: 2,
    textShadowColor: light ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.55)',
    textShadowBlur: 3,
    ...extra,
  }
}

export function axisLabelStyle(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    color: chartMutedColor(),
    fontSize: 11,
    fontWeight: 500,
    ...extra,
  }
}

export function legendTextStyle(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    color: chartTextColor(),
    fontSize: 12,
    fontWeight: 500,
    ...extra,
  }
}

/** 柱体：顶部高光渐变 + 外发光 */
export function barGlowStyle(hex: string, soft = false): Record<string, unknown> {
  const c = hex
  return {
    borderRadius: [4, 4, 0, 0],
    color: {
      type: 'linear',
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: c },
        { offset: 0.45, color: c },
        { offset: 1, color: soft ? c : shadeHex(c, -0.28) },
      ],
    },
    shadowBlur: prefersReducedMotion() ? 0 : 14,
    shadowColor: withAlpha(c, 0.45),
    shadowOffsetY: prefersReducedMotion() ? 0 : 2,
  }
}

/** 折线发光 */
export function lineGlowStyle(hex: string, width = 2.5): Record<string, unknown> {
  return {
    width,
    color: hex,
    shadowBlur: prefersReducedMotion() ? 0 : 12,
    shadowColor: withAlpha(hex, 0.55),
  }
}

export function pointGlowStyle(hex: string): Record<string, unknown> {
  return {
    color: hex,
    borderColor: '#fff',
    borderWidth: 1,
    shadowBlur: prefersReducedMotion() ? 0 : 14,
    shadowColor: withAlpha(hex, 0.7),
  }
}

/**
 * 折线点呼吸：同坐标 effectScatter（showEffectOn:render 持续涟漪）。
 * data 与主 series 同序；reduced-motion 时返回 null，调用方勿 push。
 */
export function breathScatterSeries(
  name: string,
  data: number[],
  hex: string,
  yAxisIndex = 0,
): Record<string, unknown> | null {
  if (prefersReducedMotion()) return null
  return {
    name: `${name}·glow`,
    type: 'effectScatter',
    yAxisIndex,
    data,
    symbolSize: 7,
    showEffectOn: 'render',
    rippleEffect: {
      brushType: 'stroke',
      scale: 2.8,
      period: 2.8,
      color: hex,
    },
    itemStyle: {
      color: hex,
      shadowBlur: 10,
      shadowColor: withAlpha(hex, 0.8),
    },
    z: 6,
    tooltip: { show: false },
    silent: true,
    legendHoverLink: false,
    animation: true,
  }
}

/** 环形 hover：放大 + 外圈光晕 */
export function pieEmphasis(): Record<string, unknown> {
  return {
    scale: true,
    scaleSize: 10,
    itemStyle: {
      shadowBlur: prefersReducedMotion() ? 8 : 22,
      shadowColor: 'rgba(34, 211, 238, 0.55)',
    },
    label: {
      fontSize: 13,
      fontWeight: 700,
    },
  }
}

/** 高对比系列色板（费用多折线等） */
export const SERIES_PALETTE = [
  '#22d3ee',
  '#c084fc',
  '#fbbf24',
  '#34d399',
  '#fb7185',
  '#60a5fa',
  '#f472b6',
  '#2dd4bf',
  '#a78bfa',
  '#f59e0b',
]

function withAlpha(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r},${g},${b},${a})`
}

/** amount in [-1,1] darken/lighten hex */
function shadeHex(hex: string, amount: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const n = parseInt(m[1], 16)
  let r = (n >> 16) & 255
  let g = (n >> 8) & 255
  let b = n & 255
  const adj = (c: number) => {
    if (amount < 0) return Math.max(0, Math.round(c * (1 + amount)))
    return Math.min(255, Math.round(c + (255 - c) * amount))
  }
  r = adj(r)
  g = adj(g)
  b = adj(b)
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
}
