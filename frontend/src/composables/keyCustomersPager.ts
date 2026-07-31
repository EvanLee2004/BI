/**
 * 重点客户池列表分页 SSOT（3.6.1 · 纯函数）
 * pageSize 固定 20；序号在池+过滤+搜索结果上跨页 1-based 连续。
 */

export const KC_POOL_PAGE_SIZE = 20

export function pageCount(total: number, pageSize = KC_POOL_PAGE_SIZE): number {
  const n = Math.max(0, Math.floor(Number(total) || 0))
  const ps = Math.max(1, Math.floor(Number(pageSize) || KC_POOL_PAGE_SIZE))
  return Math.max(1, Math.ceil(n / ps) || 1)
}

export function clampPage(
  page: number,
  total: number,
  pageSize = KC_POOL_PAGE_SIZE,
): number {
  const pages = pageCount(total, pageSize)
  const p = Math.floor(Number(page) || 1)
  if (!Number.isFinite(p) || p < 1) return 1
  return Math.min(p, pages)
}

/** 当前页切片（空列表 → []，不抛错） */
export function slicePage<T>(
  items: readonly T[],
  page: number,
  pageSize = KC_POOL_PAGE_SIZE,
): T[] {
  const all = items || []
  const ps = Math.max(1, Math.floor(Number(pageSize) || KC_POOL_PAGE_SIZE))
  const p = clampPage(page, all.length, ps)
  const start = (p - 1) * ps
  return all.slice(start, start + ps)
}

/**
 * 跨页连续 1-based 序号。
 * page=2、localIndex=0、pageSize=20 → 21
 */
export function rowIndex1Based(
  page: number,
  localIndex: number,
  pageSize = KC_POOL_PAGE_SIZE,
): number {
  const ps = Math.max(1, Math.floor(Number(pageSize) || KC_POOL_PAGE_SIZE))
  const p = Math.max(1, Math.floor(Number(page) || 1))
  const i = Math.max(0, Math.floor(Number(localIndex) || 0))
  return (p - 1) * ps + i + 1
}

export function pageInfoDisp(
  page: number,
  total: number,
  pageSize = KC_POOL_PAGE_SIZE,
): string {
  const n = Math.max(0, Math.floor(Number(total) || 0))
  if (n <= 0) return '共 0 条 · 第 1/1 页'
  const pages = pageCount(n, pageSize)
  const p = clampPage(page, n, pageSize)
  return `共 ${n} 条 · 第 ${p}/${pages} 页`
}

/** 区间摘要：21–40 / 共 N（空 → 0–0 / 共 0） */
export function pageRangeDisp(
  page: number,
  total: number,
  pageSize = KC_POOL_PAGE_SIZE,
): string {
  const n = Math.max(0, Math.floor(Number(total) || 0))
  if (n <= 0) return '0–0 / 共 0'
  const ps = Math.max(1, Math.floor(Number(pageSize) || KC_POOL_PAGE_SIZE))
  const p = clampPage(page, n, ps)
  const start = (p - 1) * ps + 1
  const end = Math.min(p * ps, n)
  return `${start}–${end} / 共 ${n}`
}
