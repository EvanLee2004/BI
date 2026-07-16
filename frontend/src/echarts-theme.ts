/** 任务书46·3B：ECharts 主题，色板取自 theme.css 变量（暗/亮两套） */

function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

export function kanbanTheme(mode: 'dark' | 'light' = 'dark') {
  const isLight = mode === 'light'
  return {
    color: [
      cssVar('--blue', isLight ? '#0891b2' : '#22d3ee'),
      cssVar('--purple', isLight ? '#6d28d9' : '#c084fc'),
      cssVar('--teal', isLight ? '#0d9488' : '#2dd4bf'),
      cssVar('--orange', isLight ? '#c2410c' : '#fbbf24'),
      cssVar('--cost', isLight ? '#8b9aab' : '#64769e'),
      cssVar('--pos', isLight ? '#0f766e' : '#34d399'),
      cssVar('--accent', isLight ? '#0891b2' : '#22d3ee'),
      cssVar('--neg', isLight ? '#c2410c' : '#fb7185'),
    ],
    backgroundColor: 'transparent',
    textStyle: {
      color: cssVar('--ink', isLight ? '#15202b' : '#eaf1ff'),
      fontFamily: '-apple-system,"PingFang SC",sans-serif',
    },
    grid: { left: 54, right: 36, top: 34, bottom: 40 },
    categoryAxis: {
      axisLine: { lineStyle: { color: cssVar('--line', 'rgba(125,211,252,.16)') } },
      axisLabel: { color: cssVar('--mut', '#93a1c0') },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisLabel: { color: cssVar('--mut2', '#5f6d92') },
      splitLine: { lineStyle: { color: cssVar('--line', 'rgba(125,211,252,.16)') } },
    },
  }
}

export function currentThemeMode(): 'dark' | 'light' {
  if (typeof document === 'undefined') return 'dark'
  return document.documentElement.classList.contains('theme-light') ? 'light' : 'dark'
}
