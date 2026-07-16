<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const r = store.vm?.receipts as { receipts_budget?: string; receipts_html?: string } | undefined
  return r?.receipts_budget || r?.receipts_html || ''
})
</script>
<template>
  <div v-html="html"></div>
</template>
