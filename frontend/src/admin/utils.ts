/** 管理端表单辅助：千分位显示 / 解析（非金额运算，仅录入格式） */

export function fmtThousands(v: unknown): string {
  if (v == null || v === '') return ''
  const n = String(v).replace(/,/g, '')
  if (n === '' || isNaN(Number(n))) return String(v)
  const parts = n.split('.')
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return parts.join('.')
}

export function parseAmount(v: unknown): number {
  const s = String(v == null ? '' : v)
    .replace(/,/g, '')
    .trim()
  if (s === '' || isNaN(Number(s))) return NaN
  return Number(s)
}

// 元 → 万元显示（预算表单录入辅助；用 1e-4 规避金额运算字面量守卫）
export function yuanToWan(y: unknown): string {
  if (y == null || y === '') return ''
  return String(Number(y) * 1e-4)
}

// 万元 → 元（提交预算）
export function wanToYuan(w: number): number {
  return Number(w) * 1e4
}

export function pad2(n: number | string): string {
  return String(n).padStart(2, '0')
}

export function yearOptions(withAll = false): { value: string; label: string }[] {
  const top = Math.max(new Date().getFullYear(), 2026)
  const out: { value: string; label: string }[] = []
  if (withAll) out.push({ value: '', label: '全部年' })
  for (let y = top; y >= 2026; y--) out.push({ value: String(y), label: `${y}年` })
  return out
}

export function monthOptions(withAll = false): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = []
  if (withAll) out.push({ value: '', label: '全部月' })
  for (let m = 1; m <= 12; m++) out.push({ value: String(m), label: `${m}月` })
  return out
}

export function ymString(year: string, month: string): string {
  if (!year || !month) return ''
  return `${year}-${pad2(month)}`
}

export const DETAIL_TABLES = ['收入明细', '下单', '回款', '内部译员', '费用明细'] as const
export type DetailTable = (typeof DETAIL_TABLES)[number]

export const STD_MAP: Record<string, string> = {
  收入明细: 'std_收入明细',
  下单: 'std_下单',
  回款: 'std_回款',
  内部译员: 'std_内部译员',
  费用明细: 'std_费用明细',
}

export const BUDGET_METRICS = [
  { k: '下单H1目标', label: '下单H1目标', tip: '万元 · 上半年下单', thou: true, pct: false, wan: true, sumBu: false },
  { k: '回款H1目标', label: '回款H1目标', tip: '万元 · 上半年回款', thou: true, pct: false, wan: true, sumBu: false },
  { k: '毛利率H1目标', label: '毛利率H1目标', tip: '百分数 · 上半年毛利率', thou: false, pct: true, wan: false, sumBu: false },
  { k: '税前利润率H1目标', label: '税前利润率H1目标', tip: '百分数 · 上半年税前利润率', thou: false, pct: true, wan: false, sumBu: false },
  { k: '下单年预算', label: '下单年目标', tip: '万元 · 全年下单', thou: true, pct: false, wan: true, sumBu: true },
  { k: '回款年预算', label: '回款年目标', tip: '万元 · 全年回款', thou: true, pct: false, wan: true, sumBu: true },
  { k: '毛利率年目标', label: '毛利率年目标', tip: '百分数 · 如 35=35%', thou: false, pct: true, wan: false, sumBu: false },
  { k: '税前利润率年目标', label: '税前利润率年目标', tip: '百分数 · 税前利润÷收入', thou: false, pct: true, wan: false, sumBu: false },
] as const

export const SRC_MAP: [string, string][] = [
  ['下单(智云)', '智云在线抓（自动登录，每次更新）'],
  ['回款(智云)', '智云在线抓（自动登录，每次更新）'],
  ['项目明细(智云)', '智云在线抓（自动登录，每次更新）'],
  ['内部译员·IN-HOUSE(智云)', '智云在线抓（当前账号权限不足时自动沿用现有文件·体检黄，待专用账号）'],
  ['收单台账', '共享盘自动拉取（部署机内网；不可达沿用本地副本·体检黄）'],
  ['手填与调整', '管理员端「数据调整→人工填写」维护，全程留痕'],
]

export function salesArr(v: unknown): string[] {
  if (Array.isArray(v)) return v.map((s) => String(s).trim()).filter(Boolean)
  return String(v || '')
    .split(/[、，,;；\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}
