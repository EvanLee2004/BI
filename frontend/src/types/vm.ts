/**
 * 任务书51·B8：与后端 pydantic CockpitVM / BUPageVM 等逐字段对齐的 TypeScript 契约。
 * 金额/比率一律 *_disp 显示串；前端零金额运算。
 *
 * 54.14 R-20 · disp 单位约定（防「万万」）：
 * - **整串含「万」**：donut_center.total_disp、views.total_disp、amount_disp/amt_disp、
 *   排名 revenue_disp、KPI feet peak/ar、部分 subs → 前端原样展示。
 * - **裸数字串**：KPI value_disp(+value_unit)、donut 扇区 value_disp、图表序列 *_disp、
 *   回款摘要 orders/receipts/gap/target/budget_month_disp → 需要时用 withWanUnit() 幂等拼接。
 */

export type AxisTick = { value: number; label: string }

export type KpiDelta = { show: boolean; cls: string; text: string }
export type KpiSub = { label: string; value_disp: string }
export type KpiFoot = { kind: string; label: string; value_disp: string }
export type KpiTarget = {
  empty?: boolean
  kind?: string
  label?: string
  tgt_disp?: string
  cur_disp?: string
  done_disp?: string
  pct_disp?: string
  bar_w?: number
  cls?: string
}
export type BuOrderRow = {
  name: string
  amount_disp: string
  badge_disp: string
  bar_w: number
  cls: string
  tip: string
}
export type KpiCard = {
  label: string
  period_tag: string
  value_disp: string
  value_unit: string
  delta: KpiDelta
  subs: KpiSub[]
  target: KpiTarget | null
  bu_orders: BuOrderRow[]
  feet: KpiFoot[]
  src: string
  data_key: string
}
export type KpiCardsVM = {
  year_key: string
  period_keys: string[]
  body_by_period: Record<string, string>
  cards_by_period: Record<string, KpiCard[]>
}

export type TrendVM = {
  svg_html: string
  labels: string[]
  revenue: number[]
  cost: number[]
  margin_pct: number[]
  revenue_disp: string[]
  cost_disp: string[]
  margin_pct_disp: string[]
  y_axis_labels: string[]
  y_axis_ticks: AxisTick[]
  y_axis_min: number
  y_axis_max: number
  y_axis_interval: number
}

export type PLRow = {
  name: string
  amt_disp: string
  kind: string
  formula: string
  open_key: string | null
  total: boolean
  grand: boolean
  is_pct: boolean
}
export type PLDetailLine = { name: string; amt_disp: string; kind: string; sub: boolean }
export type PLDetail = { title: string; lines: PLDetailLine[] }
export type PLTablePeriod = { rows: PLRow[]; details: Record<string, PLDetail> }
export type PLTableVM = {
  body_by_period: Record<string, string>
  pl_tag: string
  table_by_period: Record<string, PLTablePeriod>
}

export type AreaSeries = { name: string; data: number[]; data_disp: string[] }
export type DonutItem = { name: string; value: number; value_disp: string; pct_disp: string }
export type DonutCenter = { title: string; total_disp: string }
export type ExpenseHBarLine = { name: string; amt_disp: string }
export type ExpenseHBar = {
  key: string
  name: string
  amt_disp: string
  bar_w: number
  sink: boolean
  fine: ExpenseHBarLine[]
}
export type ExpenseViewsPeriod = {
  total_disp: string
  by_category: ExpenseHBar[]
  by_pc: ExpenseHBar[]
  by_dept: ExpenseHBar[]
}
export type ExpenseVM = {
  body_by_period: Record<string, string>
  trend_html: string
  area_categories: string[]
  area_labels: string[]
  area_series: AreaSeries[]
  area_totals_disp: string[]
  donut_by_period: Record<string, DonutItem[]>
  views_by_period: Record<string, ExpenseViewsPeriod>
  donut_center_by_period: Record<string, DonutCenter>
  area_y_axis_labels: string[]
  area_y_axis_ticks: AxisTick[]
  area_y_axis_min: number
  area_y_axis_max: number
  area_y_axis_interval: number
}

