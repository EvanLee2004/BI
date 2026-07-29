<script setup lang="ts">
/**
 * 3.3.0 管理端「用户统计」：登录成功主指标 + 按账号/BU/形态 + 四图 + 明细。
 * 图表经 loadEcharts 异步加载，禁止静态 import echarts。
 * 色值只读 CSS 变量（admin.css tokens），遵守 F-2 守卫。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { jget } from '../api'
import { loadEcharts, type EChartsType } from '../../echarts-loader'

type Kpi = {
  login_ok?: number
  login_fail?: number
  active_accounts?: number
  detail_vm?: number
  export?: number
  logout?: number
}
type AccRow = {
  account?: string
  display_name?: string
  perm_label?: string
  bu_bucket?: string
  login_ok?: number
  login_fail?: number
  detail_vm?: number
  export?: number
  last_login_ok?: string
}
type BuRow = { bu_bucket?: string; login_ok?: number; login_fail?: number; active_accounts?: number }
type ActionRow = { action?: string; label?: string; count?: number; pct?: number }
type DailyRow = { date?: string; count?: number }
type EvRow = {
  id?: number
  time?: string
  account?: string
  action?: string
  label?: string
  summary?: string
  bu_bucket?: string
}

const pageEl = ref<HTMLElement | null>(null)
const days = ref(30)
const loading = ref(false)
const errMsg = ref('')
const note = ref('')
const windowLabel = ref('')
const kpi = ref<Kpi>({})
const byAccount = ref<AccRow[]>([])
const byBu = ref<BuRow[]>([])
const byAction = ref<ActionRow[]>([])
const daily = ref<DailyRow[]>([])

const tab = ref('account')
const evAction = ref('')
const evAccount = ref('')
const evLoading = ref(false)
const evTotal = ref(0)
const evItems = ref<EvRow[]>([])
const evLimit = 50
const evOffset = ref(0)

const chartAccountEl = ref<HTMLDivElement | null>(null)
const chartBuEl = ref<HTMLDivElement | null>(null)
const chartActionEl = ref<HTMLDivElement | null>(null)
const chartDailyEl = ref<HTMLDivElement | null>(null)
const charts: EChartsType[] = []
let destroyed = false

const dayOptions = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
  { label: '全部', value: 0 },
]

const actionOptions = [
  { label: '全部动作', value: '' },
  { label: '登录成功', value: 'login_ok' },
  { label: '登录失败', value: 'login_fail' },
  { label: '看端明细', value: 'detail_vm' },
  { label: '导出', value: 'export' },
  { label: '退出', value: 'logout' },
  { label: '其他访问', value: 'other_access' },
]

const evPage = computed(() => Math.floor(evOffset.value / evLimit) + 1)
const evPages = computed(() => Math.max(1, Math.ceil(evTotal.value / evLimit)))

function cssVar(name: string, fallback: string): string {
  const el = pageEl.value || document.documentElement
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

function chartPalette() {
  return {
    text: cssVar('--admin-us-chart-text', cssVar('--admin-fg', '')),
    muted: cssVar('--admin-us-chart-muted', cssVar('--admin-mut', '')),
    grid: cssVar('--admin-us-chart-grid', cssVar('--admin-line', '')),
    accent: cssVar('--admin-us-chart-accent', cssVar('--admin-cyan', '')),
    ok: cssVar('--admin-us-chart-ok', cssVar('--admin-ok-num', '')),
    pie: [
      cssVar('--admin-us-chart-accent', ''),
      cssVar('--admin-us-chart-ok', ''),
      cssVar('--admin-us-chart-warn', cssVar('--admin-orange', '')),
      cssVar('--admin-us-chart-bad', cssVar('--admin-alert-fg', '')),
      cssVar('--admin-us-chart-vio', cssVar('--admin-vio', '')),
      cssVar('--admin-us-chart-sky', cssVar('--admin-cyan', '')),
    ].filter(Boolean),
  }
}

function disposeCharts() {
  while (charts.length) {
    const c = charts.pop()
    try {
      c?.dispose()
    } catch {
      /* ignore */
    }
  }
}

