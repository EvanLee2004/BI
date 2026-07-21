import type { BUPageVM, CockpitVM, PageVM } from '../types/vm'

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' })
  if (r.status === 401) {
    // 会话过期 → 看端登录（54.4·C 替代 legacy shell fragments 401 跳转）
    if (typeof location !== 'undefined' && !location.pathname.startsWith('/admin')) {
      location.replace('/login')
    }
    throw new Error('未登录')
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error((d as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}

export async function fetchCockpitVm(): Promise<CockpitVM> {
  return apiGet<CockpitVM>('/api/v1/vm/cockpit')
}

export async function fetchBuVm(name: string): Promise<BUPageVM> {
  return apiGet<BUPageVM>(`/api/v1/vm/bu/${encodeURIComponent(name)}`)
}

export async function fetchSession() {
  return apiGet<Record<string, unknown>>('/api/v1/session')
}

/** 2.2.5：产品版本号（任意登录会话可读；前端不硬编码 VERSION） */
export async function fetchProductVersion(): Promise<{ version?: string; stage?: string; label?: string }> {
  return apiGet('/api/version')
}

export type { PageVM }
