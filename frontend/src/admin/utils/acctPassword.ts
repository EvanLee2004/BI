/**
 * 3.7.18：账号表密码列常显掩码与保存守卫。
 * 固定掩码占位不得作为新密码提交；空串=留空不改。
 */

/** 已设但无回显明文时的固定圆点占位（禁止写入保存 payload） */
export const ACCT_PW_FIXED_MASK = '••••••••'

export type AcctPwRow = {
  密码?: string
  password_set?: boolean
  初始密码?: boolean
  /** 本地新加、尚未服务端确认 */
  _localNew?: boolean
}

export function isLocalNewAcct(row: AcctPwRow | null | undefined): boolean {
  return !!(row && row._localNew)
}

export function hasRealPassword(row: AcctPwRow | null | undefined): boolean {
  if (!row) return false
  const pw = String(row.密码 ?? '')
  return pw.length > 0 && pw !== ACCT_PW_FIXED_MASK
}

/**
 * 已持久化（或非本地新行）且无真实密码串 → 用固定掩码，禁止空框。
 */
export function needsFixedPasswordMask(row: AcctPwRow | null | undefined): boolean {
  if (!row) return false
  if (isLocalNewAcct(row)) return false
  if (hasRealPassword(row)) return false
  // 非新行：password_set 或默认视为已存在
  return row.password_set === true || !isLocalNewAcct(row)
}

/** 输入框展示值：真密码 / 固定掩码 / 空（新行） */
export function acctPasswordDisplayValue(row: AcctPwRow | null | undefined): string {
  if (!row) return ''
  if (hasRealPassword(row)) return String(row.密码)
  if (needsFixedPasswordMask(row)) return ACCT_PW_FIXED_MASK
  return String(row.密码 ?? '')
}

/** 固定掩码态只读；有真密码或本地新行可编辑 */
export function isAcctPasswordReadonly(row: AcctPwRow | null | undefined): boolean {
  return needsFixedPasswordMask(row)
}

export function canRevealAcctPassword(row: AcctPwRow | null | undefined): boolean {
  return hasRealPassword(row)
}

/**
 * 保存 payload 用的密码：null = 不传（留空不改）。
 * 固定掩码与空串均视为不改。
 */
export function passwordForSave(pw: unknown): string | null {
  const s = String(pw ?? '').trim()
  if (!s || s === ACCT_PW_FIXED_MASK) return null
  return s
}

/** 新账号未填密码时的 placeholder */
export function acctPasswordPlaceholder(row: AcctPwRow | null | undefined): string {
  if (isLocalNewAcct(row) || (row && row.password_set !== true && !hasRealPassword(row) && !needsFixedPasswordMask(row))) {
    return '新账号必填'
  }
  return ''
}