async function renderCharts() {
  if (destroyed) return
  disposeCharts()
  const echarts = await loadEcharts()
  if (destroyed) return
  const pal = chartPalette()
  const commonText = { color: pal.text }
  const axisLine = { lineStyle: { color: pal.grid } }
  const splitLine = { lineStyle: { color: pal.grid } }

  if (chartAccountEl.value) {
    const top = byAccount.value
      .filter((r) => (r.login_ok || 0) > 0)
      .slice(0, 15)
      .reverse()
    const ch = echarts.init(chartAccountEl.value, undefined, { renderer: 'svg' })
    charts.push(ch)
    if (!top.length) {
      ch.setOption({
        title: {
          text: '暂无登录成功数据',
          left: 'center',
          top: 'middle',
          textStyle: { color: pal.muted, fontSize: 13 },
        },
      })
    } else {
      ch.setOption({
        animation: false,
        grid: { left: 88, right: 24, top: 16, bottom: 24 },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        xAxis: { type: 'value', axisLabel: commonText, axisLine, splitLine },
        yAxis: {
          type: 'category',
          data: top.map((r) => r.display_name || r.account || ''),
          axisLabel: { ...commonText, fontSize: 11 },
          axisLine,
        },
        series: [
          {
            type: 'bar',
            data: top.map((r) => r.login_ok || 0),
            itemStyle: { color: pal.accent, borderRadius: [0, 4, 4, 0] },
            barMaxWidth: 18,
          },
        ],
      })
    }
  }

  if (chartBuEl.value) {
    const rows = byBu.value.filter((r) => (r.login_ok || 0) > 0)
    const ch = echarts.init(chartBuEl.value, undefined, { renderer: 'svg' })
    charts.push(ch)
    if (!rows.length) {
      ch.setOption({
        title: {
          text: '暂无 BU 登录数据',
          left: 'center',
          top: 'middle',
          textStyle: { color: pal.muted, fontSize: 13 },
        },
      })
    } else {
      ch.setOption({
        animation: false,
        color: pal.pie,
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0, textStyle: commonText, type: 'scroll' },
        series: [
          {
            type: 'pie',
            radius: ['36%', '62%'],
            center: ['50%', '46%'],
            data: rows.map((r) => ({ name: r.bu_bucket || '?', value: r.login_ok || 0 })),
            label: { color: pal.text, formatter: '{b}\n{c}' },
          },
        ],
      })
    }
  }

  if (chartActionEl.value) {
    const rows = byAction.value
    const ch = echarts.init(chartActionEl.value, undefined, { renderer: 'svg' })
    charts.push(ch)
    if (!rows.length) {
      ch.setOption({
        title: {
          text: '暂无访问形态数据',
          left: 'center',
          top: 'middle',
          textStyle: { color: pal.muted, fontSize: 13 },
        },
      })
    } else {
      ch.setOption({
        animation: false,
        color: pal.pie,
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0, textStyle: commonText, type: 'scroll' },
        series: [
          {
            type: 'pie',
            radius: ['36%', '62%'],
            center: ['50%', '46%'],
            data: rows.map((r) => ({ name: r.label || r.action || '?', value: r.count || 0 })),
            label: { color: pal.text, formatter: '{b}\n{c}' },
          },
        ],
      })
    }
  }

  if (chartDailyEl.value) {
    const rows = daily.value
    const ch = echarts.init(chartDailyEl.value, undefined, { renderer: 'svg' })
    charts.push(ch)
    if (!rows.length) {
      ch.setOption({
        title: {
          text: '暂无日趋势',
          left: 'center',
          top: 'middle',
          textStyle: { color: pal.muted, fontSize: 13 },
        },
      })
    } else {
      ch.setOption({
        animation: false,
        grid: { left: 40, right: 16, top: 24, bottom: 40 },
        tooltip: { trigger: 'axis' },
        xAxis: {
          type: 'category',
          data: rows.map((r) => r.date || ''),
          axisLabel: { ...commonText, fontSize: 10, rotate: rows.length > 14 ? 40 : 0 },
          axisLine,
        },
        yAxis: {
          type: 'value',
          minInterval: 1,
          axisLabel: commonText,
          splitLine,
          axisLine,
        },
        series: [
          {
            type: 'bar',
            data: rows.map((r) => r.count || 0),
            itemStyle: { color: pal.ok, borderRadius: [3, 3, 0, 0] },
            barMaxWidth: 22,
          },
        ],
      })
    }
  }
}

