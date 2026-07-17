<script setup lang="ts">
/**
 * 板块四：下单/回款双系列横向条形图（ECharts）+ 其余弹窗 + 月度下钻。
 * 铁律2：金额串/系列值全后端；前端只摆 option。
 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import type { RankItem, RankView, RankViewBlk } from '../types/vm'

const store = useCockpitStore()

type DualItem = RankItem
type DualBlk = RankViewBlk

const view = computed((): RankView | null => {
  return store.vm?.rankings?.rankings_view?.[store.period] || null
})

const monthly = computed(() => {
  return store.vm?.rankings?.rankings_monthly_data || {}
})

const modal = ref(false)
const modalTitle = ref('')
const modalTag = ref('')
const modalItems = ref<DualItem[]>([])

function openModal(title: string, tag: string, items: DualItem[]) {
  modalTitle.value = title
  modalTag.value = tag
  modalItems.value = items
  modal.value = true
}
function closeModal() {
  modal.value = false
}
function openOthers(blk: DualBlk) {
  openModal((blk.title || '') + ' · 完整排名', '', blk.full_items || [])
}
function openMonthly(it: DualItem) {
  if (!it.mkey) return
  const rows = monthly.value[it.mkey] || []
  openModal(it.name + ' · 1~12 月下单/回款', '', rows)
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') closeModal()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))

function barOption(blk: DualBlk | undefined) {
  const items = [...(blk?.items || [])].reverse() // 横向条图顶=第1名
  const names = items.map((it) => it.name)
  const orders = items.map((it) => Number(it.wo) || 0) // 用后端宽度百分比作条长（非金额运算）
  const receipts = items.map((it) => Number(it.wr) || 0)
  const od = items.map((it) => it.order_disp || '')
  const rd = items.map((it) => it.receipt_disp || '')
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number; seriesName: string }[]) => {
        const i = params?.[0]?.dataIndex ?? 0
        const it = items[i]
        return `${it?.name || ''}<br/>下单 ${od[i]}<br/>回款 ${rd[i]}`
      },
    },
    legend: { data: ['下单', '回款'] },
    grid: { left: 100, right: 48, top: 28, bottom: 16 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: { width: 90, overflow: 'truncate' },
    },
    series: [
      {
        name: '下单',
        type: 'bar',
        data: orders,
        itemStyle: { color: '#a78bfa' },
        label: {
          show: true,
          position: 'right',
          formatter: (p: { dataIndex: number }) => od[p.dataIndex] || '',
          fontSize: 10,
        },
      },
      {
        name: '回款',
        type: 'bar',
        data: receipts,
        itemStyle: { color: '#2dd4bf' },
        label: {
          show: true,
          position: 'right',
          formatter: (p: { dataIndex: number }) => rd[p.dataIndex] || '',
          fontSize: 10,
        },
      },
    ],
    animationDuration: 600,
  }
}

function onChartClick(blk: DualBlk | undefined, params: { dataIndex?: number }) {
  if (!blk?.items || params.dataIndex == null) return
  // reverse 后的 index
  const items = [...(blk.items || [])].reverse()
  const it = items[params.dataIndex]
  if (it) openMonthly(it)
}

function pct(v: unknown): string {
  const n = v == null ? 0 : Number(v)
  return (Number.isFinite(n) ? n : 0).toFixed(1)
}
</script>
<template>
  <div
    v-if="view && view.visible !== false"
    id="rankViews"
    class="rank-host dual-rankings"
    data-source="rankings_view"
    :data-start="view.start"
    :data-end="view.end"
  >
    <div class="grid-2e dual-grid" :data-start="view.start" :data-end="view.end">
      <div v-for="blk in [view.sales, view.customer]" :key="blk?.dim || Math.random()" class="card" :data-dim="blk?.dim">
        <div class="card-h">
          {{ blk?.title }}
          <span class="dual-legend">
            <span class="dual-leg dual-o">紫=下单</span>
            <span class="dual-leg dual-r">青=回款</span>
          </span>
        </div>
        <div v-if="!blk || blk.empty || !(blk.items && blk.items.length)" class="ev-empty">本期无数据</div>
        <div v-else>
          <div style="height: 320px">
            <EchartsHost
              :option="barOption(blk)"
              @click="(p) => onChartClick(blk, p)"
            />
          </div>
          <div
            v-if="blk.others"
            class="ev-row rk-row rk-others rk-more"
            title="点开看 10 名以后的完整明细"
            style="cursor: pointer; padding: 8px 12px"
            @click="openOthers(blk)"
          >
            <span class="rk-no">…</span>
            <span class="ev-name"
              >其余 {{ blk.others.names }} 个 <span class="rk-open">点开看明细 ›</span></span
            >
            <span class="ev-amt">{{ blk.others.amt }}</span>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="modal" id="rkModal" class="rkm-mask" style="display: flex" @click.self="closeModal">
        <div class="rkm">
          <div class="rkm-h">
            <b id="rkmTitle">{{ modalTitle }}</b>
            <span id="rkmTag" class="tag">{{ modalTag }}</span>
            <button type="button" class="ghost mini" id="rkmClose" @click="closeModal">关闭</button>
          </div>
          <div class="rkm-list" id="rkmList">
            <div v-if="!modalItems.length" class="ev-empty">本期无数据</div>
            <div v-else class="ev-list">
              <div v-for="it in modalItems" :key="'m' + it.i + it.name" class="ev-row dual-row">
                <span class="rk-no">{{ it.i }}</span>
                <span class="ev-name" :title="it.name">{{ it.name }}</span>
                <div class="dual-bars">
                  <span class="dual-bar dual-o"
                    ><i :style="{ width: pct(it.wo) + '%' }"></i><em>{{ it.order_disp }}</em></span
                  >
                  <span class="dual-bar dual-r"
                    ><i :style="{ width: pct(it.wr) + '%' }"></i><em>{{ it.receipt_disp }}</em></span
                  >
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
