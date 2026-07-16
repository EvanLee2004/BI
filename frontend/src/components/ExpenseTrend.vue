<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const e = store.vm?.expense as { trend_html?: string } | undefined
  return e?.trend_html || ''
})
</script>
<template>
  <div v-html="html"></div>
</template>