function onResize() {
  for (const c of charts) {
    try {
      c.resize()
    } catch {
      /* ignore */
    }
  }
}

async function loadStats() {
  loading.value = true
  errMsg.value = ''
  try {
    const d = await jget<{
      days?: number
      window_start?: string
      window_end?: string
      kpi?: Kpi
      by_account?: AccRow[]
      by_bu?: BuRow[]
      by_action?: ActionRow[]
      daily_login_ok?: DailyRow[]
      note?: string
    }>(`/api/v1/admin/user_stats?days=${days.value}`)
    kpi.value = d.kpi || {}
    byAccount.value = d.by_account || []
    byBu.value = d.by_bu || []
    byAction.value = d.by_action || []
    daily.value = d.daily_login_ok || []
    note.value = d.note || ''
    const ws = d.window_start || ''
    const we = d.window_end || ''
    windowLabel.value = ws ? `${ws} ~ ${we}` : `全部（至 ${we}）`
    await nextTick()
    await renderCharts()
  } catch (e) {
    errMsg.value = String(e)
    ElMessage.error('加载用户统计失败：' + String(e))
  } finally {
    loading.value = false
  }
}

async function loadEvents() {
  evLoading.value = true
  try {
    const q = new URLSearchParams()
    q.set('days', String(days.value))
    q.set('limit', String(evLimit))
    q.set('offset', String(evOffset.value))
    if (evAction.value) q.set('action', evAction.value)
    if (evAccount.value.trim()) q.set('account', evAccount.value.trim())
    const d = await jget<{ total?: number; items?: EvRow[] }>(
      `/api/v1/admin/user_stats/events?${q.toString()}`,
    )
    evTotal.value = d.total || 0
    evItems.value = d.items || []
  } catch (e) {
    ElMessage.error('加载明细失败：' + String(e))
  } finally {
    evLoading.value = false
  }
}

async function refreshAll() {
  evOffset.value = 0
  await loadStats()
  await loadEvents()
}

function onDaysChange() {
  void refreshAll()
}

function prevEv() {
  if (evOffset.value <= 0) return
  evOffset.value = Math.max(0, evOffset.value - evLimit)
  void loadEvents()
}

function nextEv() {
  if (evOffset.value + evLimit >= evTotal.value) return
  evOffset.value += evLimit
  void loadEvents()
}

watch(evAction, () => {
  evOffset.value = 0
  void loadEvents()
})

onMounted(() => {
  window.addEventListener('resize', onResize)
  void refreshAll()
})

