/** fetch 封装：/api/v1/vm/*，携带 cookie，401→跳登录 */

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' })
  if (r.status === 401) {
    window.location.href = '/login'
    throw new Error('未登录')
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error((d as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}

export async function fetchCockpitVm() {
  return apiGet<Record<string, unknown>>('/api/v1/vm/cockpit')
}

export async function fetchBuVm(name: string) {
  return apiGet<Record<string, unknown>>(`/api/v1/vm/bu/${encodeURIComponent(name)}`)
}

export async function fetchSession() {
  return apiGet<Record<string, unknown>>('/api/v1/session')
}
