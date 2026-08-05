/**
 * 任务书54·B：ECharts 主题全面从 SciFi kit CSS 变量派生（+ theme.css 业务色）。
 * 任务书54.1：V6 图表文字清晰度（轴/图例字号≥11、对比提高）。
 * FE-002：色值一律经 cssColor（token 回落），本文件无硬编码 hex/rgba。
 */

import { cssColor } from './utils/cssColor'

/** 解析后的正文色（ECharts canvas 不能吃 CSS var()，图内 label 必须用实色）。 */
export function themeInkColor(): string {
  const mode = currentThemeMode()
  const isLight = mode === 'light'
  const isNeon = mode === 'neon'
  return cssColor(
    '--dsdk-text-color',
    cssColor('--ink', isLight ? cssColor('--ink-light') : isNeon ? cssColor('--ink-neon') : cssColor('--ink')),
  )
}

export function kanbanTheme(mode: 'neon' | 'dark' | 'light' = 'dark') {
  const isLight = mode === 'light'
  const isNeon = mode === 'neon'
  const accent = cssColor(
    '--dsdk-accent-color-secondary',
    cssColor('--blue', isLight ? cssColor('--blue-light') : isNeon ? cssColor('--blue-neon') : cssColor('--blue')),
  )
  const purple = cssColor(
    '--dsdk-accent-color-main',
    cssColor(
      '--purple',
      isLight ? cssColor('--purple-light') : isNeon ? cssColor('--purple-neon') : cssColor('--purple'),
    ),
  )
  const teal = cssColor('--teal', isLight ? cssColor('--teal-light') : isNeon ? cssColor('--teal-neon') : cssColor('--teal'))
  const orange = cssColor(
    '--dsdk-warning-color',
    cssColor(
      '--orange',
      isLight ? cssColor('--orange-light') : isNeon ? cssColor('--orange-neon') : cssColor('--orange'),
    ),
  )
  const cost = cssColor(
    '--cost',
    isLight ? cssColor('--cost-light') : isNeon ? cssColor('--cost-neon') : cssColor('--cost'),
  )
  const pos = cssColor(
    '--dsdk-success-color',
    cssColor('--pos', isLight ? cssColor('--pos-light') : isNeon ? cssColor('--pos-neon') : cssColor('--pos')),
  )
  const neg = cssColor(
    '--dsdk-danger-color',
    cssColor('--neg', isLight ? cssColor('--neg-light') : isNeon ? cssColor('--neg-neon') : cssColor('--neg')),
  )
  const ink = cssColor(
    '--dsdk-text-color',
    cssColor('--ink', isLight ? cssColor('--ink-light') : isNeon ? cssColor('--ink-neon') : cssColor('--ink')),
  )
  /* V6：暗色/霓虹用更亮墨色、亮色用更深墨色，轴标签对比拉满 */
  const mut = isLight
    ? cssColor('--dsdk-text-color-darker', cssColor('--mut-chart-light'))
    : cssColor('--note', isNeon ? cssColor('--note-neon') : cssColor('--note-dark'))
  const mut2 = isLight
    ? cssColor('--dsdk-text-color-dim', cssColor('--mut2'))
    : isNeon
      ? cssColor('--mut2-neon')
      : cssColor('--mut2-dark')
  const line = cssColor(
    '--dsdk-panel-border-default',
    cssColor('--line', isNeon ? cssColor('--line-neon') : cssColor('--line')),
  )
  const mono = cssColor('--dsdk-font-mono', 'ui-monospace, monospace')
  const tipBg = isLight
    ? cssColor('--chart-tooltip-bg-light')
    : isNeon
      ? cssColor('--chart-tooltip-bg-neon')
      : cssColor('--chart-tooltip-bg-dark')
  const tipShadow = isLight
    ? cssColor('--chart-tooltip-shadow-light')
    : isNeon
      ? cssColor('--chart-tooltip-shadow-neon')
      : cssColor('--chart-tooltip-shadow-dark')

  return {
    color: [accent, purple, teal, orange, cost, pos, accent, neg],
    backgroundColor: 'transparent',
    textStyle: {
      color: ink,
      fontFamily: `-apple-system,"PingFang SC",sans-serif,${mono}`,
      fontSize: 12,
    },
    grid: { left: 54, right: 36, top: 34, bottom: 40 },
    categoryAxis: {
      axisLine: { lineStyle: { color: line, width: 1 } },
      axisLabel: { color: mut, fontSize: 12, fontWeight: 500 },
      splitLine: { show: false },
      axisTick: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisLabel: { color: mut2, fontSize: 12, fontWeight: 500 },
      splitLine: {
        lineStyle: {
          color: line,
          type: 'dashed',
          opacity: isLight ? 0.7 : isNeon ? 0.55 : 0.45,
        },
      },
    },
    legend: {
      textStyle: { color: mut, fontSize: 12, fontWeight: 500 },
      pageTextStyle: { color: mut2 },
    },
    tooltip: {
      backgroundColor: tipBg,
      borderColor: accent,
      borderWidth: 1,
      textStyle: { color: ink, fontSize: 12 },
      extraCssText: tipShadow,
    },
  }
}

export function currentThemeMode(): 'neon' | 'dark' | 'light' {
  if (typeof document === 'undefined') return 'neon'
  const ds = document.documentElement.dataset.theme
  if (ds === 'neon' || ds === 'dark' || ds === 'light') return ds
  return document.documentElement.classList.contains('theme-light') ? 'light' : 'dark'
}
