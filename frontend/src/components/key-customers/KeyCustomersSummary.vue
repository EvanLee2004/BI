<script setup lang="ts">
/**
 * 经营摘要三卡：重点客户贡献、临界晋级（可进名单）、需跟进数量与入口。
 * 3.7.4：行动信息 + 入口；临界无名单时明确说明原因。
 */
import type { KeyCustomersVM } from '../../types/vm'

const props = defineProps<{
  cards: NonNullable<KeyCustomersVM['summary_cards']>
  nearTip: string
  nearCount?: number
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

function onSilentActivate() {
  if ((props.silentCount || 0) > 0) emit('openSilent')
}

function onKey(e: KeyboardEvent, kind: 'near' | 'silent') {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    if (kind === 'near') onNearActivate()
    else onSilentActivate()
  }
}
</script>

<template>
  <section class="kc-summary-cards" data-testid="kc-summary-cards" aria-label="经营摘要">
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
      @keydown="onKey($event, 'near')"
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
    <div
      v-if="(silentCount || 0) > 0"
      class="kc-card kc-card--action"
      data-testid="kc-card-silent"
      role="button"
      tabindex="0"
      @click="onSilentActivate"
      @keydown="onKey($event, 'silent')"
    >
      <div class="kc-card__label">需跟进重点客</div>
      <div class="kc-card__value">{{ silentCount }}</div>
      <div class="kc-card__action" data-testid="kc-silent-entry">查看需跟进 →</div>
    </div>
  </section>
</template>
