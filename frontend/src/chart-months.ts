/**
 * 年视图 X 轴铺满 1~12 月：有数月保留 VM 值/显示串，无数月占位空串（前端不造金额）。
 * 仅当已有标签全部像「N月」且不足 12 时启用。
 * 任务书61·C-2：pad 后可用 clipToCurrentMonth 裁掉未来空月（仅显示层，不改数值）。
 */

const MONTH_RE = /^(\d{1,2})月$/

export function isMonthAxis(labels: string[]): boolean {
  if (!labels.length) return false
  return labels.every((l) => MONTH_RE.test(String(l).trim()))
}

/**
 * 当前系统月上界（1–12）。优先用后端下发的 chart_month_max / daily.default_end（尊重 period_pin）。
 */
export function resolveMonthCap(opts?: {
  chartMonthMax?: number | null
  defaultEnd?: string | null
  now?: Date
}): number {
  const raw = opts?.chartMonthMax
  if (raw != null && Number.isFinite(Number(raw))) {
    const n = Math.trunc(Number(raw))
    if (n >= 1 && n <= 12) return n
  }
  const de = String(opts?.defaultEnd || '').trim()
  if (/^\d{4}-\d{2}/.test(de)) {
    const m = Number(de.slice(5, 7))
    if (m >= 1 && m <= 12) return m
  }
  const d = opts?.now || new Date()
  return Math.min(12, Math.max(1, d.getMonth() + 1))
}

/**
 * 裁 x 轴到「当前系统月」：只保留 1..cap 月（如 7 月 → 1–7），未来月整段不画。
 * 仅裁显示；不改任何已有数值/显示串。
 */
export function clipToCurrentMonth(
  labels: string[],
  series: number[][],
  disps: string[][],
  monthCap: number,
): { labels: string[]; series: number[][]; disps: string[][] } {
  const cap = Math.min(12, Math.max(1, Math.trunc(Number(monthCap) || 12)))
  if (!isMonthAxis(labels)) {
    return { labels: [...labels], series: series.map((s) => [...s]), disps: disps.map((d) => [...d]) }
  }
  const keepIdx: number[] = []
  labels.forEach((lab, i) => {
    const m = MONTH_RE.exec(String(lab).trim())
    if (m && Number(m[1]) <= cap) keepIdx.push(i)
  })
  if (!keepIdx.length || keepIdx.length === labels.length) {
    if (keepIdx.length === labels.length) {
      return { labels: [...labels], series: series.map((s) => [...s]), disps: disps.map((d) => [...d]) }
    }
  }
  return {
    labels: keepIdx.map((i) => labels[i]),
    series: series.map((s) => keepIdx.map((i) => s[i] ?? 0)),
    disps: disps.map((d) => keepIdx.map((i) => (d[i] != null ? String(d[i]) : ''))),
  }
}

/**
 * @param labels VM 轴标签
 * @param series 同长度数值序列（可多条）
 * @param disps 同长度显示串序列（可多条）
 * @returns 铺到 12 月的 labels / series / disps
 */
export function padYearMonths(
  labels: string[],
  series: number[][],
  disps: string[][],
): { labels: string[]; series: number[][]; disps: string[][] } {
  if (!isMonthAxis(labels) || labels.length >= 12) {
    return { labels: [...labels], series: series.map((s) => [...s]), disps: disps.map((d) => [...d]) }
  }
  const fullLab = Array.from({ length: 12 }, (_, i) => `${i + 1}月`)
  const idxOf = new Map<number, number>()
  labels.forEach((lab, i) => {
    const m = MONTH_RE.exec(String(lab).trim())
    if (m) idxOf.set(Number(m[1]), i)
  })
  const outSeries = series.map(() => Array(12).fill(0) as number[])
  const outDisps = disps.map(() => Array(12).fill('') as string[])
  for (let mo = 1; mo <= 12; mo++) {
    const src = idxOf.get(mo)
    const j = mo - 1
    if (src == null) continue
    series.forEach((s, si) => {
      outSeries[si][j] = Number(s[src]) || 0
    })
    disps.forEach((d, di) => {
      outDisps[di][j] = d[src] != null ? String(d[src]) : ''
    })
  }
  return { labels: fullLab, series: outSeries, disps: outDisps }
}

/**
 * 轴 max 至少盖住序列峰值 + 一格留白（防柱顶/折线出画布）。
 * 不改显示串；仅视觉刻度上限。
 * 防护：结果不得比 dataMax 大出离谱（避免 分/万 混用或 interval 异常产生 1e7 裸轴）。
 */
export function axisMaxCover(
  vmMax: number | undefined,
  interval: number | undefined,
  seriesVals: number[],
): number | undefined {
  const dataMax = seriesVals.reduce((a, b) => {
    const n = Number(b)
    return Number.isFinite(n) ? Math.max(a, n) : a
  }, 0)
  if (!(dataMax > 0) && !(vmMax != null && vmMax > 0)) return vmMax

  let maxV = vmMax != null && vmMax > 0 ? Number(vmMax) : undefined
  const need = dataMax > 0 ? dataMax * 1.14 : 0

  if (need > 0 && (maxV == null || need > maxV)) {
    if (interval && interval > 0 && interval < dataMax * 2) {
      maxV = Math.ceil(need / interval) * interval
      if (maxV < need) maxV += interval
    } else {
      maxV = need
    }
  } else if (maxV != null && interval && interval > 0 && interval < maxV) {
    /* 已盖住数据时仍加一格给柱顶字 */
    const bumped = maxV + interval
    if (dataMax <= 0 || bumped <= dataMax * 3) maxV = bumped
  }

  /* 硬顶：不超过 dataMax 的 2.5 倍（防脏 interval） */
  if (dataMax > 0 && maxV != null && maxV > dataMax * 2.5) {
    maxV = dataMax * 1.2
    if (interval && interval > 0 && interval < dataMax) {
      maxV = Math.ceil(maxV / interval) * interval
    }
  }
  return maxV
}

/**
 * 54.14 R-24：比率轴（% 线）上限自适应数据最大值，线永远在绘图区内。
 * - 负值：min 随数据下探并留边
 * - 0：min=0
 * - 超 100%：max 抬到 ceil(max*1.08) 至少盖住峰值
 * 不改显示串；仅视觉刻度。
 */
export function ratioAxisBounds(
  vals: Array<number | null | undefined>,
  opts?: { floorMax?: number },
): { min: number; max: number } {
  const floorMax = opts?.floorMax ?? 100
  let lo = 0
  let hi = 0
  let any = false
  for (const v of vals) {
    if (v == null) continue
    const n = Number(v)
    if (!Number.isFinite(n)) continue
    if (!any) {
      lo = hi = n
      any = true
    } else {
      lo = Math.min(lo, n)
      hi = Math.max(hi, n)
    }
  }
  if (!any) return { min: 0, max: floorMax }
  let min = lo < 0 ? Math.floor(lo * 1.08) : 0
  let max = Math.max(floorMax, hi)
  if (hi > 0) {
    max = Math.max(max, Math.ceil(hi * 1.08))
  }
  // 至少一格视觉余量：全 0 时仍给 100
  if (max <= min) max = min + Math.max(floorMax, 1)
  return { min, max }
}
