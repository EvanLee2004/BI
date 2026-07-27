/** 将 fetch/网络/HTTP 异常译成用户可读中文（2.6.10 V-5：不透 HTTP 码/堆栈）。 */

export type Httpish = {
  status?: number
  message?: string
  detail?: string
}

const FALLBACK = '暂时打不开，请稍后再试'

/** 按 HTTP 状态码的人话（给用户，不含技术串）。 */
export function friendlyFromStatus(status: number): string {
  if (status === 401) return '登录已失效，请重新登录'
  if (status === 403) return '你的账号没有这个页面的权限，请联系管理员开通'
  if (status === 404) return '没有找到这个页面'
  if (status === 409) return '操作冲突，请稍后重试'
  if (status === 500 || status === 502) return FALLBACK
  if (status === 503) return '数据还在准备中，请稍后刷新'
  if (status === 504) return '请求超时，请稍后重试'
  if (status >= 400 && status < 500) return '暂时打不开，请稍后再试'
  if (status >= 500) return FALLBACK
  return FALLBACK
}

export function friendlyError(err: unknown): string {
  if (err == null) return FALLBACK
  if (typeof err === 'object' && err !== null && 'status' in err) {
    const st = Number((err as Httpish).status)
    if (Number.isFinite(st) && st > 0) {
      // 401 由上层进登录；这里仍给安全文案
      return friendlyFromStatus(st)
    }
  }
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
  // 绝不把 HTTP 数字 / 英文异常类名透给用户
  if (/\bHTTP\s*\d{3}\b/i.test(m) || /^HTTP\s*\d{3}/i.test(m)) {
    const code = Number((m.match(/\b(\d{3})\b/) || [])[1] || 0)
    return code ? friendlyFromStatus(code) : FALLBACK
  }
  if (/error:|exception|traceback|typeerror|referenceerror|syntaxerror/i.test(m)) {
    return FALLBACK
  }
  // 已知业务中文：无权限类
  if (m.includes('无权') || m.includes('无权限') || m.includes('没有这个') || m.includes('驾驶舱权限')) {
    return '你的账号没有这个页面的权限，请联系管理员开通'
  }
  if (m.includes('未登录') || m.includes('请先登录') || m.includes('需要登录') || m.includes('需要管理员登录')) {
    return '登录已失效，请重新登录'
  }
  if (m.includes('不存在') || m.includes('未配置') || m.includes('没有找到')) {
    return '没有找到这个页面'
  }
  if (m.includes('尚未生成') || m.includes('暂无数据') || m.includes('数据还在')) {
    return '数据还在准备中，请稍后刷新'
  }
  // 兜底：若像技术串则压住
  if (/^[A-Za-z0-9_./:\-\[\]'"\s]+$/.test(m) && /[{}<>]|status|detail|null|undefined/.test(low)) {
    return FALLBACK
  }
  // 短中文业务文案可保留；过长/含路径的压住
  if (m.length > 80 || m.includes('/api/') || m.includes('Traceback')) {
    return FALLBACK
  }
  // 默认：仍避免原样吐后端 detail 中的技术片段
  if (/[A-Za-z]{3,}/.test(m) && !/[\u4e00-\u9fff]/.test(m)) {
    return FALLBACK
  }
  return m || FALLBACK
}

/** 用户可见文案中不得出现的技术形态（测试用）。 */
export function hasTechLeak(text: string): boolean {
  const t = text || ''
  if (/\bHTTP\s*\d{3}\b/i.test(t)) return true
  if (/TypeError|ReferenceError|SyntaxError|Traceback|Exception/i.test(t)) return true
  return false
}
