/**
 * 2.4.3：纯 BU 会话打开根路径 / 或整体 cockpit 403 时的回流决策（纯函数，可单测）。
 * 权限不在前端抬高——只决定是否 location.replace 到 /bu/xxx。
 */

export type SessionLike = {
  can_main?: boolean
  is_admin?: boolean
  bus?: unknown
}

export function firstBuName(session: SessionLike | null | undefined): string | null {
  const bus = session?.bus
  if (!Array.isArray(bus) || bus.length === 0) return null
  const n = bus[0]
  if (n == null || String(n).trim() === '') return null
  return String(n)
}

/** 非管理员且无整体权限、且至少有一个可见 BU */
export function isPureBuSession(session: SessionLike | null | undefined): boolean {
  if (!session || typeof session !== 'object') return false
  if (session.is_admin || session.can_main) return false
  return firstBuName(session) != null
}

export function buPathFromSession(session: SessionLike | null | undefined): string | null {
  if (!isPureBuSession(session)) return null
  const name = firstBuName(session)
  if (!name) return null
  return '/bu/' + encodeURIComponent(name)
}

/** path 为 / 时，纯 BU → /bu/xxx；否则 null */
export function shouldRedirectRootToBu(
  pathname: string,
  session: SessionLike | null | undefined,
): string | null {
  const p = pathname || '/'
  if (p !== '/' && p !== '') return null
  return buPathFromSession(session)
}

/** loadMain / cockpit 403「无整体驾驶舱权限」等 */
export function isOverallForbiddenError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err ?? '')
  const m = (msg || '').trim()
  if (!m) return false
  if (m.includes('无整体')) return true
  if (m.includes('驾驶舱权限')) return true
  return false
}

export function navigateToBuPath(path: string): void {
  if (!path) return
  if (typeof location !== 'undefined') {
    location.replace(path)
  }
}
