<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
// rankings_view 叶子由后端算好显示串；此处用 profit_rank 预渲染 HTML 作板块三
const profitHtml = computed(() => {
  const r = store.vm?.rankings as { profit_rank_body?: Record<string, string> } | undefined
  return r?.profit_rank_body?.[store.period] || ''
})
</script>
<template>
  <div class="rank-host" v-html="profitHtml"></div>
</template>
