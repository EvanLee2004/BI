/** 将 fetch/网络异常译成用户可读中文（54 终局·零散补漏）。 */
export function friendlyError(err: unknown): string {
  if (err == null) return '操作失败，请稍后重试'
  if (typeof err === 'string') return friendlyMessage(err)
  if (err instanceof Error) return friendlyMessage(err.message)
  return friendlyMessage(String(err))
}

export function friendlyMessage(msg: string): string {
  const m = (msg || '').trim()
  const low = m.toLowerCase()
  if (
    low.includes('failed to fetch') ||
    low.includes('networkerror') ||
    low.includes('network request failed') ||
    low.includes('load failed') ||
    low.includes('fetch failed')
  ) {
    return '服务暂时不可达，请稍后重试'
  }
  if (low.includes('timeout') || low.includes('timed out')) {
    return '请求超时，请稍后重试'
  }
  if (low.includes('abort')) {
    return '请求已取消'
  }
  return m || '操作失败，请稍后重试'
}
