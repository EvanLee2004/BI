<script setup lang="ts">
/**
 * 板块四：下单/回款双系列排名（CSS RankList，非 ECharts）+ 其余弹窗 + 月度下钻。
 * Layer 3：只取数 + 组装 Layer 2。
 */
import { computed, ref } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
import SciFiPanel from './SciFiPanel.vue'
import RankList from './base/RankList.vue'
import RankBar from './base/RankBar.vue'
import DataModal from './base/DataModal.vue'
import type { RankItem, RankView, RankViewBlk } from '../types/vm'
import type { RankListItem } from './base/RankList.vue'

const store = useCockpitStore()

const view = computed((): RankView | null => {
  return store.vm?.rankings?.rankings_view?.[store.period] || null
})

const dailyOn = computed(() => store.dailyActive && !!store.dailyDual)
const rangeLabel = computed(() =>
  store.dailyRange.start === store.dailyRange.end
    ? store.dailyRange.start
    : `${store.dailyRange.start} ~ ${store.dailyRange.end}`,
)
const blkPair = computed((): (RankViewBlk | undefined)[] => {
  if (dailyOn.value) return [store.dailyDual?.sales, store.dailyDual?.customer]
  return [view.value?.sales, view.value?.customer]
})
const visible = computed(() => dailyOn.value || !!(view.value && view.value.visible !== false))

function blkTitle(blk: RankViewBlk | undefined): string {
  const t = blk?.title || ''
  const base = dailyOn.value ? `${t} · 区间 ${rangeLabel.value}` : t
  const n = (blk?.items || []).length
  if (!n) return base
  return `${base} · 前${n}名`
}

const monthly = computed(() => {
  return store.vm?.rankings?.rankings_monthly_data || {}
})

const monthModal = ref(false)
const monthTitle = ref('')
const monthRows = ref<RankItem[]>([])

function toListItems(blk: RankViewBlk | undefined): RankListItem[] {
  return (blk?.items || []).map((it) => ({
    i: it.i,
    name: it.name,
    wo: it.wo,
    wr: it.wr,
    order_disp: it.order_disp,
    receipt_disp: it.receipt_disp,
    mkey: it.mkey,
  }))
}

function fetchFull(blk: RankViewBlk) {
  return async (): Promise<RankListItem[]> => {
    const local = blk.full_items || []
    if (local.length) {
      return local.map((it, idx) => ({
        i: it.i ?? idx + 1,
        name: it.name,
        wo: it.wo,
        wr: it.wr,
        order_disp: it.order_disp,
        receipt_disp: it.receipt_disp,
        mkey: it.mkey,
      }))
    }
    const dim = blk.dim === 'customer' ? 'customer' : 'sales'
    const period = encodeURIComponent(store.period || '')
    const buQ =
      store.scope === 'bu' && store.buName
        ? `&bu=${encodeURIComponent(store.buName)}`
        : ''
    const r = await fetch(`/api/v1/rankings/full?period=${period}&dim=${dim}${buQ}`, {
      credentials: 'same-origin',
    })
    if (!r.ok) {
      console.warn('[rankings/full]', r.status)
      throw new Error('加载完整排名失败')
    }
    const d = (await r.json()) as { items?: RankItem[] }
    return (d.items || []).map((it, idx) => ({
      i: it.i ?? idx + 1,
      name: it.name,
      wo: it.wo,
      wr: it.wr,
      order_disp: it.order_disp,
      receipt_disp: it.receipt_disp,
      mkey: it.mkey,
    }))
  }
}

function onItemClick(it: RankListItem) {
  if (!it.mkey) return
  const rows = monthly.value[it.mkey] || []
  monthTitle.value = it.name + ' · 1~12 月下单/回款'
  monthRows.value = rows
  monthModal.value = true
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
    <div
      class="grid-2e dual-grid"
      :data-start="dailyOn ? store.dailyRange.start : view?.start"
      :data-end="dailyOn ? store.dailyRange.end : view?.end"
    >
      <SciFiPanel
        v-for="blk in blkPair"
        :key="(blk?.dim || '') + (dailyOn ? 'd' : 'v')"
        :data-dim="blk?.dim"
      >
        <template #header>
          <span>{{ blkTitle(blk) }}</span>
        </template>
        <RankList
          dual
          legend
          :items="toListItems(blk)"
          :empty="!blk || blk.empty || !(blk.items && blk.items.length)"
          :others="blk?.others || null"
          :full-items="blk?.full_items || []"
          :fetch-full="blk ? fetchFull(blk) : undefined"
          :modal-title="(blk?.title || '') + ' · 完整排名'"
          :on-item-click="onItemClick"
        />
      </SciFiPanel>
    </div>
    <DataModal :open="monthModal" :title="monthTitle" @close="monthModal = false">
      <div v-if="!monthRows.length" class="rank-list__empty">暂无数据</div>
      <RankBar
        v-for="(it, idx) in monthRows"
        :key="'mo' + idx + it.name"
        :rank="it.i ?? idx + 1"
        :name="String(it.name || '')"
        dual
        :primary-width="Number(it.wo) || 0"
        :primary-value="it.order_disp"
        :secondary-width="Number(it.wr) || 0"
        :secondary-value="it.receipt_disp"
      />
    </DataModal>
  </div>
</template>
