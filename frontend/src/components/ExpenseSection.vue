<script setup lang="ts">
/** 期间费用构成：环形（按大类） + 三态进度条列表（按类别 / 按利润中心 / 按部门）。
 *  2026-07-21：三态列表点某一行 → 右侧抽屉展开该项「费用明细」，与「管理利润表」(PLTable) 同一交互；
 *  取代早前的左右分栏 master-detail 与行内嵌展开。
 *  54.14 R-20：center.total_disp 已含「万」，禁止再拼单位。
 *  铁律17：抽屉 position:fixed，必须 Teleport to body（与 PLTable 一致）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

type ListMode = 'fine' | 'pc' | 'dept'

const store = useCockpitStore()
const exp = computed((): Partial<ExpenseVM> => store.vm?.expense || {})
const mode = ref<'donut' | ListMode>('donut')

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

const isListMode = computed(
  () => mode.value === 'fine' || mode.value === 'pc' || mode.value === 'dept',
)

const hbar = computed((): ExpenseHBar[] => {
  if (mode.value === 'fine') return views.value.by_category || []
  if (mode.value === 'pc') return views.value.by_pc || []
  if (mode.value === 'dept') return views.value.by_dept || []
  return []
})

/** 右侧抽屉：选中行 key；切 tab / 切周期都关闭清空（开合模型与 PLTable 抽屉一致）。 */
const openKey = ref<string | null>(null)
const drawerOpen = computed(() => isListMode.value && !!openKey.value)
const openRow = computed((): ExpenseHBar | null => {
  if (!openKey.value) return null
  return hbar.value.find((r) => r.key === openKey.value) || null
})

const entityLabel = computed(() => {
  if (mode.value === 'fine') return '类别'
  if (mode.value === 'pc') return '利润中心'
  return '部门'
})
const emptyFineText = computed(() => `该${entityLabel.value}无细类明细`)

function openDrawer(row: ExpenseHBar) {
  openKey.value = row.key
}
function closeDrawer() {
  openKey.value = null
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeDrawer()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))

watch(mode, () => {
  openKey.value = null
})
watch(
  () => store.period,
  () => {
    openKey.value = null
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
      <!-- 按类别 / 按利润中心 / 按部门：进度条列表，点行开右侧抽屉 -->
      <div
        v-else-if="isListMode"
        class="ev-list exp-hbar-scroll"
        style="padding: 8px 12px"
        data-testid="exp-list"
        :data-mode="mode"
      >
        <div
          v-for="(row, i) in hbar"
          :key="mode + '-' + i + '-' + row.key"
          class="ev-row exp-bar-row"
          :class="{ on: openKey === row.key }"
          data-testid="exp-bar-row"
          @click="openDrawer(row)"
        >
          <span class="ev-name">{{ row.name }}</span>
          <span class="ev-track"><i :style="{ width: row.bar_w + '%' }"></i></span>
          <span class="ev-amt">{{ row.amt_disp }}</span>
        </div>
        <div v-if="!hbar.length" class="ev-empty">本期无数据</div>
      </div>
      <div v-else class="ev-empty">本期无数据</div>
    </div>

    <!-- 右侧抽屉：与 PLTable 同一套 body 直下 fixed（Teleport）；复用全局 drawer/pl-drow 样式 -->
    <Teleport to="body">
      <div v-if="drawerOpen && openRow" class="drawer open" aria-hidden="false">
        <div class="drawer-mask" data-testid="exp-drawer-mask" @click="closeDrawer"></div>
        <div class="drawer-panel" data-testid="exp-drawer-panel">
          <div class="drawer-h">
            <b>{{ openRow.name }} · 费用明细</b>
            <button type="button" class="ghost mini" data-close @click="closeDrawer">关闭</button>
          </div>
          <div class="drawer-body">
            <template v-if="openRow.fine && openRow.fine.length">
              <div v-for="(f, j) in openRow.fine" :key="j" class="pl-drow sub">
                <span class="pl-name">{{ f.name }}</span>
                <span class="pl-amt">{{ f.amt_disp }}</span>
              </div>
            </template>
            <div v-else class="ev-empty">{{ emptyFineText }}</div>
          </div>
        </div>
      </div>
    </Teleport>
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
.exp-bar-row {
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s ease;
}
.exp-bar-row:hover {
  background: rgba(34, 211, 238, 0.08);
}
.exp-bar-row.on {
  background: rgba(34, 211, 238, 0.12);
  outline: 1px solid rgba(34, 211, 238, 0.35);
}
</style>
