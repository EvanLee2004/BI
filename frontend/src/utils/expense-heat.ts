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

/** 从 VM area_* 构建 heatmap 格子（与 ExpenseHeatmap 渲染同源）。 */
export function buildExpenseHeatPack(
  areaLabels: string[] | undefined,
  areaSeries: AreaSeriesIn[] | undefined,
): HeatPack {
  const labels = (areaLabels || []).map(String)
  const seriesIn = areaSeries || []
  const cats = seriesIn.map((s) => String(s.name || ''))
  const data: [number, number, number][] = []
  const dispMap: Record<string, string> = {}
  let vmax = 0
  seriesIn.forEach((s, yi) => {
    const row = s.data || []
    const disps = s.data_disp || []
    row.forEach((v, xi) => {
      const n = Number(v) || 0
      data.push([xi, yi, n])
      dispMap[`${xi},${yi}`] = String(disps[xi] ?? '')
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
