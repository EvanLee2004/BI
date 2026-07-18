/** 54.11 R-02：将后端平铺 period_keys 映射为两段式粒度（纯前端、零改 VM）。 */

export type PeriodGrain = 'year' | 'quarter' | 'month' | 'custom'

export function classifyPeriodKey(k: string): PeriodGrain {
  if (/^\d{4}年$/.test(k)) return 'year'
  if (/Q[1-4]/.test(k)) return 'quarter'
  if (/^\d{4}年\d{1,2}月$/.test(k)) return 'month'
  return 'custom'
}

export function groupPeriodKeys(keys: string[]) {
  const year: string[] = []
  const quarter: string[] = []
  const month: string[] = []
  const custom: string[] = []
  for (const k of keys) {
    const g = classifyPeriodKey(k)
    if (g === 'year') year.push(k)
    else if (g === 'quarter') quarter.push(k)
    else if (g === 'month') month.push(k)
    else custom.push(k)
  }
  return { year, quarter, month, custom }
}

/** 自定义起止月 → 已有 key（仅当 key 在 keys 中存在）。 */
export function resolveCustomPeriodKey(
  keys: string[],
  year: string,
  fromM: number,
  toM: number,
): string {
  const a = Math.min(fromM, toM)
  const b = Math.max(fromM, toM)
  const cand = a === b ? `${year}年${a}月` : `${year}年${a}-${b}月`
  return keys.includes(cand) ? cand : ''
}
