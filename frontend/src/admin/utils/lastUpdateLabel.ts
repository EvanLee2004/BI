/**
 * 3.7.18：管理端顶栏体检 pill 文案。
 * 只显示「上次更新 YYYY-MM-DD HH:mm」；漏跑/告警不下沉到 pill 主文案。
 */

/** 空时间固定形态（单测与 UI 共用） */
export const LAST_UPDATE_EMPTY = '上次更新 —'

/**
 * 将 run_time / built_at 规范为 `YYYY-MM-DD HH:mm`；无法解析则返回 ''。
 * 含秒可截到分；已是目标格式则原样；ISO 等常见串尽量解析。
 */
export function formatLastUpdateTime(raw: unknown): string {
  if (raw == null) return ''
  const s = String(raw).trim()
  if (!s || s === '?' || s === '—' || s === '-') return ''

  // 已是 YYYY-MM-DD HH:mm 或带秒
  const m = s.match(
    /^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/,
  )
  if (m) return `${m[1]} ${m[2]}:${m[3]}`

  // 仅日期
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return `${s} 00:00`

  // Date 可解析
  const d = new Date(s)
  if (!Number.isNaN(d.getTime())) {
    const y = d.getFullYear()
    const mo = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const h = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${y}-${mo}-${day} ${h}:${mi}`
  }
  return ''
}

/** 时间字段优先级：run_time → built_at → 空 */
export function pickLastUpdateRaw(health: {
  run_time?: unknown
  built_at?: unknown
} | null | undefined): string {
  if (!health) return ''
  const fromRun = formatLastUpdateTime(health.run_time)
  if (fromRun) return fromRun
  return formatLastUpdateTime(health.built_at)
}

/** pill 主文案：`上次更新 YYYY-MM-DD HH:mm ▾` 或 `上次更新 — ▾` */
export function buildLastUpdatePillLabel(health: {
  run_time?: unknown
  built_at?: unknown
  run_reasons?: unknown
  warnings?: unknown
  result?: unknown
} | null | undefined): string {
  const t = pickLastUpdateRaw(health)
  const body = t ? `上次更新 ${t}` : LAST_UPDATE_EMPTY
  return body + ' ▾'
}

/** hover title：短状态，不堆漏跑时间表 */
export function buildLastUpdatePillTitle(health: {
  result?: unknown
  run_reasons?: unknown
  warnings?: unknown
} | null | undefined): string {
  const result = String(health?.result || '?')
  const reasons = (health?.run_reasons as string[] | undefined) || []
  const warns = (health?.warnings as string[] | undefined) || []
  const hasAlert = reasons.length > 0 || warns.length > 0
  if (result === '绿' && !hasAlert) return `管道 绿 · 点开看明细`
  if (hasAlert) return `管道 ${result} · 有运行告警 · 点开看明细`
  return `管道 ${result} · 点开看明细`
}

/** 断言用：pill 文案不得含漏跑/定时刷新等运维细节 */
export function pillHasForbiddenOpsTokens(label: string): boolean {
  return /漏跑|定时刷新|待补|\d{1,2}:\d{2}\s*,\s*\d{1,2}:\d{2}/.test(label)
}
