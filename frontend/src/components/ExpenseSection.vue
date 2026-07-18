<script setup lang="ts">
/** 期间费用构成：环形 + 构成四态。54.2：饼周无标签、图例横排底部（色点+名+金额）。 */
import { computed, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  chartMutedColor,
  chartTextColor,
  pieEmphasis,
  SERIES_PALETTE,
} from '../chart-fx'
import type { ExpenseHBar, ExpenseVM } from '../types/vm'

const store = useCockpitStore()
const exp = computed((): Partial<ExpenseVM> => store.vm?.expense || {})
const mode = ref<'donut' | 'fine' | 'pc' | 'dept'>('donut')

const items = computed(() => {
  const by = exp.value.donut_by_period || {}
  return by[store.period] || []
})
const center = computed(() => {
  const by = exp.value.donut_center_by_period || {}
  return by[store.period] || { title: '期间费用', total_disp: '' }
})
const views = computed(() => {
  const by = exp.value.views_by_period || {}
  return by[store.period] || { total_disp: '', by_category: [], by_pc: [], by_dept: [] }
})

const hbar = computed((): ExpenseHBar[] => {
  if (mode.value === 'fine') return views.value.by_category || []
  if (mode.value === 'pc') return views.value.by_pc || []
  if (mode.value === 'dept') return views.value.by_dept || []
  return []
})

const openFine = ref<string | null>(null)

const legendColors = computed(() =>
  items.value.map((_, i) => SERIES_PALETTE[i % SERIES_PALETTE.length]),
)

const option = computed(() => {
  const data = items.value
  const c = center.value
  const ink = chartTextColor()
  const mut = chartMutedColor()
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number; name: string }) => {
        const it = data[p.dataIndex]
        return `${p.name}<br/>${it?.value_disp || '—'}万（${it?.pct_disp || '—'}）`
      },
    },
    color: SERIES_PALETTE,
    series: [
      {
        type: 'pie',
        radius: ['44%', '70%'],
        center: ['50%', '48%'],
        avoidLabelOverlap: true,
        data: data.map((d, i) => ({
          name: d.name,
          value: d.value,
          itemStyle: { color: SERIES_PALETTE[i % SERIES_PALETTE.length] },
        })),
        /* 54.2：图例在下方，饼周不挤字 */
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          shadowBlur: 0,
          shadowColor: 'transparent',
          borderColor: 'rgba(4,8,20,0.45)',
          borderWidth: 2,
        },
        emphasis: pieEmphasis(),
        animationType: 'expansion',
        animationDuration: 0,
      },
    ],
    graphic: [
      {
        type: 'group',
        left: 'center',
        top: 'middle',
        children: [
          {
            type: 'text',
            style: {
              text: c.title || '期间费用',
              textAlign: 'center',
              fill: mut,
              fontSize: 12,
              fontWeight: 500,
            },
            top: -12,
          },
          {
            type: 'text',
            style: {
              text: c.total_disp ? `${c.total_disp}万` : '',
              textAlign: 'center',
              fill: ink,
              fontSize: 18,
              fontWeight: 800,
            },
            top: 6,
          },
        ],
      },
    ],
    ...animBlock(),
  }
})
</script>
<template>
  <SciFiPanel
    title="期间费用构成"
    :tag="String((views.total_disp as string) || center.total_disp || '')"
    panel-class="exp-donut-card"
    style="margin-top: 16px"
  >
    <div class="ev-tabs" style="display: flex; gap: 6px; padding: 4px 0 8px">
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'donut' }" @click="mode = 'donut'">按大类</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'fine' }" @click="mode = 'fine'">按类别</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'pc' }" @click="mode = 'pc'">按利润中心</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'dept' }" @click="mode = 'dept'">按部门</button>
    </div>
    <div v-if="mode === 'donut' && items.length" class="ev-body">
      <div style="height: 280px">
        <EchartsHost :option="option" />
      </div>
      <div class="ev-legend-row">
        <span v-for="(it, i) in items" :key="it.name" class="ev-legend-item">
          <i :style="{ background: legendColors[i], color: legendColors[i] }" />
          {{ it.name }}
          <em>{{ it.value_disp }}万</em>
        </span>
      </div>
    </div>
    <div v-else-if="mode !== 'donut'" class="ev-list" style="padding: 8px 12px">
      <div
        v-for="(row, i) in hbar"
        :key="i"
        class="ev-row"
        @click="openFine = openFine === row.key ? null : row.key"
      >
        <span class="ev-name">{{ row.name }}</span>
        <span class="ev-track"><i :style="{ width: row.bar_w + '%' }"></i></span>
        <span class="ev-amt">{{ row.amt_disp }}</span>
        <div v-if="openFine === row.key && row.fine?.length" class="ev-fine" style="width: 100%; padding-left: 12px">
          <div v-for="(f, j) in row.fine" :key="j" class="pl-drow sub">
            <span>{{ f.name }}</span><span>{{ f.amt_disp }}</span>
          </div>
        </div>
      </div>
      <div v-if="!hbar.length" class="ev-empty">本期无数据</div>
    </div>
    <div v-else class="ev-empty">本期无数据</div>
  </SciFiPanel>
</template>
