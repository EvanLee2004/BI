/**
 * 管理端 API 客户端（credentials include · 与 static/admin jget/jpost 对齐）
 * Cookie 会话 kanban_session 由后端 Set-Cookie，前端不碰 token。
 */

export class AdminApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function api(path: string, opts?: RequestInit): Promise<Response> {
  const r = await fetch(path, { credentials: 'same-origin', ...opts })
  if (r.status === 401) {
    // 未登录 / 会话失效 → 回登录
    if (!location.pathname.startsWith('/admin/login') && location.pathname.startsWith('/admin')) {
      location.href = '/admin/login'
    }
    throw new AdminApiError(401, '需要管理员登录')
  }
  return r
}

export async function jget<T = unknown>(path: string): Promise<T> {
  const r = await api(path)
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new AdminApiError(r.status, (d as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}

export async function jpost<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) {
    throw new AdminApiError(r.status, (d as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  return d as T
}

/** 下载二进制（导出 Excel 等） */
export async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  const r = await api(path)
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new AdminApiError(r.status, (d as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  const blob = await r.blob()
  const a = document.createElement('a')
  const cd = r.headers.get('Content-Disposition') || ''
  const mfn = cd.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i)
  const fn = mfn ? decodeURIComponent(mfn[1].replace(/"/g, '')) : fallbackName
  a.href = URL.createObjectURL(blob)
  a.download = fn
  a.click()
  URL.revokeObjectURL(a.href)
}

/** 管理员 JSON 登录（与 static/admin_login 一致） */
export async function adminLogin(account: string, password: string): Promise<{ ok: boolean; redirect?: string; detail?: string }> {
  const r = await fetch('/api/v1/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ account, password }),
  })
  const j = await r.json().catch(() => ({}))
  if (r.ok && j && j.redirect) {
    return { ok: true, redirect: j.redirect as string }
  }
  const m = (j && (j.detail || j.message)) || '账号或密码不正确'
  return { ok: false, detail: typeof m === 'string' ? m : '账号或密码不正确' }
}

export async function fetchSession(): Promise<Record<string, unknown>> {
  return jget('/api/v1/session')
}
