/**
 * 任务书54.4 · 图表性能/清晰度共享（纯 ECharts 原生，禁新库）。
 * 2.3.0 S3：fxLevel 1 仅霓虹+非 reduced-motion；0 时与 2.2.9 逐字段相同。
 * FE-002：色值一律经 cssColor / seriesPalette，本文件无硬编码 hex/rgba。
 */

import { themeInkColor, currentThemeMode } from './echarts-theme'
import { cssColor, hexWithAlpha, seriesPalette, shadeHex } from './utils/cssColor'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 0 = 无特效（暗色/亮色/reduced-motion）
 * 1 = 霓虹发光与入场动画
 */
export function fxLevel(): 0 | 1 {
  if (prefersReducedMotion()) return 0
  if (currentThemeMode() === 'neon') return 1
  return 0
}

/** 默认关闭入场/更新动画；fx=1 时放行短动画 */
export function animBlock(_ms = 700): Record<string, unknown> {
  if (fxLevel() === 1) {
    return {
      animation: true,
      animationDuration: 600,
      animationDurationUpdate: 300,
      animationEasing: 'cubicOut',
    }
  }
  return {
    animation: false,
    animationDuration: 0,
    animationDurationUpdate: 0,
  }
}

/** V6：图内正文/轴/图例统一清晰色（canvas 必须实色） */
export function chartTextColor(): string {
  return themeInkColor()
}

export function chartMutedColor(): string {
  const mode = currentThemeMode()
  if (mode === 'light') return cssColor('--mut-chart-light')
  if (mode === 'neon') return cssColor('--note-neon')
  return cssColor('--note-dark')
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
    textBorderColor: light
      ? cssColor('--chart-label-stroke-light')
      : cssColor('--chart-label-stroke-dark'),
    textBorderWidth: 2,
    textShadowColor: light
      ? cssColor('--chart-label-shadow-light')
      : cssColor('--chart-label-shadow-dark'),
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

/** 柱体：顶部高光渐变；fx=1 时软阴影 + 顶帽高亮 */
export function barGlowStyle(hex: string, soft = false): Record<string, unknown> {
  const c = hex
  const fx = fxLevel() === 1
  return {
    borderRadius: [4, 4, 0, 0],
    color: {
      type: 'linear',
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: fx
        ? [
            { offset: 0, color: shadeHex(c, 0.35) },
            { offset: 0.08, color: c },
            { offset: 0.5, color: c },
            { offset: 1, color: soft ? c : shadeHex(c, -0.28) },
          ]
        : [
            { offset: 0, color: c },
            { offset: 0.45, color: c },
            { offset: 1, color: soft ? c : shadeHex(c, -0.28) },
          ],
    },
    /* fx=0 时与 2.2.9 一致：shadowBlur: 0 */
    shadowBlur: fx ? 12 : 0,
    shadowColor: fx ? hexWithAlpha(c, 0.5) : 'transparent',
    shadowOffsetY: 0,
    ...(fx
      ? {
          borderColor: shadeHex(c, 0.45),
          borderWidth: 0,
        }
      : {}),
  }
}

/** 折线：fx=1 发光 */
export function lineGlowStyle(hex: string, width = 2.5): Record<string, unknown> {
  const fx = fxLevel() === 1
  return {
    width: fx ? width + 0.5 : width,
    color: hex,
    /* fx=0：shadowBlur: 0 */
    shadowBlur: fx ? 14 : 0,
    shadowColor: fx ? hexWithAlpha(hex, 0.5) : 'transparent',
  }
}

export function pointGlowStyle(hex: string): Record<string, unknown> {
  const fx = fxLevel() === 1
  return {
    color: hex,
    borderColor: cssColor('--white'),
    borderWidth: 1,
    /* fx=0：shadowBlur: 0 */
    shadowBlur: fx ? 10 : 0,
    shadowColor: fx ? hexWithAlpha(hex, 0.55) : 'transparent',
  }
}

/**
 * fx=1：趋势图收入系列 areaStyle 线性渐变；fx=0 返回 undefined。
 */
export function areaGradient(hex: string): Record<string, unknown> | undefined {
  if (fxLevel() !== 1) return undefined
  return {
    color: {
      type: 'linear',
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: hexWithAlpha(hex, 0.35) },
        { offset: 1, color: hexWithAlpha(hex, 0) },
      ],
    },
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

/** 环形 hover：略放大；阴影 ≤4；霓虹加强 */
export function pieEmphasis(): Record<string, unknown> {
  const fx = fxLevel() === 1
  return {
    scale: true,
    scaleSize: fx ? 10 : 8,
    itemStyle: {
      shadowBlur: fx ? 12 : 4,
      shadowColor: fx ? cssColor('--chart-pie-glow-neon') : cssColor('--chart-pie-glow-dark'),
    },
    label: {
      fontSize: 13,
      fontWeight: 700,
    },
  }
}

/** 环形外发光 itemStyle 补丁（仅样式，不碰 data/label） */
export function pieGlowItemStyle(hex: string): Record<string, unknown> {
  if (fxLevel() !== 1) return {}
  return {
    shadowBlur: 14,
    shadowColor: hexWithAlpha(hex, 0.45),
    borderColor: shadeHex(hex, 0.25),
    borderWidth: 1,
  }
}

/** 系列 emphasis focus（三主题免费午餐） */
export function seriesEmphasisFocus(): Record<string, unknown> {
  return { emphasis: { focus: 'series' } }
}

/** tooltip axisPointer 竖线+半透明色带 */
export function axisPointerStyle(): Record<string, unknown> {
  const mode = currentThemeMode()
  const isLight = mode === 'light'
  return {
    type: 'line',
    lineStyle: {
      color: isLight ? cssColor('--chart-axis-ptr-light') : cssColor('--chart-axis-ptr-neon'),
      width: 1,
    },
    crossStyle: {
      color: isLight ? cssColor('--chart-axis-cross-light') : cssColor('--chart-axis-cross-neon'),
    },
  }
}

/** 高对比系列色板（费用多折线等）— 自 token 派生 */
export const SERIES_PALETTE = seriesPalette()

// re-export for callers that need hex helpers without importing cssColor
export { hexWithAlpha, shadeHex }
// 兼容旧名
export { hexWithAlpha as hexToRgba }
