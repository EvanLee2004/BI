<script setup lang="ts">
/** 板块三：收入与毛利结构（确认口径·按客户/按销售）——显示串来自 VM profit_rank_body */
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const r = store.vm?.rankings as { profit_rank_body?: Record<string, string> } | undefined
  return r?.profit_rank_body?.[store.period] || ''
})
</script>
<template>
  <div>
    <div id="profitRankViews" v-html="html"></div>
    <div class="pr-formula">
      <span class="pr-f-h">计算逻辑</span>
      <span class="pr-f-item"><b>交付金额</b> = 智云含税原数</span>
      <span class="pr-f-item"><b>交付收入</b> = 交付金额 ÷ 1.06</span>
      <span class="pr-f-item"><b>系统成本率</b> = 项目成本 ÷ 交付收入</span>
      <span class="pr-f-item"><b>集中度</b> = 前5大交付收入 ÷ 期内总交付收入</span>
    </div>
  </div>
</template>
