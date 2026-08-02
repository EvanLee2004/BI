/**
 * 54.14 R-26：费用热力格子数据打包（纯函数，组件与测试共用）。
 * 仅映射 VM expense.area_*；零金额运算。
 *
 * 3.7.5：图例范围用 data_disp（万级显示串），禁止把库内分值当「万」展示。
 * visualMap 的 min/max 仍用 data 数值（与格子 value 同尺，仅着色）。
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
  /** 平行：是否确认为 0（有 disp 且数值 0）；缺失则不进 data 或 value 为特殊 */
  missingMap: Record<string, boolean>
  dispMap: Record<string, string>
  /** 与 data 同尺（库内分），仅供 visualMap 着色 */
  vmax: number
  vmin: number
  vmid: number
  /** 权威显示串：取自 data_disp（万级裸数字，如 "123.5"），非分值 */
  vmin_disp: string
  vmid_disp: string
  vmax_disp: string
  unit: string
  /** 图例整句（不含二次「万」拼接；组件用 withWanUnit 拼单位） */
  legend_range: string
}

type Sample = { n: number; disp: string }

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
  const missingMap: Record<string, boolean> = {}
  const samples: Sample[] = []
  seriesIn.forEach((s, yi) => {
    const row = s.data || []
    const disps = s.data_disp || []
    keepIdx.forEach((srcXi, xi) => {
      const raw = row[srcXi]
      const disp = disps[srcXi]
      const key = `${xi},${yi}`
      const hasDisp = disp != null && String(disp).trim() !== ''
      const hasNum = raw != null && !Number.isNaN(Number(raw))
      if (!hasNum && !hasDisp) {
        missingMap[key] = true
        data.push([xi, yi, -1]) // 哨兵：缺失，不参与 vmax
        dispMap[key] = '—'
        return
      }
      const n = Number(raw) || 0
      // 显示串只认 data_disp；无 disp 时不伪造 fen→万换算（前端零金额运算）
      const dStr = hasDisp ? String(disp).trim() : '—'
      data.push([xi, yi, n])
      dispMap[key] = dStr
      missingMap[key] = false
      samples.push({ n, disp: dStr })
    })
  })
  const range = _rangeFromSamples(samples)
  return {
    labels,
    cats,
    data,
    dispMap,
    missingMap,
    vmax: range.vmax,
    vmin: range.vmin,
    vmid: range.vmid,
    vmin_disp: range.vmin_disp,
    vmid_disp: range.vmid_disp,
    vmax_disp: range.vmax_disp,
    unit: '万',
    legend_range: range.legend_range,
  }
}

/** 从样本取 min/mid/max 数值 + 对应 data_disp（不换算分）。 */
export function _rangeFromSamples(samples: Sample[]): {
  vmin: number
  vmid: number
  vmax: number
  vmin_disp: string
  vmid_disp: string
  vmax_disp: string
  legend_range: string
} {
  if (!samples.length) {
    return {
      vmin: 0,
      vmid: 0,
      vmax: 0,
      vmin_disp: '0.0',
      vmid_disp: '0.0',
      vmax_disp: '0.0',
      legend_range: '最小 0.0 / 中位 0.0 / 最大 0.0',
    }
  }
  const byN = [...samples].sort((a, b) => a.n - b.n)
  const lo = byN[0]
  const hi = byN[byN.length - 1]
  const positives = byN.filter((s) => s.n > 0)
  const mid = positives.length
    ? positives[Math.floor(positives.length / 2)]
    : lo
  const vmin_disp = lo.disp !== '—' ? lo.disp : '0.0'
  const vmax_disp = hi.disp !== '—' ? hi.disp : '0.0'
  const vmid_disp = mid.disp !== '—' ? mid.disp : '0.0'
  return {
    vmin: lo.n,
    vmid: mid.n,
    vmax: hi.n,
    vmin_disp,
    vmid_disp,
    vmax_disp,
    legend_range: `最小 ${vmin_disp} / 中位 ${vmid_disp} / 最大 ${vmax_disp}`,
  }
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
