import type { BUPageVM, CockpitVM, PageVM } from '../types/vm'
import { friendlyFromStatus } from '../utils/friendlyError'
import { createSessionSingleflight } from '../utils/sessionSingleflight'

/** 会话 cookie：仅 `kanban_sid`（2.7.1+）；请求须 credentials:same-origin。 */
/** 带 HTTP 状态的错误，供 store 按状态码分流（2.6.10 V-5）。 */
export class ApiError extends Error {
  status: number
  constructor(status: number, message?: string) {
    super(message || friendlyFromStatus(status))
    this.name = 'ApiError'
    this.status = status
  }
}

export type ApiGetInit = {
  signal?: AbortSignal
}

export async function apiGet<T = unknown>(path: string, init?: ApiGetInit): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin', signal: init?.signal })
  if (r.status === 401) {
    // 401 session expired → store.authRequired → App LoginView（不依赖中文 detail、不 location.replace）
    throw new ApiError(401, '登录已失效，请重新登录')
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    const detail = typeof (d as { detail?: string }).detail === 'string' ? (d as { detail: string }).detail : ''
    // 用户文案按状态码生成；detail 仅进 console
    if (detail) {
      console.warn('[api]', path, r.status, detail)
    }
    throw new ApiError(r.status, friendlyFromStatus(r.status))
  }
  return r.json() as Promise<T>
}

export async function fetchCockpitVm(init?: ApiGetInit): Promise<CockpitVM> {
  return apiGet<CockpitVM>('/api/v1/vm/cockpit', init)
}

export async function fetchBuVm(name: string, init?: ApiGetInit): Promise<BUPageVM> {
  return apiGet<BUPageVM>(`/api/v1/vm/bu/${encodeURIComponent(name)}`, init)
}

/** AUDIT-017：同页 GET /api/v1/session 单飞；登录成功/登出后 invalidateSessionCache */
const sessionSf = createSessionSingleflight(() => apiGet<Record<string, unknown>>('/api/v1/session'))

export async function fetchSession() {
  return sessionSf.get()
}

export function invalidateSessionCache(): void {
  sessionSf.invalidate()
}

/** 2.2.5：产品版本号（任意登录会话可读；前端不硬编码 VERSION） */
export async function fetchProductVersion(): Promise<{ version?: string; stage?: string; label?: string }> {
  return apiGet('/api/v1/version')
}

export type { PageVM }
