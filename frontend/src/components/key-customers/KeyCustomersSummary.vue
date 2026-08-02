<script setup lang="ts">
/**
 * 经营摘要三等宽卡：全部客户、重点客户贡献、临界晋级。
 * 3.7.5：删除顶栏第二排「需跟进重点客户」卡；行动队列/筛选入口仍在下方工作台。
 */
import type { KeyCustomersVM } from '../../types/vm'

const props = defineProps<{
  cards: NonNullable<KeyCustomersVM['summary_cards']>
  nearTip: string
  nearCount?: number
  /** @deprecated 3.7.5 摘要区不再展示需跟进卡；保留 prop 兼容调用方 */
  silentCount?: number
  hasNearList?: boolean
}>()

const emit = defineEmits<{
  openNear: []
  openSilent: []
}>()

function onNearActivate() {
  if (props.hasNearList) emit('openNear')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    onNearActivate()
  }
}
</script>

<template>
  <section class="kc-summary-cards kc-summary-cards--triple" data-testid="kc-summary-cards" aria-label="经营摘要">
    <div class="kc-card" data-testid="kc-card-total">
      <div class="kc-card__label">{{ cards.total?.label || '全部客户 / 年累计' }}</div>
      <div class="kc-card__value">{{ cards.total?.value_disp || '—' }}</div>
    </div>
    <div class="kc-card" data-testid="kc-card-contrib" :title="cards.focus_contrib?.tip">
      <div class="kc-card__label">{{ cards.focus_contrib?.label || '重点客户贡献' }}</div>
      <div class="kc-card__value">{{ cards.focus_contrib?.value_disp || '—' }}</div>
      <div class="kc-card__sub">{{ cards.focus_contrib?.amount_disp }}</div>
    </div>
    <div
      class="kc-card"
      :class="{ 'kc-card--action': hasNearList }"
      data-testid="kc-card-near"
      :title="cards.near_upgrade?.tip || nearTip"
      :role="hasNearList ? 'button' : undefined"
      :tabindex="hasNearList ? 0 : undefined"
      @click="onNearActivate"
      @keydown="onKey"
    >
      <div class="kc-card__label">{{ cards.near_upgrade?.label || '临界晋级客户' }}</div>
      <div class="kc-card__value">{{ cards.near_upgrade?.value_disp || '—' }}</div>
      <div v-if="hasNearList" class="kc-card__action" data-testid="kc-near-entry">
        查看名单 →
      </div>
      <div v-else class="kc-card__sub" data-testid="kc-near-empty-reason">
        当前无临界晋级名单可进入
      </div>
    </div>
  </section>
</template>
