/**
 * B-5 / 任务书64·D5：全局前端错误 → 顶部友好条 + POST /api/v1/client-error。
 * 不发送 cookie 外的敏感字段；消息/栈截断。
 *
 * 2026-07-21：Chrome 在布局 reflow（如费用「按部门」master-detail）时
 * ResizeObserver 常抛无害 “loop completed with undelivered notifications”，
 * 不得当作用户可见异常。
 */

import type { App } from 'vue'

let installed = false
const BANNER_ID = 'kanban-global-error-banner'

/**
 * 浏览器无害噪声：不弹红条、不上报。
 * Chrome: "ResizeObserver loop completed with undelivered notifications."
 * 旧版: "ResizeObserver loop limit exceeded"
 */
export function isIgnorableClientError(message: string): boolean {
  return /ResizeObserver loop/i.test(String(message || ''))
}

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

/** 页面顶部友好错误条（不白屏；可关闭）。 */
export function showFriendlyErrorBanner(message: string) {
  if (typeof document === 'undefined') return
  if (isIgnorableClientError(message)) return
  let el = document.getElementById(BANNER_ID)
  if (!el) {
    el = document.createElement('div')
    el.id = BANNER_ID
    el.setAttribute('role', 'alert')
    el.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:99999;background:#b91c1c;color:#fff;' +
      'padding:10px 16px;font:14px/1.4 system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);'
    const close = document.createElement('button')
    close.type = 'button'
    close.textContent = '关闭'
    close.style.cssText =
      'float:right;margin-left:12px;background:transparent;border:1px solid #fff;color:#fff;border-radius:4px;cursor:pointer;padding:2px 8px;'
    close.onclick = () => el?.remove()
    el.appendChild(close)
    const span = document.createElement('span')
    span.dataset.msg = '1'
    el.appendChild(span)
    document.body.appendChild(el)
  }
  const span = el.querySelector('[data-msg="1"]') as HTMLElement | null
  if (span) {
    span.textContent = '页面出现异常，其余部分仍可使用。' + (message ? `（${message.slice(0, 120)}）` : '')
  }
}

function reportAndBanner(message: string, stack: string) {
  if (isIgnorableClientError(message)) return
  showFriendlyErrorBanner(message)
  postError({
    message: message.slice(0, 500),
    stack: stack.slice(0, 1200),
    page: typeof location !== 'undefined' ? String(location.pathname + location.search).slice(0, 200) : '',
  })
}

export function installFrontendErrorReporter(app?: App) {
  if (installed || typeof window === 'undefined') return
  installed = true
  window.onerror = (message, source, lineno, colno, error) => {
    reportAndBanner(
      String(message || 'error'),
      error?.stack ? String(error.stack) : `${source || ''}:${lineno || 0}:${colno || 0}`,
    )
    return false
  }
  window.addEventListener('unhandledrejection', (ev) => {
    const r = ev.reason
    const msg = r instanceof Error ? r.message : String(r || 'unhandledrejection')
    const stack = r instanceof Error && r.stack ? r.stack : ''
    reportAndBanner(msg, stack)
  })
  if (app) {
    app.config.errorHandler = (err, _instance, info) => {
      const e = err instanceof Error ? err : new Error(String(err))
      reportAndBanner(e.message || String(err), (e.stack || '') + (info ? `\ninfo:${info}` : ''))
    }
  }
}

/** Vue 根组件 onErrorCaptured 用：返回 false 阻止继续向上。 */
export function onVueErrorCaptured(err: unknown): boolean {
  const e = err instanceof Error ? err : new Error(String(err))
  reportAndBanner(e.message || String(err), e.stack || '')
  return false
}