export type RankItem = {
  i: number
  name: string
  revenue_disp?: string
  margin_disp?: string
  bar_w?: number
  wo?: number
  wr?: number
  order_disp?: string
  receipt_disp?: string
  mkey?: string
}
export type RankSide = {
  title: string
  dim: string
  conc_disp: string
  items: RankItem[]
  others: { names?: number | string; amt_disp?: string; amt?: string; margin_disp?: string; count?: number | string } | null
  empty: boolean
  full_items: RankItem[]
  show_meta?: boolean
  embed_full?: boolean
}
export type ProfitRankPeriod = {
  start: string
  end: string
  customer: RankSide
  sales: RankSide
}
export type RankViewBlk = {
  title?: string
  dim?: string
  items?: RankItem[]
  others?: { names?: number | string; amt?: string; count?: number | string }
  empty?: boolean
  embed_full?: boolean
  full_items?: RankItem[]
}
export type RankView = {
  visible?: boolean
  start?: string
  end?: string
  sales?: RankViewBlk
  customer?: RankViewBlk
}
export type RankingsVM = {
  rankings_view: Record<string, RankView>
  rankings_monthly_data: Record<string, RankItem[]>
  profit_rank_body: Record<string, string>
  profit_rank_by_period: Record<string, ProfitRankPeriod>
}

export type ReceiptsVM = {
  receipts_html: string
  receipts_budget: string
  labels: string[]
  receipts: number[]
  orders: number[]
  receipts_disp: string[]
  orders_disp: string[]
  ratio_pct_disp: string[]
  y_axis_labels: string[]
  y_axis_ticks: AxisTick[]
  y_axis_min: number
  y_axis_max: number
  y_axis_interval: number
  /** 各周期摘要显示串（orders/receipts/gap/ratio/年目标） */
  summary_by_period: Record<string, Record<string, string>>
  /** 月均预算虚线数值（与柱同口径，后端已算好） */
  budget_month?: number
  budget_month_disp?: string
}

export type PeriodMonthRange = { month_from: string; month_to: string }
export type LedgerVM = {
  columns: string[]
  note: string
  forbidden_columns: string[]
  period_months: Record<string, PeriodMonthRange>
}

export type DailyDefaults = {
  year: number
  default_start: string
  default_end: string
  year_key: string
}

/** 整体页 VM（CockpitVM） */
export type CockpitVM = {
  api_version: string
  scope: string
  year_key: string
  period_keys: string[]
  kpi: KpiCardsVM
  trend: TrendVM
  pl: PLTableVM
  expense: ExpenseVM
  rankings: RankingsVM
  receipts: ReceiptsVM
  ledger: LedgerVM
  period_bar: string
  daily_html: string
  daily: DailyDefaults
  numbers: Record<string, unknown>
  /** 任务书61·C-2：图表 x 轴月上界 1–12 */
  chart_month_max?: number
  /** 路由层注入的 BU 导航（非 pydantic 核心字段，extra allow） */
  bu_names?: string[]
  bu_nav_label?: string
  bu_nav_hint?: string
  bu_config_count?: number
  current_bu?: string
}

/** BU 页 VM */
export type BUPageVM = {
  scope: string
  bu_name: string
  year_key: string
  period_keys: string[]
  kpi: KpiCardsVM
  trend: TrendVM
  pl: PLTableVM
  expense: ExpenseVM
  rankings: RankingsVM
  receipts: ReceiptsVM
  ledger: LedgerVM
  period_bar: string
  daily_html: string
  daily: DailyDefaults
  numbers: Record<string, unknown>
  chart_month_max?: number
  bu_names?: string[]
  bu_nav_label?: string
  bu_nav_hint?: string
  bu_config_count?: number
  current_bu?: string
}

export type PageVM = CockpitVM | BUPageVM
