<script setup lang="ts">
/**
 * 下单/回款情况：紫柱下单 + 青柱回款 + 月均预算虚线 + 右侧摘要（本年下单/回款 + 年目标进度条）。
 * 任务书61·A：删尚待回款/年标签/回款占下单/黄回款率线；目标进度条有则显。
 * 任务书61·C-2：x 轴裁到当前系统月。显示串全 VM；前端零金额运算（铁律2）。
 * 2.2.4·C：y 轴 max 覆盖 budget_month，月均预算虚线不再被裁。
 */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  axisLabelStyle,
  barGlowStyle,
  dataLabelStyle,
  legendTextStyle,
} from '../chart-fx'
import { axisMaxCover, clipToCurrentMonth, padYearMonths, resolveMonthCap } from '../chart-months'
import { withWanUnit } from '../utils/disp'
import { themeMode } from '../utils/theme'
import type { AxisTick, ReceiptsVM } from '../types/vm'

const store = useCockpitStore()
const r = computed((): Partial<ReceiptsVM> => store.vm?.receipts || {})

function tickLabel(ticks: AxisTick[], val: number): string {
  for (const t of ticks) {
    if (Math.abs(Number(t.value) - Number(val)) < 1e-9) return t.label
  }
  return ''
}

const side = computed(() => {
  const map = r.value.summary_by_period || {}
  const pk = store.period || ''
  return map[pk] || map[store.vm?.year_key || ''] || null
})

/** 右侧摘要：有本年下单/回款 或 任一年目标条才显示 */
const sideVisible = computed(() => {
  const s = side.value
  if (!s) return false
  if (s.orders_disp || s.receipts_disp) return true
  if (s.receipt_target_disp || s.order_target_disp) return true
  return false
})

