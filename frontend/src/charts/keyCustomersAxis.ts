/**
 * 重点客户金额轴纯函数（3.6.0 G4 · 3.6.3 headroom）
 * 共同零轴：max 只来自当前选中系列峰值 × 固定 headroom；禁止用全局 amount_axis.max。
 * 无 ECharts / DOM 依赖，可供 node 单测驱动。
 * 禁止前端重算金额业务值——仅做展示轴留白。
 */

/** 峰值上方固定留白系数（P2-01）：轴略高于系列峰值，避免顶标贴边。 */
export const AMOUNT_AXIS_HEADROOM = 1.08

/** 金额模式 Y 轴上限：selectedLocalMax（万）× headroom；global 参数显式忽略。 */
export function resolveAmountAxisMax(
  selectedLocalMax: number,
  globalAmountAxisMax?: number | null,
): number {
  void globalAmountAxisMax
  const v = Number(selectedLocalMax)
  if (!Number.isFinite(v) || v < 0) return 0
  if (v === 0) return 0
  return v * AMOUNT_AXIS_HEADROOM
}

/** 从多系列月值数组取峰值（忽略 null/NaN） */
export function peakOfSeries(values: readonly (number | null | undefined)[]): number {
  let mx = 0
  for (const x of values) {
    if (x == null) continue
    const n = Number(x)
    if (!Number.isFinite(n)) continue
    if (n > mx) mx = n
  }
  return mx
}

/**
 * 2/20/50/100/200 万组合：选中小客时轴不得被全局 200 抬高。
 * 返回 { axisMax, ratioSmallToBig } 供断言（axisMax 含 headroom）。
 */
export function selectedVsGlobalAxisProbe(opts: {
  selectedPeaksWan: number[]
  globalAxisMaxWan: number
}): { axisMax: number; selectedPeak: number; ratioIfUsedGlobal: number } {
  const selectedPeak = Math.max(0, ...opts.selectedPeaksWan.map((n) => Number(n) || 0))
  const axisMax = resolveAmountAxisMax(selectedPeak, opts.globalAxisMaxWan)
  const g = Number(opts.globalAxisMaxWan) || 0
  return {
    axisMax,
    selectedPeak,
    ratioIfUsedGlobal: g > 0 ? selectedPeak / g : 0,
  }
}
