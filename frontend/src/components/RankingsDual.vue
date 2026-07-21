<script setup lang="ts">
/**
 * 板块四：下单/回款双系列横向条形图（ECharts）+ 其余弹窗 + 月度下钻。
 * 与 DailyQuery 共用 dualRankBarOption，保证样式/顺序一致；放大行高。
 */
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import EchartsHost from './charts/EchartsHost.vue'
import SciFiPanel from './SciFiPanel.vue'
import { dualRankBarOption, dualRankItemAt } from '../dual-rank-option'
import type { RankItem, RankView, RankViewBlk } from '../types/vm'

const store = useCockpitStore()

type DualItem = RankItem
type DualBlk = RankViewBlk

const view = computed((): RankView | null => {
  return store.vm?.rankings?.rankings_view?.[store.period] || null
})

/** B-01：按时间段查询激活时，排名双卡「原位」切换为区间结果（回款总图不动、版面不跳）。 */
const dailyOn = computed(() => store.dailyActive && !!store.dailyDual)
const rangeLabel = computed(() =>
  store.dailyRange.start === store.dailyRange.end
    ? store.dailyRange.start
    : `${store.dailyRange.start} ~ ${store.dailyRange.end}`,
)
const blkPair = computed((): (DualBlk | undefined)[] => {
  if (dailyOn.value) return [store.dailyDual?.sales, store.dailyDual?.customer]
  return [view.value?.sales, view.value?.customer]
})
const visible = computed(() => dailyOn.value || !!(view.value && view.value.visible !== false))
function blkTitle(blk: DualBlk | undefined): string {
  const t = blk?.title || ''
  const base = dailyOn.value ? `${t} · 区间 ${rangeLabel.value}` : t
  // 任务书61·D2：标注前 N 名（按后端 items 实际条数，常见 top10）
  const n = (blk?.items || []).length
  if (!n) return base
  return `${base} · 前${n}名`
}

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
  return dualRankBarOption(blk)
}

function chartH(blk: DualBlk | undefined): number {
  const opt = dualRankBarOption(blk)
  return typeof opt._chartH === 'number' ? opt._chartH : 480
}

function onChartClick(blk: DualBlk | undefined, params: { dataIndex?: number }) {
  const it = dualRankItemAt(blk, params.dataIndex)
  if (it) openMonthly(it)
}

function pct(v: unknown): string {
  const n = v == null ? 0 : Number(v)
  return (Number.isFinite(n) ? n : 0).toFixed(1)
}
</script>
<template>
  <div
    v-if="visible"
    id="rankViews"
    class="rank-host dual-rankings"
    data-source="rankings_view"
    :data-daily="dailyOn ? '1' : '0'"
    :data-start="dailyOn ? store.dailyRange.start : view?.start"
    :data-end="dailyOn ? store.dailyRange.end : view?.end"
  >
    <div class="grid-2e dual-grid" :data-start="dailyOn ? store.dailyRange.start : view?.start" :data-end="dailyOn ? store.dailyRange.end : view?.end">
      <SciFiPanel
        v-for="blk in blkPair"
        :key="(blk?.dim || '') + (dailyOn ? 'd' : 'v')"
        :data-dim="blk?.dim"
      >
        <template #header>
          <span>{{ blkTitle(blk) }}</span>
          <span class="dual-legend">
            <span class="dual-leg dual-o">紫=下单</span>
            <span class="dual-leg dual-r">青=回款</span>
          </span>
        </template>
        <div v-if="!blk || blk.empty || !(blk.items && blk.items.length)" class="ev-empty">本期无数据</div>
        <div v-else class="rk-card-body">
          <div class="rank-chart-host" :style="{ height: chartH(blk) + 'px', minHeight: '420px' }">
            <EchartsHost
              :option="barOption(blk)"
              @click="(p) => onChartClick(blk, p)"
            />
          </div>
          <!-- 任务书61·D1：其余入口完整可见可点，禁止被容器裁切露半行 -->
          <button
            v-if="blk.others"
            type="button"
            class="rk-others-btn"
            data-testid="rk-others-btn"
            title="点开展示前 N 名以后的完整明细"
            @click="openOthers(blk)"
          >
            <span class="rk-no">…</span>
            <span class="ev-name"
              >其余 {{ blk.others.names }} 个 <span class="rk-open">点开展示明细 ›</span></span
            >
            <span class="ev-amt">{{ blk.others.amt }}</span>
          </button>
        </div>
      </SciFiPanel>
    </div>

    <Teleport to="body">
      <div v-if="modal" id="rkModal" class="rkm-mask" style="display: flex" @click.self="closeModal">
        <div class="rkm" role="dialog" aria-modal="true">
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

<style scoped>
.rk-card-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: visible;
}
.rk-others-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid rgba(125, 211, 252, 0.18);
  border-radius: 8px;
  background: rgba(34, 211, 238, 0.06);
  color: var(--ink, #e8eef8);
  cursor: pointer;
  text-align: left;
  font: inherit;
  flex-shrink: 0;
}
.rk-others-btn:hover {
  border-color: rgba(34, 211, 238, 0.45);
  background: rgba(34, 211, 238, 0.12);
}
.rk-others-btn .ev-name {
  flex: 1;
  min-width: 0;
}
.rk-others-btn .rk-open {
  color: #22d3ee;
  font-weight: 600;
}
.rk-others-btn .ev-amt {
  font-family: var(--num-font, ui-monospace, monospace);
  font-size: 12px;
  color: var(--note, #8b9bb4);
  white-space: nowrap;
}
</style>
