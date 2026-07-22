/**
 * 2.3.0 S4.B / 2.3.1 S1 KPI count-up（铁律例外：仅展示插值，禁止金额运算）。
 *
 * 硬约束：
 * 1. 中间帧只用后端 number value 插值
 * 2. 禁止从 value_disp 反解数字
 * 3. 最后一帧显式赋 value_disp 原串
 * 4. 非纯数字 disp 直接不动画
 *
 * 2.3.1：播放条件解绑主题——三主题均可播，仅 reduced-motion 否决。
 */

import { prefersReducedMotion } from '../chart-fx'

/** value_disp 是否允许动画（纯数字形态，可含千分位逗号与可选负号）。 */
export function isAnimatableDisp(disp: unknown): boolean {
  if (disp == null) return false
  const s = String(disp).trim()
  if (!s) return false
  if (s === '-' || s === '—' || s === '–' || s === 'N/A' || s === 'n/a') return false
  /* 含 % 或 em-dash 等 → 不动画；纯数字（可负、可千分位）才动画 */
  if (/%/.test(s) || /[—–]/.test(s)) return false
  return /^-?[\d,]+(\.\d+)?$/.test(s)
}

function formatIntermediate(n: number): string {
  /* 纯显示：一位小数 + 千分位（与万口径常见展示对齐）；不参与后续计算 */
  const rounded = Math.round(n * 10) / 10
  const neg = rounded < 0
  const abs = Math.abs(rounded)
  const [intPart, dec = '0'] = abs.toFixed(1).split('.')
  const withComma = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${neg ? '-' : ''}${withComma}.${dec}`
}

export type CountUpHandlers = {
  onFrame: (text: string) => void
  onDone: (finalDisp: string) => void
}

/**
 * 启动 count-up。返回 cancel 函数。
 * prefers-reduced-motion 或 disp 不可动画时立即 onDone(value_disp)。
 */
export function runCountUp(
  value: number,
  valueDisp: string,
  handlers: CountUpHandlers,
  opts?: { durationMs?: number },
): () => void {
  const disp = valueDisp == null ? '' : String(valueDisp)
  if (prefersReducedMotion() || !isAnimatableDisp(disp) || !Number.isFinite(value)) {
    handlers.onDone(disp)
    return () => {}
  }

  const duration = Math.min(opts?.durationMs ?? 800, 800)
  const start = performance.now()
  let raf = 0
  let cancelled = false

  const tick = (now: number) => {
    if (cancelled) return
    const t = Math.min(1, (now - start) / duration)
    /* cubicOut */
    const eased = 1 - Math.pow(1 - t, 3)
    if (t >= 1) {
      /* 终帧：显式赋 value_disp 原串，禁止插值「碰巧等于」 */
      handlers.onDone(disp)
      return
    }
    handlers.onFrame(formatIntermediate(value * eased))
    raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
  return () => {
    cancelled = true
    if (raf) cancelAnimationFrame(raf)
  }
}
