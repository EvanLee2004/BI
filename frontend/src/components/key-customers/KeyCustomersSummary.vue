<script setup lang="ts">
import type { KeyCustomersVM } from '../../types/vm'

defineProps<{
  cards: NonNullable<KeyCustomersVM['summary_cards']>
  silentTip: string
  nearTip: string
}>()
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
    <div class="kc-card" data-testid="kc-card-silent" :title="cards.silent_focus?.tip || silentTip">
      <div class="kc-card__label">{{ cards.silent_focus?.label || '需跟进重点客' }}</div>
      <div class="kc-card__value">{{ cards.silent_focus?.value_disp || '—' }}</div>
    </div>
    <div class="kc-card" data-testid="kc-card-near" :title="cards.near_upgrade?.tip || nearTip">
      <div class="kc-card__label">{{ cards.near_upgrade?.label || '临界晋级客户' }}</div>
      <div class="kc-card__value">{{ cards.near_upgrade?.value_disp || '—' }}</div>
    </div>
  </section>
</template>
