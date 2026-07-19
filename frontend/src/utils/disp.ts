/**
 * 54.14 R-20：VM `*_disp` 单位约定与防「万万」拼接。
 *
 * 约定（与 src/viewmodels 一致）：
 * - **整串（已含单位）**：`donut_center.total_disp`、`views.total_disp`、
 *   `amount_disp` / `amt_disp` / 排名 `revenue_disp`、KPI feet peak/ar 等 → 前端原样展示，勿再拼「万」。
 * - **裸数字串 + 独立 unit**：KPI `value_disp` + `value_unit`；环形扇区 `value_disp`；
 *   图表序列 `orders_disp`/`receipts_disp`/`revenue_disp`/`area_*_disp`；
 *   回款摘要 `orders_disp`/`gap_disp`/`*_target_disp`/`budget_month_disp` → 需要时再拼单位。
 *
 * 本模块提供幂等拼接：已以「万」结尾则不重复追加。
 */

/** 若串已以「万」结尾则原样返回，否则补「万」。空串/占位符原样。 */
export function withWanUnit(disp: string | null | undefined): string {
  const s = disp == null ? '' : String(disp).trim()
  if (!s || s === '—' || s === '-') return s
  if (s.endsWith('万')) return s
  return s + '万'
}

/** 渲染结果不得出现「万万」（回归守卫用）。 */
export function assertNoDoubleWan(text: string): boolean {
  return !String(text || '').includes('万万')
}

/** 从任意文本中收集含「万」的片段（测试辅助）。 */
export function findDoubleWan(text: string): string[] {
  const t = String(text || '')
  const out: string[] = []
  const re = /[\d,.\-−]+万万/g
  let m: RegExpExecArray | null
  while ((m = re.exec(t))) out.push(m[0])
  if (!out.length && t.includes('万万')) out.push('万万')
  return out
}
