/**
 * 解析 CSS 变量为 canvas/ECharts 可用的实色（hex/rgb）。
 * ECharts addColorStop 不能吃 `var(--x)` 字符串 → SyntaxError + 红条。
 * 回退值与 tokens.css / theme.css 默认对齐；运行时优先 getComputedStyle。
 */
const FALLBACKS: Record<string, string> = {
  '--blue': '#22d3ee',
  '--purple': '#c084fc',
  '--teal': '#2dd4bf',
  '--orange': '#fbbf24',
  '--cost': '#64769e',
  '--pos': '#34d399',
  '--neg': '#fb7185',
  '--ink': '#eaf1ff',
  '--mut': '#93a1c0',
  '--note': '#b6c3e0',
  '--rank-primary': '#c084fc',
  '--rank-primary-alt': '#a78bfa',
  '--rank-secondary': '#2dd4bf',
  '--rank-others-border-hover': 'rgba(34, 211, 238, 0.45)',
  '--chart-label-stroke-dark': 'rgba(4, 8, 20, 0.85)',
  '--chart-label-stroke-light': 'rgba(255, 255, 255, 0.92)',
  '--line-cyan-35': 'rgba(34, 211, 238, 0.35)',
  '--heat-l0': '#e0f2fe',
  '--heat-l1': '#67e8f9',
  '--heat-l3': '#b45309',
  '--heat-d0': 'rgba(8, 16, 32, 0.2)',
  '--heat-d1': '#0e7490',
  '--heat-d4': '#f59e0b',
  '--dsdk-text-color': '#eaf1ff',
  '--dsdk-text-color-darker': '#93a1c0',
  '--dsdk-accent-color-secondary': '#22d3ee',
  '--dsdk-accent-color-main': '#c084fc',
}

/** 返回解析后的颜色字符串，绝不返回 `var(...)`。 */
export function cssColor(name: string, fallback?: string): string {
  const fb = fallback || FALLBACKS[name] || '#22d3ee'
  if (typeof document === 'undefined') return fb
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    if (!v) return fb
    // 防御：若仍是 var() 引用链，回退
    if (v.startsWith('var(')) return fb
    return v
  } catch {
    return fb
  }
}
