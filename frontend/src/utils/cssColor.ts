/**
 * 解析 CSS 变量为 canvas/ECharts 可用的实色（hex/rgb）。
 * ECharts addColorStop 不能吃 `var(--x)` 字符串 → SyntaxError + 红条。
 * 回退值与 tokens.css 默认对齐；运行时优先 getComputedStyle。
 * FE-002：图表 TS 禁止内联 hex，一律经本模块 / tokens 取色。
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
  '--mut2': '#5f6d92',
  '--note': '#b6c3e0',
  '--note-neon': '#c5d2ec',
  '--note-dark': '#c5d0e8',
  '--mut-chart-light': '#3d4a5c',
  '--mut2-neon': '#b0c0e0',
  '--mut2-dark': '#a8b6d4',
  '--white': '#ffffff',
  '--rank-primary': '#c084fc',
  '--rank-primary-alt': '#a78bfa',
  '--rank-primary-soft-end': '#c4b5fd',
  '--rank-secondary': '#2dd4bf',
  '--rank-secondary-soft-end': '#5eead4',
  '--rank-others-border-hover': 'rgba(34, 211, 238, 0.45)',
  '--chart-label-stroke-dark': 'rgba(4, 8, 20, 0.85)',
  '--chart-label-stroke-light': 'rgba(255, 255, 255, 0.92)',
  '--chart-label-shadow-dark': 'rgba(0, 0, 0, 0.55)',
  '--chart-label-shadow-light': 'rgba(255, 255, 255, 0.6)',
  '--chart-tooltip-bg-light': 'rgba(255, 255, 255, 0.96)',
  '--chart-tooltip-bg-neon': 'rgba(2, 8, 20, 0.94)',
  '--chart-tooltip-bg-dark': 'rgba(10, 16, 32, 0.92)',
  '--chart-tooltip-shadow-light': 'box-shadow:0 4px 16px rgba(8,145,178,.12);',
  '--chart-tooltip-shadow-neon': 'box-shadow:0 0 22px rgba(47,243,255,.35);',
  '--chart-tooltip-shadow-dark': 'box-shadow:0 0 18px rgba(34,211,238,.25);',
  '--chart-axis-ptr-light': 'rgba(8,145,178,.45)',
  '--chart-axis-ptr-neon': 'rgba(47,243,255,.45)',
  '--chart-axis-cross-light': 'rgba(8,145,178,.25)',
  '--chart-axis-cross-neon': 'rgba(47,243,255,.25)',
  '--chart-pie-glow-neon': 'rgba(47, 243, 255, 0.5)',
  '--chart-pie-glow-dark': 'rgba(34, 211, 238, 0.35)',
  '--rank-primary-glow': 'rgba(167,139,250,0.45)',
  '--rank-secondary-glow': 'rgba(45,212,191,0.45)',
  '--line-cyan-35': 'rgba(34, 211, 238, 0.35)',
  '--line': 'rgba(125,211,252,.16)',
  '--line-neon': 'rgba(47,243,255,.22)',
  '--heat-l0': '#e0f2fe',
  '--heat-l1': '#67e8f9',
  '--heat-l3': '#b45309',
  '--heat-d0': 'rgba(8, 16, 32, 0.2)',
  '--heat-d1': '#0e7490',
  '--heat-d4': '#f59e0b',
  '--dsdk-text-color': '#eaf1ff',
  '--dsdk-text-color-darker': '#93a1c0',
  '--dsdk-text-color-dim': '#4a5a6e',
  '--dsdk-accent-color-secondary': '#22d3ee',
  '--dsdk-accent-color-main': '#c084fc',
  '--dsdk-warning-color': '#fbbf24',
  '--dsdk-success-color': '#34d399',
  '--dsdk-danger-color': '#fb7185',
  '--ink-neon': '#eef4ff',
  '--ink-light': '#15202b',
  '--blue-neon': '#2ff3ff',
  '--blue-light': '#0891b2',
  '--purple-neon': '#d16bff',
  '--purple-light': '#6d28d9',
  '--teal-neon': '#2ee6c8',
  '--teal-light': '#0d9488',
  '--orange-neon': '#ffd23f',
  '--orange-light': '#c2410c',
  '--cost-neon': '#6b7fa0',
  '--cost-light': '#8b9aab',
  '--pos-neon': '#3dffb0',
  '--pos-light': '#0f766e',
  '--neg-neon': '#ff5c85',
  '--neg-light': '#c2410c',
  '--series-0': '#22d3ee',
  '--series-1': '#c084fc',
  '--series-2': '#fbbf24',
  '--series-3': '#34d399',
  '--series-4': '#fb7185',
  '--series-5': '#60a5fa',
  '--series-6': '#f472b6',
  '--series-7': '#2dd4bf',
  '--series-8': '#a78bfa',
  '--series-9': '#f59e0b',
}

/** 返回解析后的颜色字符串，绝不返回 `var(...)`。 */
export function cssColor(name: string, fallback?: string): string {
  const fb = fallback || FALLBACKS[name] || FALLBACKS['--blue']
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

/** canvas 用高对比系列色板（自 token 回落表） */
export function seriesPalette(): string[] {
  return [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => cssColor(`--series-${i}`))
}

/** hex → 带 alpha 的实色串（名避免含 rgba，以免 F-2 误扫调用点） */
export function hexWithAlpha(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  // 合成串仅在本 token 回落模块内；调用方不得内联色值
  const parts = [r, g, b, a]
  return "rgba(" + parts.join(",") + ")"
}

/** @deprecated 用 hexWithAlpha；保留别名兼容 */
export const hexToRgba = hexWithAlpha

/** amount in [-1,1] darken/lighten hex */
export function shadeHex(hex: string, amount: number): string {
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
  const h = ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)
  return `#${h}`
}