const option = computed(() => {
  void themeMode.value
  const rawLabels = (r.value.labels || []).map((x) => String(x))
  const rawRecs = (r.value.receipts || []).map((x) => Number(x) || 0)
  const rawOrds = (r.value.orders || []).map((x) => Number(x) || 0)
  const rawRd = (r.value.receipts_disp || []).map((x) => String(x ?? ''))
  const rawOd = (r.value.orders_disp || []).map((x) => String(x ?? ''))
  const padded = padYearMonths(rawLabels, [rawRecs, rawOrds], [rawRd, rawOd])
  const monthCap = resolveMonthCap({
    chartMonthMax: (r.value as { chart_month_max?: number }).chart_month_max
      ?? (store.vm as { chart_month_max?: number } | null)?.chart_month_max,
    defaultEnd: store.vm?.daily?.default_end,
  })
  const clipped = clipToCurrentMonth(padded.labels, padded.series, padded.disps, monthCap)
  const labels = clipped.labels
  const recs = clipped.series[0]
  const ords = clipped.series[1]
  const rd = clipped.disps[0]
  const od = clipped.disps[1]
  const empty = (i: number) => !rd[i] && !od[i]
  const recPlot = recs.map((v, i) => (empty(i) ? null : v))
  const ordPlot = ords.map((v, i) => (empty(i) ? null : v))
  const ticks = r.value.y_axis_ticks || []
  const maxV0 = r.value.y_axis_max || (ticks.length ? ticks[ticks.length - 1].value : undefined)
  const interval =
    r.value.y_axis_interval || (ticks.length >= 2 ? ticks[1].value - ticks[0].value : undefined)
  const minV = r.value.y_axis_min ?? 0
  // 2.2.4·C：先算 bud，再纳入 y 轴上限（游戏等低量 BU 的月均预算虚线不再被裁出画面）
  const bud = Number(r.value.budget_month) || 0
  const maxV = axisMaxCover(maxV0, interval, [...recs, ...ords, bud])
  const cOrd = '#a78bfa'
  const cRec = '#22d3ee'
  // budget_month_disp 为裸数字；receipts_budget 已含「月均预算 X万」整句——勿双拼
  const budRaw = String(r.value.budget_month_disp || '').trim()
  const budFallback = String(r.value.receipts_budget || '').trim()
  const budLabel = budRaw
    ? `月均预算 ${withWanUnit(budRaw)}`
    : budFallback || '月均预算'
  const series: Record<string, unknown>[] = [
    {
      name: '下单',
      type: 'bar',
      data: ordPlot,
      barMaxWidth: 28,
      itemStyle: barGlowStyle(cOrd),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
        fontSize: 12,
      }),
    },
    {
      name: '回款',
      type: 'bar',
      data: recPlot,
      barMaxWidth: 28,
      itemStyle: barGlowStyle(cRec),
      label: dataLabelStyle({
        position: 'top',
        formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
        fontSize: 12,
      }),
    },
  ]
  // 月均预算虚线（后端 budget_month 已下发；标签用 budget_month_disp）
  if (bud > 0) {
    series.push({
      name: '月均预算',
      type: 'line',
      data: labels.map(() => bud),
      symbol: 'none',
      lineStyle: {
        type: 'dashed',
        width: 1.5,
        color: '#2dd4bf',
      },
      itemStyle: { color: '#2dd4bf' },
      label: {
        show: true,
        position: 'end',
        formatter: () => budLabel,
        color: '#2dd4bf',
        fontSize: 12,
      },
      tooltip: { show: true },
      z: 3,
    })
  }
  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params: { dataIndex: number; seriesName?: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        if (empty(i)) return `${labels[i] || ''} · 暂无数据`
        const budLine = budLabel && budLabel !== '月均预算' ? `<br/>${budLabel}` : ''
        return `${labels[i] || ''}<br/>下单 ${withWanUnit(od[i] || '—')}<br/>回款 ${withWanUnit(rd[i] || '—')}${budLine}`
      },
    },
    legend: {
      data: bud > 0 ? ['下单', '回款', '月均预算'] : ['下单', '回款'],
      bottom: 0,
      textStyle: legendTextStyle(),
    },
    grid: { left: 56, right: 28, top: 48, bottom: 56, containLabel: true },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: axisLabelStyle({ interval: 0 }),
    },
    yAxis: [
      {
        type: 'value',
        min: minV,
        max: maxV,
        interval,
        axisLabel: {
          formatter: (val: number) => {
            const lab = tickLabel(ticks, val)
            if (lab) return lab
            if (val === 0) return '0'
            return ''
          },
          ...axisLabelStyle(),
        },
      },
    ],
    series,
    ...animBlock(),
  }
})
const hasSeries = computed(() => (r.value.labels || []).length > 0)
</script>
<template>
  <SciFiPanel id="receiptsCard" title="下单/回款情况" panel-class="rc-card">
    <div v-if="hasSeries" class="rc-layout" :class="{ 'rc-solo': !sideVisible }">
      <div class="rc-body" data-chart="receipts">
        <EchartsHost :option="option" />
      </div>
      <aside v-if="sideVisible && side" class="rc-side" aria-label="下单/回款摘要">
        <div class="rc-hero">
          <div class="rc-hero-row">
            <span class="rc-k">本年下单</span>
            <span class="rc-v">{{ withWanUnit(side.orders_disp) }}</span>
          </div>
          <div class="rc-hero-row">
            <span class="rc-k">本年回款</span>
            <span class="rc-v rc-v-rec">{{ withWanUnit(side.receipts_disp) }}</span>
          </div>
        </div>
        <div v-if="side.receipt_target_disp" class="rc-bud" data-testid="rc-bud-receipt">
          <div class="rc-bud-h">
            <span>{{ side.receipt_title || '回款年目标' }}</span>
            <strong>{{ side.receipt_pct_disp }}</strong>
          </div>
          <div class="rc-bud-sub">目标 {{ withWanUnit(side.receipt_target_disp) }}</div>
          <div class="rc-bud-bar"><i :style="{ width: (side.receipt_bar_w || '0') + '%' }" /></div>
        </div>
        <div v-if="side.order_target_disp" class="rc-bud" data-testid="rc-bud-order">
          <div class="rc-bud-h">
            <span>{{ side.order_title || '下单年目标' }}</span>
            <strong>{{ side.order_pct_disp }}</strong>
          </div>
          <div class="rc-bud-sub">目标 {{ withWanUnit(side.order_target_disp) }}</div>
          <div class="rc-bud-bar"><i :style="{ width: (side.order_bar_w || '0') + '%' }" /></div>
        </div>
      </aside>
    </div>
    <div v-else class="ev-empty">暂无回款数据</div>
  </SciFiPanel>
</template>

<style scoped>
.rc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 240px);
  gap: 12px;
  align-items: stretch;
  min-height: 320px;
}
.rc-layout.rc-solo {
  grid-template-columns: 1fr;
}
.rc-body {
  min-width: 0;
  min-height: 320px;
  height: 100%;
}
.rc-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px 4px 8px;
  border-left: 1px solid rgba(125, 211, 252, 0.12);
  font-size: 12.5px;
}
.rc-hero-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
}
.rc-k {
  color: var(--note, #8b9bb4);
  font-weight: 500;
}
.rc-v {
  font-family: var(--num-font, ui-monospace, monospace);
  font-weight: 700;
  color: var(--ink, #e8eef8);
}
.rc-v-rec {
  color: #22d3ee;
}
.rc-bud-h {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
  font-weight: 600;
}
.rc-bud-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(125, 211, 252, 0.12);
  overflow: hidden;
}
.rc-bud-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #22d3ee, #a78bfa);
  border-radius: 3px;
}
.rc-bud-sub {
  font-size: 12px;
  color: var(--note, #8b9bb4);
  margin-bottom: 4px;
}
@media (max-width: 900px) {
  .rc-layout {
    grid-template-columns: 1fr;
  }
  .rc-side {
    border-left: none;
    border-top: 1px solid rgba(125, 211, 252, 0.12);
    padding: 10px 0 0;
  }
}
</style>
