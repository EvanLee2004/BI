import type { BUPageVM, CockpitVM, PageVM } from '../types/vm'

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' })
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

export type { PageVM }
