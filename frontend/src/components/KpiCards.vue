<script setup lang="ts">
import { computed } from 'vue'
import { useCockpitStore } from '../stores/cockpit'
const store = useCockpitStore()
const html = computed(() => {
  const kpi = store.vm?.kpi as { body_by_period?: Record<string, string> } | undefined
  return kpi?.body_by_period?.[store.period] || ''
})
</script>
<template>
  <div class="kpi-host" v-html="html"></div>
</template>
