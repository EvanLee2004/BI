<script setup lang="ts">
/** 期间费用构成：环形 + 构成四态切换 + 抽屉。数字全后端。
 *  任务书54.1：V4 环形 hover 光晕 + V6 文字清晰。
 */
import { computed, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import {
  animBlock,
  animDuration,
  chartMutedColor,
  chartTextColor,
  pieEmphasis,
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
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        avoidLabelOverlap: true,
        data: data.map((d) => ({ name: d.name, value: d.value })),
        label: {
          formatter: (p: { dataIndex: number; name: string }) => {
            const it = data[p.dataIndex]
            return `${p.name}\n${it?.pct_disp || ''}`
          },
          fontSize: 12,
          color: ink,
          fontWeight: 600,
          textBorderColor: 'rgba(4,8,20,0.75)',
          textBorderWidth: 2,
        },
        labelLine: { length: 14, length2: 10, lineStyle: { width: 1.5 } },
        itemStyle: {
          shadowBlur: 12,
          shadowColor: 'rgba(34,211,238,0.25)',
          borderColor: 'rgba(4,8,20,0.35)',
          borderWidth: 1,
        },
        emphasis: pieEmphasis(),
        animationType: 'scale',
        animationDuration: animDuration(600),
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
            top: -10,
          },
          {
            type: 'text',
            style: {
              text: '合计' + (c.total_disp || ''),
              textAlign: 'center',
              fill: ink,
              fontSize: 15,
              fontWeight: 700,
            },
            top: 8,
          },
        ],
      },
    ],
    ...animBlock(animDuration(600)),
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
      <EchartsHost :option="option" />
      <div class="legend" style="display: flex; flex-wrap: wrap; gap: 8px 14px; justify-content: center; margin-top: 8px">
        <span v-for="it in items" :key="it.name" class="muted" style="font-size: 12px">
          {{ it.name }} {{ it.value_disp }}万（{{ it.pct_disp }}）
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
