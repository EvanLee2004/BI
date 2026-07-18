/**
 * 任务书54.4 · 图表性能/清晰度共享（纯 ECharts 原生，禁新库）。
 * - 默认零持续动画（ECharts 复杂场景官方建议 animation:false）
 * - 删除 breath/effectScatter 常驻特效（showEffectOn render 开销大）
 * - shadowBlur 默认 0，hover 才略加
 * - prefers-reduced-motion 彻底静止
 */

import { themeInkColor, currentThemeMode } from './echarts-theme'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** @deprecated 54.4 默认零动画；保留签名以免旧调用炸 */
export function animDuration(_ms = 700): number {
  return 0
}

/** 默认关闭入场/更新动画（PERF A1） */
export function animBlock(_ms = 700): Record<string, unknown> {
  return {
    animation: false,
    animationDuration: 0,
    animationDurationUpdate: 0,
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
    fontSize: 12,
    fontWeight: 600,
    color: ink,
    textBorderColor: light ? 'rgba(255,255,255,0.92)' : 'rgba(4,8,20,0.85)',
    textBorderWidth: 2,
    textShadowColor: light ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.55)',
    textShadowBlur: 0,
    ...extra,
  }
}

export function axisLabelStyle(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    color: chartMutedColor(),
    fontSize: 12,
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

/** 柱体：顶部高光渐变；默认无软阴影（PERF A3） */
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
    shadowBlur: 0,
    shadowColor: 'transparent',
    shadowOffsetY: 0,
  }
}

/** 折线：无常驻发光 */
export function lineGlowStyle(hex: string, width = 2.5): Record<string, unknown> {
  return {
    width,
    color: hex,
    shadowBlur: 0,
    shadowColor: 'transparent',
  }
}

export function pointGlowStyle(hex: string): Record<string, unknown> {
  return {
    color: hex,
    borderColor: '#fff',
    borderWidth: 1,
    shadowBlur: 0,
    shadowColor: 'transparent',
  }
}

/**
 * @deprecated 54.4 已删呼吸系列；保留函数恒返回 null，调用方 if 守卫可保留。
 */
export function breathScatterSeries(
  _name: string,
  _data: number[],
  _hex: string,
  _yAxisIndex = 0,
): Record<string, unknown> | null {
  return null
}

/** 环形 hover：略放大；阴影 ≤4 */
export function pieEmphasis(): Record<string, unknown> {
  return {
    scale: true,
    scaleSize: 8,
    itemStyle: {
      shadowBlur: 4,
      shadowColor: 'rgba(34, 211, 238, 0.35)',
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

