<script setup lang="ts">
/**
 * Layer 2 · RankList
 * 列表 + 「其余 N 个」+ 点开弹层（按需拉取 / 加载中 / 失败态）
 * 弹层逻辑收敛于此，杜绝「改了一个漏另一个」。
 */
import { ref } from 'vue'
import RankBar from './RankBar.vue'
import DataModal from './DataModal.vue'

export type RankListItem = {
  i?: number | string
  name: string
  /** 单条：bar 宽度 */
  bar_w?: number
  revenue_disp?: string
  margin_disp?: string
  /** 双条 */
  wo?: number
  wr?: number
  order_disp?: string
  receipt_disp?: string
  mkey?: string
}

const props = withDefaults(
  defineProps<{
    items?: RankListItem[]
    empty?: boolean
    dual?: boolean
    others?: { names?: number | string; amt_disp?: string; amt?: string } | null
    /** 本地 full；空则走 fetchFull */
    fullItems?: RankListItem[]
    fetchFull?: () => Promise<RankListItem[]>
    modalTitle?: string
    showMeta?: boolean
    metaLabel?: string
    metaTitle?: string
    legend?: boolean
    /** 行点击（如月度下钻） */
    onItemClick?: (it: RankListItem) => void
  }>(),
  {
    items: () => [],
    empty: false,
    dual: false,
    fullItems: () => [],
    showMeta: false,
    legend: false,
  },
)

const modal = ref(false)
const modalTag = ref('')
const modalItems = ref<RankListItem[]>([])
const modalTitleRef = ref('')

async function openOthers() {
  const title = props.modalTitle || '完整排名'
  modalTitleRef.value = title
  const local = props.fullItems || []
  if (local.length) {
    modalTag.value = ''
    modalItems.value = local
    modal.value = true
    return
  }
  if (!props.fetchFull) {
    modalTag.value = '本期无数据'
    modalItems.value = []
    modal.value = true
    return
  }
  modalTag.value = '加载中…'
  modalItems.value = []
  modal.value = true
  try {
    const items = await props.fetchFull()
    modalItems.value = (items || []).map((it, idx) => ({
      ...it,
      i: it.i ?? idx + 1,
    }))
    modalTag.value = modalItems.value.length ? '' : '本期无数据'
  } catch {
    modalTag.value = '加载失败'
    modalItems.value = []
  }
}

function close() {
  modal.value = false
}

function barW(it: RankListItem): number {
  if (it.bar_w != null) return Number(it.bar_w) || 0
  return 0
}

defineExpose({ openOthers })
</script>

<template>
  <div class="rank-list" data-testid="rank-list">
    <div v-if="legend && dual" class="rank-list__legend">
      <span class="rank-list__leg-o">下单</span>
      <span class="rank-list__leg-r">回款</span>
    </div>
    <div
      v-if="showMeta && metaLabel && !dual"
      class="rank-list__meta-col-label"
      :title="metaTitle || metaLabel"
    >
      <span class="rank-bar__meta-head">{{ metaLabel }}</span>
    </div>
    <div v-if="empty || !items?.length" class="rank-list__empty">本期无数据</div>
    <template v-else>
      <div
        v-for="it in items"
        :key="String(it.i) + it.name"
        class="rank-list__row"
        :class="{ 'is-clickable': !!onItemClick && it.mkey }"
        @click="onItemClick && it.mkey ? onItemClick(it) : undefined"
      >
        <RankBar
          :rank="it.i ?? ''"
          :name="it.name"
          :dual="dual"
          :primary-width="dual ? Number(it.wo) || 0 : barW(it)"
          :primary-value="dual ? it.order_disp : it.revenue_disp"
          :secondary-width="dual ? Number(it.wr) || 0 : 0"
          :secondary-value="dual ? it.receipt_disp : undefined"
          :meta="showMeta ? it.margin_disp : undefined"
          :meta-label="showMeta ? metaLabel : undefined"
          :meta-title="metaTitle"
        />
      </div>
      <button
        v-if="others"
        type="button"
        class="rank-list__others"
        data-testid="rank-others-btn"
        title="点开展示完整明细"
        @click="openOthers"
      >
        <span class="rank-bar__no">…</span>
        <span class="rank-bar__name"
          >其余 {{ others.names }} 个 <span class="rank-list__open">点开展示明细 ›</span></span
        >
        <span class="rank-list__others-amt">{{ others.amt_disp || others.amt || '' }}</span>
      </button>
    </template>

    <DataModal :open="modal" :title="modalTitleRef" :tag="modalTag" @close="close">
      <div v-if="!modalItems.length" class="rank-list__empty">
        {{ modalTag || '本期无数据' }}
      </div>
      <div v-else data-testid="rank-modal-list">
        <RankBar
          v-for="it in modalItems"
          :key="'m' + it.i + it.name"
          :rank="it.i ?? ''"
          :name="it.name"
          :dual="dual"
          :primary-width="dual ? Number(it.wo) || 0 : barW(it)"
          :primary-value="dual ? it.order_disp : it.revenue_disp"
          :secondary-width="dual ? Number(it.wr) || 0 : 0"
          :secondary-value="dual ? it.receipt_disp : undefined"
          :meta="showMeta ? it.margin_disp : undefined"
          :meta-label="showMeta ? metaLabel : undefined"
          :meta-title="metaTitle"
        />
      </div>
    </DataModal>
  </div>
</template>
