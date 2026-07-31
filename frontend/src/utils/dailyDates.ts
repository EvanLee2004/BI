/**
 * 日查日期快捷（3.6.1 · 纯函数）
 * 与 DailyQuery「本月/昨天」共用 new Date() 本地日历体系。
 */

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** 本地日历日 yyyy-mm-dd */
export function ymdOf(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/**
 * 昨天（本地日历）：从 now 减一天。
 * 1 日 → 上月最后一天；1 月 1 日 → 上年 12 月 31 日。
 */
export function yesterdayYmd(now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  return ymdOf(d)
}

/** 本月 1 日～今天（含） */
export function thisMonthRangeYmd(now: Date = new Date()): { start: string; end: string } {
  const y = now.getFullYear()
  const m = now.getMonth() + 1
  return {
    start: `${y}-${pad2(m)}-01`,
    end: ymdOf(now),
  }
}
