/**
 * 任务书54·B：ECharts 主题全面从 SciFi kit CSS 变量派生（+ theme.css 业务色）。
 * 任务书54.1：V6 图表文字清晰度（轴/图例字号≥11、对比提高）。
 * 目标：图表与 kit 面板肉眼同一套设计；亮暗纯前端 CSS 切换。
 */

function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/** 解析后的正文色（ECharts canvas 不能吃 CSS var()，图内 label 必须用 hex/rgb）。 */
export function themeInkColor(): string {
  const mode = currentThemeMode()
  const isLight = mode === 'light'
  return cssVar('--dsdk-text-color', cssVar('--ink', isLight ? '#15202b' : '#eaf1ff'))
}

export function kanbanTheme(mode: 'neon' | 'dark' | 'light' = 'dark') {
  const isLight = mode === 'light'
  const isNeon = mode === 'neon'
  const accent = cssVar(
    '--dsdk-accent-color-secondary',
    cssVar('--blue', isLight ? '#0891b2' : isNeon ? '#2ff3ff' : '#22d3ee'),
  )
  const purple = cssVar(
    '--dsdk-accent-color-main',
    cssVar('--purple', isLight ? '#6d28d9' : isNeon ? '#d16bff' : '#c084fc'),
  )
  const teal = cssVar('--teal', isLight ? '#0d9488' : isNeon ? '#2ee6c8' : '#2dd4bf')
  const orange = cssVar(
    '--dsdk-warning-color',
    cssVar('--orange', isLight ? '#c2410c' : isNeon ? '#ffd23f' : '#fbbf24'),
  )
  const cost = cssVar('--cost', isLight ? '#8b9aab' : isNeon ? '#6b7fa0' : '#64769e')
  const pos = cssVar(
    '--dsdk-success-color',
    cssVar('--pos', isLight ? '#0f766e' : isNeon ? '#3dffb0' : '#34d399'),
  )
  const neg = cssVar(
    '--dsdk-danger-color',
    cssVar('--neg', isLight ? '#c2410c' : isNeon ? '#ff5c85' : '#fb7185'),
  )
  const ink = cssVar('--dsdk-text-color', cssVar('--ink', isLight ? '#15202b' : isNeon ? '#eef4ff' : '#eaf1ff'))
  /* V6：暗色/霓虹用更亮墨色、亮色用更深墨色，轴标签对比拉满 */
  const mut = isLight
    ? cssVar('--dsdk-text-color-darker', cssVar('--mut', '#3d4a5c'))
    : cssVar('--note', isNeon ? '#c5d2ec' : '#c5d0e8')
  const mut2 = isLight
    ? cssVar('--dsdk-text-color-dim', cssVar('--mut2', '#4a5a6e'))
    : isNeon
      ? '#b0c0e0'
      : '#a8b6d4'
  const line = cssVar(
    '--dsdk-panel-border-default',
    cssVar('--line', isNeon ? 'rgba(47,243,255,.22)' : 'rgba(125,211,252,.16)'),
  )
  const mono = cssVar('--dsdk-font-mono', cssVar('--mono', 'ui-monospace, monospace'))

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
      backgroundColor: isLight ? 'rgba(255,255,255,0.96)' : isNeon ? 'rgba(2,8,20,0.94)' : 'rgba(10,16,32,0.92)',
      borderColor: accent,
      borderWidth: 1,
      textStyle: { color: ink, fontSize: 12 },
      extraCssText: isLight
        ? 'box-shadow:0 4px 16px rgba(8,145,178,.12);'
        : isNeon
          ? 'box-shadow:0 0 22px rgba(47,243,255,.35);'
          : 'box-shadow:0 0 18px rgba(34,211,238,.25);',
    },
  }
}

export function currentThemeMode(): 'neon' | 'dark' | 'light' {
  if (typeof document === 'undefined') return 'neon'
  const ds = document.documentElement.dataset.theme
  if (ds === 'neon' || ds === 'dark' || ds === 'light') return ds
  return document.documentElement.classList.contains('theme-light') ? 'light' : 'dark'
}

