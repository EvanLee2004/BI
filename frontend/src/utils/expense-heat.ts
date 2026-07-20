/**
 * 54.14 R-26：费用热力格子数据打包（纯函数，组件与测试共用）。
 * 仅映射 VM expense.area_*；零金额运算。
 */
export type AreaSeriesIn = {
  name?: string
  data?: number[]
  data_disp?: string[]
}

export type HeatPack = {
  labels: string[]
  cats: string[]
  data: [number, number, number][]
  dispMap: Record<string, string>
  vmax: number
}

/** 从 VM area_* 构建 heatmap 格子（与 ExpenseHeatmap 渲染同源）。
 *  monthCap：任务书61·C-2，只保留 1..cap 月（未来空月不画）；只裁显示索引，不改 VM。 */
export function buildExpenseHeatPack(
  areaLabels: string[] | undefined,
  areaSeries: AreaSeriesIn[] | undefined,
  monthCap?: number | null,
): HeatPack {
  const rawLabels = (areaLabels || []).map(String)
  const seriesIn = areaSeries || []
  const cats = seriesIn.map((s) => String(s.name || ''))
  const cap =
    monthCap != null && Number.isFinite(Number(monthCap))
      ? Math.min(12, Math.max(1, Math.trunc(Number(monthCap))))
      : null
  let keepIdx = rawLabels.map((_, i) => i)
  if (cap != null && rawLabels.length) {
    const filtered: number[] = []
    rawLabels.forEach((lab, i) => {
      const m = /^(\d{1,2})月$/.exec(String(lab).trim())
      if (m) {
        if (Number(m[1]) <= cap) filtered.push(i)
      } else {
        filtered.push(i)
      }
    })
    if (filtered.length) keepIdx = filtered
  }
  const labels = keepIdx.map((i) => rawLabels[i])
  const data: [number, number, number][] = []
  const dispMap: Record<string, string> = {}
  let vmax = 0
  seriesIn.forEach((s, yi) => {
    const row = s.data || []
    const disps = s.data_disp || []
    keepIdx.forEach((srcXi, xi) => {
      const n = Number(row[srcXi]) || 0
      data.push([xi, yi, n])
      dispMap[`${xi},${yi}`] = String(disps[srcXi] ?? '')
      if (n > vmax) vmax = n
    })
  })
  return { labels, cats, data, dispMap, vmax }
}

/** 抽最多 n 个非零格（按金额降序），用于对账。 */
export function pickHeatCells(
  pack: HeatPack,
  n = 3,
): Array<{ xi: number; yi: number; value: number; disp: string; label: string; cat: string }> {
  const ranked = [...pack.data]
    .filter((d) => d[2] > 0)
    .sort((a, b) => b[2] - a[2])
    .slice(0, n)
  return ranked.map(([xi, yi, value]) => ({
    xi,
    yi,
    value,
    disp: pack.dispMap[`${xi},${yi}`] || '',
    label: pack.labels[xi] || '',
    cat: pack.cats[yi] || '',
  }))
}