onBeforeUnmount(() => {
  destroyed = true
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<template>
  <div ref="pageEl" class="us-page" data-testid="user-stats-page" v-loading="loading">
    <div class="us-head">
      <h2 class="us-title">用户统计</h2>
      <p class="us-desc" data-testid="user-stats-note">
        基于登录与关键操作留痕（表 manual_配置变更·访问类）。
        <strong>次数主指标=登录成功</strong>；打开看板首页多数不单独记；
        <strong>看端明细不计入登录次数</strong>。不含密码与业务金额。历史自系统开始写审计日起有效。
      </p>
    </div>

    <div class="us-toolbar">
      <el-radio-group v-model="days" size="small" data-testid="user-stats-days" @change="onDaysChange">
        <el-radio-button v-for="o in dayOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
      </el-radio-group>
      <el-button size="small" type="primary" :loading="loading" data-testid="user-stats-refresh" @click="refreshAll">
        刷新
      </el-button>
      <span class="us-muted">{{ windowLabel }}</span>
      <span v-if="note" class="us-muted">· {{ note }}</span>
    </div>

    <div v-if="errMsg" class="us-err" data-testid="user-stats-error">{{ errMsg }}</div>

    <div class="us-kpi" data-testid="user-stats-kpi">
      <div class="us-kpi-card main">
        <div class="k">登录成功</div>
        <div class="v">{{ kpi.login_ok ?? 0 }}</div>
        <div class="s">主指标</div>
      </div>
      <div class="us-kpi-card">
        <div class="k">登录失败</div>
        <div class="v">{{ kpi.login_fail ?? 0 }}</div>
      </div>
      <div class="us-kpi-card">
        <div class="k">活跃账号</div>
        <div class="v">{{ kpi.active_accounts ?? 0 }}</div>
        <div class="s">至少 1 次登录成功</div>
      </div>
      <div class="us-kpi-card sub">
        <div class="k">看端明细</div>
        <div class="v">{{ kpi.detail_vm ?? 0 }}</div>
        <div class="s">非登录 · 副指标</div>
      </div>
      <div class="us-kpi-card sub">
        <div class="k">导出 / 退出</div>
        <div class="v">{{ (kpi.export ?? 0) + (kpi.logout ?? 0) }}</div>
        <div class="s">导出 {{ kpi.export ?? 0 }} · 退出 {{ kpi.logout ?? 0 }}</div>
      </div>
    </div>

    <div class="us-charts">
      <div class="us-chart-card">
        <div class="us-chart-title">账号 Top 登录成功</div>
        <div ref="chartAccountEl" class="us-chart" data-testid="user-stats-chart-account" />
      </div>
      <div class="us-chart-card">
        <div class="us-chart-title">按 BU 桶（登录成功）</div>
        <div ref="chartBuEl" class="us-chart" data-testid="user-stats-chart-bu" />
      </div>
      <div class="us-chart-card">
        <div class="us-chart-title">摘要形态分布</div>
        <div ref="chartActionEl" class="us-chart" data-testid="user-stats-chart-action" />
      </div>
      <div class="us-chart-card">
        <div class="us-chart-title">每日登录成功趋势</div>
        <div ref="chartDailyEl" class="us-chart" data-testid="user-stats-chart-daily" />
      </div>
    </div>

    <el-tabs v-model="tab" class="us-tabs" data-testid="user-stats-tabs">
      <el-tab-pane label="按账号" name="account">
        <el-table :data="byAccount" border size="small" empty-text="窗内暂无访问类事件" max-height="360">
          <el-table-column prop="account" label="账号" width="120" />
          <el-table-column prop="display_name" label="显示名" width="120" />
          <el-table-column prop="perm_label" label="权限" width="100" />
          <el-table-column prop="bu_bucket" label="BU 桶" min-width="120" />
          <el-table-column prop="login_ok" label="登录成功" width="96" />
          <el-table-column prop="login_fail" label="登录失败" width="96" />
          <el-table-column prop="detail_vm" label="看端明细" width="96" />
          <el-table-column prop="last_login_ok" label="最近登录成功" min-width="160" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="按 BU" name="bu">
        <el-table :data="byBu" border size="small" empty-text="窗内暂无 BU 数据" max-height="360">
          <el-table-column prop="bu_bucket" label="BU 桶" min-width="160" />
          <el-table-column prop="login_ok" label="登录成功" width="110" />
          <el-table-column prop="active_accounts" label="活跃账号" width="110" />
          <el-table-column prop="login_fail" label="登录失败" width="110" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="按形态" name="action">
        <el-table :data="byAction" border size="small" empty-text="窗内暂无形态数据" max-height="360">
          <el-table-column prop="label" label="动作" min-width="120" />
          <el-table-column prop="action" label="码" width="120" />
          <el-table-column prop="count" label="次数" width="100" />
          <el-table-column label="占比%" width="100">
            <template #default="{ row }">{{ row.pct ?? 0 }}%</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <div class="us-events" data-testid="user-stats-events">
      <div class="us-events-head">
        <h3>明细流水</h3>
        <el-select v-model="evAction" size="small" style="width: 140px" placeholder="动作">
          <el-option v-for="o in actionOptions" :key="o.value || 'all'" :label="o.label" :value="o.value" />
        </el-select>
        <el-input
          v-model="evAccount"
          size="small"
          clearable
          placeholder="账号筛选"
          style="width: 140px"
          @keyup.enter="() => { evOffset = 0; loadEvents() }"
          @clear="() => { evOffset = 0; loadEvents() }"
        />
        <el-button size="small" @click="() => { evOffset = 0; loadEvents() }">筛明细</el-button>
        <span class="us-muted">共 {{ evTotal }} 条 · 第 {{ evPage }}/{{ evPages }} 页</span>
        <el-button size="small" :disabled="evOffset <= 0 || evLoading" @click="prevEv">上一页</el-button>
        <el-button size="small" :disabled="evOffset + evLimit >= evTotal || evLoading" @click="nextEv">下一页</el-button>
      </div>
      <el-table :data="evItems" v-loading="evLoading" border size="small" empty-text="无匹配明细" max-height="420">
        <el-table-column prop="time" label="时间" width="170" />
        <el-table-column prop="account" label="账号" width="120" />
        <el-table-column prop="label" label="动作" width="100" />
        <el-table-column prop="bu_bucket" label="BU 桶" width="120" />
        <el-table-column prop="summary" label="摘要" min-width="240" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.us-page {
  padding: 4px 2px 24px;
  color: var(--admin-fg);
}
.us-head {
  margin-bottom: 12px;
}
.us-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.us-desc {
  margin: 0;
  max-width: 960px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--admin-mut);
}
.us-desc strong {
  color: var(--admin-us-title);
  font-weight: 600;
}
.us-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}
.us-muted {
  color: var(--admin-mut);
  font-size: 12px;
}
.us-err {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--admin-radius-sm);
  background: var(--admin-us-err-bg);
  color: var(--admin-us-err-fg);
  font-size: 13px;
}
.us-kpi {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.us-kpi-card {
  background: var(--admin-us-card-bg);
  border: 1px solid var(--admin-us-card-line);
  border-radius: var(--admin-radius);
  padding: 12px 14px;
  min-height: 88px;
}
.us-kpi-card.main {
  border-color: var(--admin-us-card-line-on);
  box-shadow: 0 0 0 1px var(--admin-us-card-glow) inset;
}
.us-kpi-card.sub .v {
  color: var(--admin-us-kpi-sub);
}
.us-kpi-card .k {
  font-size: 12px;
  color: var(--admin-mut);
  margin-bottom: 6px;
}
.us-kpi-card .v {
  font-size: 26px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  color: var(--admin-us-kpi-num);
  line-height: 1.1;
}
.us-kpi-card .s {
  margin-top: 6px;
  font-size: 11px;
  color: var(--admin-mut);
}
.us-charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.us-chart-card {
  background: var(--admin-us-card-bg);
  border: 1px solid var(--admin-us-card-line);
  border-radius: var(--admin-radius);
  padding: 10px 12px 8px;
}
.us-chart-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--admin-us-title);
  margin-bottom: 4px;
}
.us-chart {
  width: 100%;
  height: 260px;
  min-height: 220px;
}
.us-tabs {
  margin-bottom: 18px;
}
.us-events-head {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.us-events-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
@media (max-width: 1100px) {
  .us-kpi {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .us-charts {
    grid-template-columns: 1fr;
  }
}
</style>
