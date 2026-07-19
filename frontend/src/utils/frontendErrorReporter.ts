/**
 * B-5：全局前端错误 → POST /api/v1/client-error（只写日志、限流在服务端）。
 * 不发送 cookie 外的敏感字段；消息/栈截断。
 */

let installed = false

function postError(payload: Record<string, string>) {
  try {
    const body = JSON.stringify(payload)
    // keepalive 避免页面卸载丢报
    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      const blob = new Blob([body], { type: 'application/json' })
      navigator.sendBeacon('/api/v1/client-error', blob)
      return
    }
    void fetch('/api/v1/client-error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      credentials: 'same-origin',
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* 上报失败静默 */
  }
}

export function installFrontendErrorReporter() {
  if (installed || typeof window === 'undefined') return
  installed = true
  window.onerror = (message, source, lineno, colno, error) => {
    postError({
      message: String(message || 'error'),
      stack: error?.stack ? String(error.stack).slice(0, 1200) : `${source || ''}:${lineno || 0}:${colno || 0}`,
      page: String(location.pathname + location.search).slice(0, 200),
    })
    return false
  }
  window.addEventListener('unhandledrejection', (ev) => {
    const r = ev.reason
    const msg = r instanceof Error ? r.message : String(r || 'unhandledrejection')
    const stack = r instanceof Error && r.stack ? r.stack.slice(0, 1200) : ''
    postError({
      message: msg,
      stack,
      page: String(location.pathname + location.search).slice(0, 200),
    })
  })
}
