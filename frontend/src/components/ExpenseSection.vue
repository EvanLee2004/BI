<script setup lang="ts">
/** 期间费用构成：环形 + 构成四态。
 *  任务书61·F：按部门改 master-detail 左右布局（左列表 / 右明细），不内嵌左框。
 *  54.14 R-20：center.total_disp 已含「万」，禁止再拼单位。
 */
import { computed, ref, watch } from 'vue'
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
import { withWanUnit } from '../utils/disp'
import { themeMode } from '../utils/theme'
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

/** 按类别/利润中心：仍用内嵌展开；按部门：master-detail 选中行 */
const openFine = ref<string | null>(null)
const selectedDeptKey = ref<string | null>(null)

const selectedDept = computed((): ExpenseHBar | null => {
  if (mode.value !== 'dept' || !selectedDeptKey.value) return null
  return hbar.value.find((r) => r.key === selectedDeptKey.value) || null
})

watch(mode, () => {
  openFine.value = null
  selectedDeptKey.value = null
})
watch(
  () => store.period,
  () => {
    openFine.value = null
    selectedDeptKey.value = null
  },
)

const legendColors = computed(() =>
  items.value.map((_, i) => SERIES_PALETTE[i % SERIES_PALETTE.length]),
)

const option = computed(() => {
  void themeMode.value
  const data = items.value
  const c = center.value
  const ink = chartTextColor()
  const mut = chartMutedColor()
  const centerText = withWanUnit(c.total_disp || '')
  return {
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: (p: { dataIndex: number; name: string }) => {
        const it = data[p.dataIndex]
        return `${p.name}<br/>${withWanUnit(it?.value_disp || '—')}（${it?.pct_disp || '—'}）`
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
              text: centerText,
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

function onHbarClick(row: ExpenseHBar) {
  if (mode.value === 'dept') {
    selectedDeptKey.value = selectedDeptKey.value === row.key ? null : row.key
    return
  }
  openFine.value = openFine.value === row.key ? null : row.key
}
</script>
<template>
  <SciFiPanel
    title="期间费用构成"
    :tag="String((views.total_disp as string) || center.total_disp || '')"
    panel-class="exp-donut-card"
    style="margin-top: 16px"
  >
    <div class="ev-tabs" style="display: flex; gap: 6px; padding: 4px 0 8px">
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'donut' }" data-testid="exp-tab-donut" @click="mode = 'donut'">按大类</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'fine' }" data-testid="exp-tab-fine" @click="mode = 'fine'">按类别</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'pc' }" data-testid="exp-tab-pc" @click="mode = 'pc'">按利润中心</button>
      <button type="button" class="ev-tab mini" :class="{ on: mode === 'dept' }" data-testid="exp-tab-dept" @click="mode = 'dept'">按部门</button>
    </div>
    <div class="exp-body-fixed" data-testid="exp-body-fixed">
      <div v-if="mode === 'donut' && items.length" class="ev-body">
        <div style="height: 280px">
          <EchartsHost :option="option" />
        </div>
        <div class="ev-legend-row">
          <span v-for="(it, i) in items" :key="it.name" class="ev-legend-item">
            <i :style="{ background: legendColors[i], color: legendColors[i] }" />
            {{ it.name }}
            <em>{{ withWanUnit(it.value_disp) }}</em>
          </span>
        </div>
      </div>
      <!-- F：按部门 master-detail -->
      <div v-else-if="mode === 'dept'" class="exp-md" data-testid="exp-dept-md">
        <div class="exp-md-list exp-hbar-scroll">
          <div
            v-for="(row, i) in hbar"
            :key="'d' + i"
            class="ev-row exp-md-row"
            :class="{ on: selectedDeptKey === row.key }"
            data-testid="exp-dept-row"
            @click="onHbarClick(row)"
          >
            <span class="ev-name">{{ row.name }}</span>
            <span class="ev-track"><i :style="{ width: row.bar_w + '%' }"></i></span>
            <span class="ev-amt">{{ row.amt_disp }}</span>
          </div>
          <div v-if="!hbar.length" class="ev-empty">本期无数据</div>
        </div>
        <div class="exp-md-detail" data-testid="exp-dept-detail">
          <template v-if="selectedDept">
            <div class="exp-md-detail-h">{{ selectedDept.name }} · 费用明细</div>
            <div v-if="selectedDept.fine?.length" class="exp-md-fine">
              <div v-for="(f, j) in selectedDept.fine" :key="j" class="pl-drow sub exp-md-fine-row">
                <span>{{ f.name }}</span><span>{{ f.amt_disp }}</span>
              </div>
            </div>
            <div v-else class="ev-empty">该部门无细类明细</div>
          </template>
          <div v-else class="ev-empty exp-md-hint">← 点左侧部门查看明细</div>
        </div>
      </div>
      <div v-else-if="mode !== 'donut'" class="ev-list exp-hbar-scroll" style="padding: 8px 12px">
        <div
          v-for="(row, i) in hbar"
          :key="i"
          class="ev-row"
          @click="onHbarClick(row)"
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
    </div>
  </SciFiPanel>
</template>

<style scoped>
.exp-body-fixed {
  min-height: 360px;
}
.exp-hbar-scroll {
  max-height: 360px;
  overflow-y: auto;
}
.exp-md {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  min-height: 320px;
  padding: 4px 0;
}
.exp-md-list {
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 8px;
  padding: 6px 8px;
}
.exp-md-row {
  cursor: pointer;
  border-radius: 6px;
  padding: 6px 8px;
}
.exp-md-row.on {
  background: rgba(34, 211, 238, 0.12);
  outline: 1px solid rgba(34, 211, 238, 0.35);
}
.exp-md-detail {
  border: 1px solid rgba(125, 211, 252, 0.12);
  border-radius: 8px;
  padding: 10px 12px;
  min-height: 200px;
}
.exp-md-detail-h {
  font-weight: 700;
  margin-bottom: 10px;
  color: var(--ink, #e8eef8);
}
.exp-md-fine-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed rgba(125, 211, 252, 0.1);
  font-size: 12.5px;
}
.exp-md-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
}
@media (max-width: 700px) {
  .exp-md {
    grid-template-columns: 1fr;
  }
}
</style>
